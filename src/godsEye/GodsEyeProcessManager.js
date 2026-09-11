/**
 * GodsEyeProcessManager — start / detect / monitor / health-check / stop / restart / getStatus
 * States: NOT_RUNNING, STARTING, HEALTH_CHECKING, READY, FAILED, STOPPING, STOPPED, RECOVERING
 * Single source of truth for process lifecycle; renderer delegates to Electron main via IPC
 */

import { GODS_EYE_URL } from './GodsEyeConfig.js';
import { GodsEyeHealthChecker } from './GodsEyeHealthChecker.js';

export const PROC_STATES = Object.freeze({
  NOT_RUNNING: 'NOT_RUNNING',
  STARTING: 'STARTING',
  HEALTH_CHECKING: 'HEALTH_CHECKING',
  READY: 'READY',
  FAILED: 'FAILED',
  STOPPING: 'STOPPING',
  STOPPED: 'STOPPED',
  RECOVERING: 'RECOVERING',
});

function isElectron() {
  return !!(window.electronAPI && window.electronAPI.isElectron);
}

export class GodsEyeProcessManager {
  constructor(endpoint = GODS_EYE_URL) {
    this.endpoint = endpoint;
    this.state = PROC_STATES.NOT_RUNNING;
    this.endpointResolved = endpoint;
    this.pid = null;
    this.startedByJarvis = false;
    this.lastError = null;
    this.healthChecker = new GodsEyeHealthChecker(endpoint);
    this._listeners = new Set();
    this._healthTimer = null;
  }

  onState(cb) { this._listeners.add(cb); return () => this._listeners.delete(cb); }
  _emit(event, detail) {
    for (const cb of this._listeners) try { cb({ event, state: this.state, detail }); } catch (_) {}
    try { window.dispatchEvent(new CustomEvent('godsEye:diag', { detail: { event, state: this.state, detail } })); } catch (_) {}
  }

  async detect() {
    if (isElectron() && window.electronAPI.godsEye.getRuntime) {
      try {
        const r = await window.electronAPI.godsEye.getRuntime();
        this.state = r.state || PROC_STATES.NOT_RUNNING;
        this.endpointResolved = r.endpoint || this.endpoint;
        this.pid = r.pid || null;
        this.startedByJarvis = !!r.startedByJarvis;
        this.lastError = r.lastError || null;
        this._emit('GODS_EYE_PROCESS_DETECTED', r);
        return r;
      } catch (e) { this.lastError = String(e); }
    }
    const ok = await this.healthChecker.checkOnce(1800);
    this.state = ok ? PROC_STATES.READY : PROC_STATES.NOT_RUNNING;
    this._emit(ok ? 'GODS_EYE_HEALTH_CHECK_PASSED' : 'GODS_EYE_HEALTH_FAILED', { ok });
    return { state: this.state, ok };
  }

  async start() {
    if (this.state === PROC_STATES.STARTING || this.state === PROC_STATES.HEALTH_CHECKING) {
      return { ok: false, error: 'already starting' };
    }
    this.state = PROC_STATES.STARTING;
    this._emit('GODS_EYE_START_REQUESTED', { endpoint: this.endpoint });
    if (isElectron() && window.electronAPI.godsEye.startServer) {
      try {
        const r = await window.electronAPI.godsEye.startServer();
        if (r.ok) {
          this.pid = r.pid || this.pid;
          this.endpointResolved = r.url || this.endpoint;
          this.startedByJarvis = !!r.started || this.startedByJarvis;
          this.state = r.state || PROC_STATES.READY;
          this._emit('GODS_EYE_PROCESS_STARTED', r);
          if (r.alreadyRunning) {
            const hc = await this.healthChecker.checkOnce();
            this.state = hc ? PROC_STATES.READY : PROC_STATES.FAILED;
            this._emit(hc ? 'GODS_EYE_READY' : 'GODS_EYE_START_FAILED', { alreadyRunning: true });
            return { ok: hc, alreadyRunning: true };
          }
          // Wait for health via checker (Electron already polled, but re-verify)
          const poll = await this.healthChecker.pollUntilReady({ maxWaitMs: 45000 });
          this.state = poll.ok ? PROC_STATES.READY : PROC_STATES.FAILED;
          this._emit(poll.ok ? 'GODS_EYE_READY' : 'GODS_EYE_START_FAILED', poll);
          this.lastError = poll.error || null;
          if (poll.ok) this._startLiveMonitor();
          return poll;
        } else {
          this.state = PROC_STATES.FAILED;
          this.lastError = r.error || 'start failed';
          this._emit('GODS_EYE_START_FAILED', r);
          return { ok: false, error: this.lastError, portConflict: !!r.portConflict };
        }
      } catch (e) {
        this.state = PROC_STATES.FAILED;
        this.lastError = String(e);
        this._emit('GODS_EYE_START_FAILED', { error: this.lastError });
        return { ok: false, error: this.lastError };
      }
    }
    // Browser fallback: cannot spawn, just poll for externally started server
    this._emit('GODS_EYE_START_REQUESTED', { browser: true });
    const poll = await this.healthChecker.pollUntilReady({ maxWaitMs: 30000 });
    this.state = poll.ok ? PROC_STATES.READY : PROC_STATES.FAILED;
    this._emit(poll.ok ? 'GODS_EYE_READY' : 'GODS_EYE_START_FAILED', poll);
    return poll;
  }

  async ensureStarted(timeoutMs = 45000) {
    const det = await this.detect();
    if (det && det.ok) return true;
    if (isElectron() && window.electronAPI.godsEye.ensureStarted) {
      try {
        const r = await window.electronAPI.godsEye.ensureStarted({ timeoutMs });
        this.state = r.state || (r.ok ? PROC_STATES.READY : PROC_STATES.FAILED);
        this._emit(r.ok ? 'GODS_EYE_READY' : 'GODS_EYE_START_FAILED', r);
        this.lastError = r.error || null;
        if (r.ok) this._startLiveMonitor();
        return !!r.ok;
      } catch (e) { this.lastError = String(e); }
    }
    const res = await this.start();
    return !!res.ok;
  }

  async healthCheck() {
    const ok = await this.healthChecker.checkOnce();
    if (!ok && this.state === PROC_STATES.READY) {
      this.state = PROC_STATES.RECOVERING;
      this._emit('GODS_EYE_HEALTH_FAILED', { error: this.healthChecker.lastError });
    } else if (ok && this.state !== PROC_STATES.READY) {
      this.state = PROC_STATES.READY;
      this._emit('GODS_EYE_HEALTH_CHECK_PASSED', { latency: this.healthChecker.lastLatency });
    }
    return ok;
  }

  _startLiveMonitor() {
    if (this._healthTimer) clearInterval(this._healthTimer);
    this._healthTimer = setInterval(async () => {
      if (this.state !== PROC_STATES.READY) return;
      const ok = await this.healthChecker.checkOnce(1800);
      if (!ok) {
        this.state = PROC_STATES.RECOVERING;
        this._emit('GODS_EYE_HEALTH_FAILED', { error: this.healthChecker.lastError });
        this._attemptRecovery();
      }
    }, 15000);
    if (this._healthTimer.unref) this._healthTimer.unref();
  }

  async _attemptRecovery() {
    this._emit('GODS_EYE_RECOVERY_STARTED', {});
    const ok = await this.healthChecker.pollUntilReady({ maxWaitMs: 12000 });
    if (ok.ok) {
      this.state = PROC_STATES.READY;
      this._emit('GODS_EYE_RECOVERY_SUCCEEDED', ok);
    } else {
      // Try restart via Electron
      if (isElectron() && window.electronAPI.godsEye.startServer) {
        try {
          const r = await window.electronAPI.godsEye.startServer();
          const poll = await this.healthChecker.pollUntilReady({ maxWaitMs: 20000 });
          this.state = poll.ok ? PROC_STATES.READY : PROC_STATES.FAILED;
          this._emit(poll.ok ? 'GODS_EYE_RECOVERY_SUCCEEDED' : 'GODS_EYE_RECOVERY_FAILED', poll);
        } catch (e) {
          this.state = PROC_STATES.FAILED;
          this._emit('GODS_EYE_RECOVERY_FAILED', { error: String(e) });
        }
      } else {
        this.state = PROC_STATES.FAILED;
        this._emit('GODS_EYE_RECOVERY_FAILED', ok);
      }
    }
  }

  getStatus() {
    return {
      state: this.state,
      endpoint: this.endpointResolved,
      pid: this.pid,
      startedByJarvis: this.startedByJarvis,
      lastError: this.lastError,
      health: { state: this.healthChecker.state, latency: this.healthChecker.lastLatency, error: this.healthChecker.lastError },
    };
  }

  stop() {
    if (this._healthTimer) clearInterval(this._healthTimer);
    this.state = PROC_STATES.STOPPED;
    this._emit('GODS_EYE_STOPPED', {});
  }
}
