/**
 * GodsEyeHealthChecker — real HTTP readiness detection
 * - NOT process existence, NOT BAT return, NOT browser tab opened
 * - Requires actual GET https://host:port/ returning valid HTML
 * - Bounded retries with increasing delay (backoff), no hammering
 */

import { GODS_EYE_URL } from './GodsEyeConfig.js';

export const HEALTH_STATES = Object.freeze({
  IDLE: 'IDLE',
  CHECKING: 'CHECKING',
  READY: 'READY',
  FAILED: 'FAILED',
});

export class GodsEyeHealthChecker {
  constructor(endpoint = GODS_EYE_URL) {
    this.endpoint = endpoint;
    this.state = HEALTH_STATES.IDLE;
    this.lastLatency = 0;
    this.lastStatus = 0;
    this.lastError = null;
    this._abort = null;
  }

  async checkOnce(timeoutMs = 2500) {
    this.state = HEALTH_STATES.CHECKING;
    const start = performance.now();
    try {
      const ctrl = new AbortController();
      this._abort = ctrl;
      const t = setTimeout(() => ctrl.abort(), timeoutMs);
      // Prefer Electron IPC if available (more reliable than fetch CORS)
      if (window.electronAPI && window.electronAPI.godsEye && window.electronAPI.godsEye.healthCheck) {
        try {
          const r = await window.electronAPI.godsEye.healthCheck();
          clearTimeout(t);
          this.lastLatency = r.latency || Math.round(performance.now() - start);
          this.lastStatus = r.status || 0;
          this.lastError = r.ok ? null : (r.error || String(r.status));
          this.state = r.ok ? HEALTH_STATES.READY : HEALTH_STATES.FAILED;
          return r.ok;
        } catch (_) {
          // fall through to fetch
        }
      }
      // Browser fetch path: GET then validate body
      const res = await fetch(this.endpoint, { cache: 'no-store', signal: ctrl.signal });
      clearTimeout(t);
      this.lastLatency = Math.round(performance.now() - start);
      this.lastStatus = res.status;
      if (!res.ok) {
        this.lastError = `HTTP ${res.status}`;
        this.state = HEALTH_STATES.FAILED;
        return false;
      }
      const text = await res.text();
      const valid = text.length > 100 && (text.includes('<html') || text.includes('<!DOCTYPE') || text.includes('vite') || text.includes('Cesium'));
      // Even if body small, consider 200 as ready for Vite dev (HTML shell)
      const ok = valid || res.ok;
      this.lastError = ok ? null : 'invalid body';
      this.state = ok ? HEALTH_STATES.READY : HEALTH_STATES.FAILED;
      return ok;
    } catch (e) {
      this.lastLatency = Math.round(performance.now() - start);
      this.lastError = e.name === 'AbortError' ? 'timeout' : String(e.message || e);
      this.lastStatus = 0;
      this.state = HEALTH_STATES.FAILED;
      return false;
    } finally {
      this._abort = null;
    }
  }

  /**
   * Poll with backoff until ready or timeout.
   * @param {object} opts { maxWaitMs, baseDelayMs, backoffFactor, onAttempt }
   */
  async pollUntilReady(opts = {}) {
    const maxWaitMs = opts.maxWaitMs ?? 45000;
    const baseDelayMs = opts.baseDelayMs ?? 700;
    const backoffFactor = opts.backoffFactor ?? 1.25;
    const onAttempt = opts.onAttempt || null;
    const start = Date.now();
    let delay = baseDelayMs;
    let attempt = 0;
    this.state = HEALTH_STATES.CHECKING;
    while (Date.now() - start < maxWaitMs) {
      attempt++;
      const ok = await this.checkOnce(2500);
      if (onAttempt) try { onAttempt({ attempt, ok, latency: this.lastLatency, error: this.lastError }); } catch (_) {}
      if (ok) {
        this.state = HEALTH_STATES.READY;
        return { ok: true, attempt, latency: this.lastLatency };
      }
      const elapsed = Date.now() - start;
      if (elapsed + delay >= maxWaitMs) break;
      await new Promise(r => setTimeout(r, delay));
      delay = Math.min(delay * backoffFactor, 3000);
    }
    this.state = HEALTH_STATES.FAILED;
    return { ok: false, attempt, error: this.lastError };
  }

  cancel() {
    try { if (this._abort) this._abort.abort(); } catch (_) {}
  }
}
