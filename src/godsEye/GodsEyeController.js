/**
 * JARVIS GodsEyeController — LifecycleManager + Controller
 * Orchestrates existing God's Eye View (http://localhost:4173) with:
 * - Real HTTP readiness (not process existence)
 * - Holographic loading (no white screen, no ERR_CONNECTION_REFUSED)
 * - Background startup, bounded retry with backoff, single instance, crash recovery
 * - Single source of truth for process/endpoint/readiness/popup state
 */

import { GODS_EYE_URL, GODS_EYE_ORIGIN, GodsEyeConfig } from './GodsEyeConfig.js';
import { GodsEyeHealthChecker } from './GodsEyeHealthChecker.js';
import { GodsEyeProcessManager, PROC_STATES } from './GodsEyeProcessManager.js';

export const STATES = Object.freeze({
  NOT_RUNNING: 'NOT_RUNNING',
  STARTING: 'STARTING',
  HEALTH_CHECKING: 'HEALTH_CHECKING',
  READY: 'READY',
  OPEN: 'OPEN',
  CLOSING: 'CLOSING',
  ERROR: 'ERROR',
  RECOVERING: 'RECOVERING',
  // Compatibility aliases used by HUD
  OFFLINE: 'OFFLINE',
  INITIALIZING: 'INITIALIZING',
  ACTIVE: 'ACTIVE',
  SUSPENDED: 'SUSPENDED',
  DESTROYED: 'DESTROYED',
  UNINITIALIZED: 'UNINITIALIZED',
});

// Phase definitions for holographic loading (real lifecycle milestones)
const PHASES = [
  { id: 'init', label: 'INITIALIZING GOD\'S EYE', progress: 5 },
  { id: 'process', label: 'STARTING LOCAL SERVER', progress: 20 },
  { id: 'detect', label: 'WAITING FOR LOCALHOST', progress: 40 },
  { id: 'health', label: 'SERVER ONLINE', progress: 60 },
  { id: 'connect', label: 'CONNECTING TO VIEWER', progress: 75 },
  { id: 'load', label: 'LOADING ORBITAL VIEW', progress: 90 },
  { id: 'data', label: 'INITIALIZING DATA', progress: 95 },
  { id: 'ready', label: "GOD'S EYE READY", progress: 100 },
];

function isElectron() {
  return !!(window.electronAPI && window.electronAPI.isElectron);
}

function getFallbackUrl() {
  try {
    const port = location.port || (window.__electronPort || '8767');
    return `http://127.0.0.1:${port}/gods-eye-offline.html`;
  } catch (_) { return 'http://127.0.0.1:8767/gods-eye-offline.html'; }
}

// Ensure holographic overlay exists (JARVIS theme)
function createOverlay() {
  if (document.getElementById('jarvis-gods-eye-overlay')) return document.getElementById('jarvis-gods-eye-overlay');
  const overlay = document.createElement('section');
  overlay.id = 'jarvis-gods-eye-overlay';
  overlay.setAttribute('aria-hidden', 'true');
  overlay.innerHTML = `
    <div id="jarvis-gods-eye-panel" role="dialog" aria-modal="true" aria-label="God's Eye">
      <div class="gods-eye-border-trace tl"></div>
      <div class="gods-eye-border-trace br"></div>
      <header class="gods-eye-header">
        <div class="gods-eye-header-left">
          <span class="gods-eye-header-badge">J.A.R.V.I.S. // LVL 5</span>
          <h2 class="glow-text">GOD'S EYE // ORBITAL VIEW</h2>
          <span id="jarvis-gods-eye-status" style="font-family:'Share Tech Mono',monospace; font-size:10px; letter-spacing:2px; color:rgba(0,212,255,0.6);">OFFLINE</span>
        </div>
        <div class="gods-eye-header-right">
          <button id="jarvis-gods-eye-fullscreen" type="button" aria-label="Open in new tab" title="Open in new tab — same browser">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18" aria-hidden="true">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
          </button>
          <button id="jarvis-gods-eye-close" type="button" aria-label="Close God's Eye">X</button>
        </div>
      </header>
      <div class="gods-eye-body">
        <div id="jarvis-gods-eye-viewer">
          <!-- Holographic loading layer (always above iframe/view, prevents white screen) -->
          <div id="jarvis-gods-eye-loading" class="gods-eye-loading-layer">
            <div class="gods-eye-loading-grid"></div>
            <div class="gods-eye-scanline"></div>
            <div class="gods-eye-loading-center">
              <div class="gods-eye-loading-title">J.A.R.V.I.S. // GOD'S EYE</div>
              <div class="gods-eye-loading-subtitle">ORBITAL VIEW INITIALIZATION</div>
              <div class="gods-eye-progress-wrap">
                <div class="gods-eye-progress-track">
                  <div id="gods-eye-progress-bar" class="gods-eye-progress-bar" style="width: 0%"></div>
                </div>
                <div id="gods-eye-progress-text" class="gods-eye-progress-text">0%</div>
              </div>
              <div id="gods-eye-phase" class="gods-eye-phase">INITIALIZING GOD'S EYE</div>
              <div id="gods-eye-phase-detail" class="gods-eye-phase-detail">checking local server…</div>
              <div class="gods-eye-data-pulses">
                <span class="pulse-dot"></span><span class="pulse-dot"></span><span class="pulse-dot"></span>
              </div>
              <div id="gods-eye-system-status" class="gods-eye-system-status">SYSTEM STATUS: INITIALIZING</div>
            </div>
            <div class="gods-eye-corner tl"></div><div class="gods-eye-corner tr"></div><div class="gods-eye-corner bl"></div><div class="gods-eye-corner br"></div>
          </div>
          <div id="jarvis-gods-eye-error" hidden>
            <strong>GOD'S EYE UNAVAILABLE</strong>
            <span id="jarvis-gods-eye-error-detail"></span>
            <div style="display:flex; gap:10px; margin-top:8px;">
              <button id="jarvis-gods-eye-retry" style="background:transparent; border:1px solid #ff6b6b; color:#ff6b6b; padding:8px 16px; font-family:'Share Tech Mono',monospace; cursor:pointer; letter-spacing:2px;">RETRY</button>
              <button id="jarvis-gods-eye-close-error" style="background:transparent; border:1px solid rgba(255,255,255,0.3); color:rgba(255,255,255,0.8); padding:8px 16px; font-family:'Share Tech Mono',monospace; cursor:pointer; letter-spacing:2px;">CLOSE</button>
            </div>
          </div>
          <div class="gods-eye-fallback-globe" id="jarvis-gods-eye-fallback" aria-label="Gods Eye globe" style="display:none;"><span></span><b>GOD'S EYE</b></div>
        </div>
        <aside class="gods-eye-readout">VIEWER <b id="gods-eye-viewer-state">OFFLINE</b> <span id="gods-eye-url" style="opacity:0.6; font-size:9px; margin-left:12px;"></span></aside>
      </div>
      <footer style="padding:8px 16px; border-top:1px solid rgba(0,212,255,0.15); font-family:'Share Tech Mono',monospace; font-size:9px; letter-spacing:1px; color:rgba(0,212,255,0.5);">SOURCE ENGINE: GOD'S EYE VIEW · PUBLIC DATA ONLY</footer>
    </div>
  `;
  return overlay;
}

export class GodsEyeController {
  constructor() {
    this.state = STATES.NOT_RUNNING;
    this.serverState = 'UNKNOWN';
    this.viewState = 'CLOSED';
    this.overlay = null;
    this.viewerEl = null;
    this.lastError = null;
    this.active = false;
    this._boundEscape = (e) => { if (e.key === 'Escape' && this.active) this.close(); };
    this._boundResize = null;
    this.metrics = { startupTime: 0, lastHealthLatency: 0, lastOpenTime: 0 };
    this._isElectron = isElectron();
    this._viewAttached = false;
    this._viewExists = false;
    this._pendingOpen = false;
    this._onGodsEyeEvent = null;
    this._iframe = null;
    this._autoStarted = false;
    this._currentPhase = 0;
    this._progress = 0;
    // Single source of truth via managers
    this.processManager = new GodsEyeProcessManager(GODS_EYE_URL);
    this.healthChecker = new GodsEyeHealthChecker(GODS_EYE_URL);
    this.endpoint = GODS_EYE_URL;
    this.origin = GODS_EYE_ORIGIN;
    // Bind process manager diagnostics to overlay
    this.processManager.onState(({ event, state }) => {
      this._emitDiag(event, state);
    });
    // Background auto-start (non-blocking: HUD ready immediately)
    setTimeout(() => this._autoStartBackground(), 1400);
  }

  // ---- Diagnostic event bus ----
  _emitDiag(event, detail) {
    try { window.dispatchEvent(new CustomEvent('godsEye:diag', { detail: { event, detail, state: this.state } })); } catch (_) {}
    // Also push to HUD diagnostics if available
    try { if (window.__pushDiagnostic) window.__pushDiagnostic('GODS-EYE', `${event}: ${detail||''}`, this.state); } catch (_) {}
    console.log(`[GodsEye][${event}]`, detail || '', 'state', this.state);
  }

  async _autoStartBackground() {
    if (this._autoStarted) return;
    this._autoStarted = true;
    this._emitDiag('GODS_EYE_START_REQUESTED', 'background auto-start');
    this.state = STATES.STARTING;
    this.serverState = 'STARTING';
    this._setPhase(1); // STARTING LOCAL SERVER
    try {
      const ok = await this.processManager.ensureStarted(45000);
      if (ok) {
        this.serverState = 'READY';
        this.state = STATES.READY;
        this.endpoint = this.processManager.endpointResolved || GODS_EYE_URL;
        this._setPhase(3); // SERVER ONLINE
        this._setStatus('READY');
        this._emitDiag('GODS_EYE_READY', this.endpoint);
        try { window.dispatchEvent(new CustomEvent('godsEye:ready', { detail: { endpoint: this.endpoint } })); } catch (_) {}
      } else {
        this.serverState = 'FAILED';
        this.state = STATES.ERROR;
        this.lastError = this.processManager.lastError;
        this._setStatus('ERROR');
        this._emitDiag('GODS_EYE_START_FAILED', this.lastError);
      }
    } catch (e) {
      this.state = STATES.ERROR;
      this.lastError = String(e);
      this._emitDiag('GODS_EYE_START_FAILED', this.lastError);
    }
  }

  _ensureOverlay() {
    if (this.overlay) return;
    this.overlay = createOverlay();
    document.body.appendChild(this.overlay);
    this.viewerEl = this.overlay.querySelector('#jarvis-gods-eye-viewer');
    const closeBtn = this.overlay.querySelector('#jarvis-gods-eye-close');
    const retryBtn = this.overlay.querySelector('#jarvis-gods-eye-retry');
    const closeErrBtn = this.overlay.querySelector('#jarvis-gods-eye-close-error');
    const fsBtn = this.overlay.querySelector('#jarvis-gods-eye-fullscreen');
    if (closeBtn) closeBtn.addEventListener('click', () => this.close());
    if (retryBtn) retryBtn.addEventListener('click', () => this._retry());
    if (closeErrBtn) closeErrBtn.addEventListener('click', () => this.close());
    if (fsBtn) fsBtn.addEventListener('click', () => this.openFullscreen());
    this.overlay.addEventListener('click', (e) => { if (e.target === this.overlay) this.close(); });
    if (this._isElectron && window.electronAPI && window.electronAPI.godsEye) {
      try { this._onGodsEyeEvent = window.electronAPI.godsEye.onEvent((evt) => this._handleElectronEvent(evt)); } catch (e) { console.warn('[GodsEye] electron onEvent failed', e); }
    }
    const urlEl = this.overlay.querySelector('#gods-eye-url');
    if (urlEl) urlEl.textContent = this.endpoint;
  }

  _setStatus(text) {
    if (!this.overlay) return;
    const el = this.overlay.querySelector('#jarvis-gods-eye-status');
    if (el) el.textContent = text || this.state;
    const viewerState = this.overlay.querySelector('#gods-eye-viewer-state');
    if (viewerState) {
      const s = this.serverState === 'READY' ? 'READY' : this.serverState === 'STARTING' ? 'CONNECTING' : this.state;
      viewerState.textContent = s + (this.viewState === 'OPEN' ? ' / OPEN' : '');
    }
  }

  _setPhase(index) {
    if (!this.overlay) return;
    const phase = PHASES[Math.max(0, Math.min(index, PHASES.length - 1))];
    this._currentPhase = index;
    this._progress = phase.progress;
    const phaseEl = this.overlay.querySelector('#gods-eye-phase');
    const detailEl = this.overlay.querySelector('#gods-eye-phase-detail');
    const bar = this.overlay.querySelector('#gods-eye-progress-bar');
    const text = this.overlay.querySelector('#gods-eye-progress-text');
    const sys = this.overlay.querySelector('#gods-eye-system-status');
    if (phaseEl) phaseEl.textContent = phase.label;
    if (bar) bar.style.width = phase.progress + '%';
    if (text) text.textContent = phase.progress + '%';
    if (sys) sys.textContent = `SYSTEM STATUS: ${phase.label}`;
    if (detailEl) {
      const details = [
        'resolving endpoint…',
        'launching vite server…',
        'probing localhost:'+GodsEyeConfig.port+'…',
        'http health check…',
        'attaching orbital viewer…',
        'loading cesium globe…',
        'syncing data layers…',
        'orbital view online',
      ];
      detailEl.textContent = details[index] || '';
    }
  }

  _showLoading(show) {
    if (!this.overlay) return;
    const l = this.overlay.querySelector('#jarvis-gods-eye-loading');
    const e = this.overlay.querySelector('#jarvis-gods-eye-error');
    if (l) l.style.display = show ? 'grid' : 'none';
    if (show && e) e.hidden = true;
  }

  _setError(title, detail) {
    if (!this.overlay) return;
    const l = this.overlay.querySelector('#jarvis-gods-eye-loading');
    const e = this.overlay.querySelector('#jarvis-gods-eye-error');
    const d = this.overlay.querySelector('#jarvis-gods-eye-error-detail');
    if (l) l.style.display = 'none';
    if (e) e.hidden = false;
    if (d) d.textContent = detail || title || 'Unknown error';
    this.lastError = new Error(detail || title);
  }

  _handleElectronEvent(evt) {
    if (!evt || !evt.type) return;
    switch (evt.type) {
      case 'diagnostic':
        // Mirror main diagnostic to overlay detail
        if (evt.event === 'GODS_EYE_HEALTH_CHECK_PASSED') this._setPhase(3);
        if (evt.event === 'GODS_EYE_READY') { this._setPhase(7); this._setStatus('READY'); }
        if (evt.event === 'GODS_EYE_PORT_CONFLICT') this._setPhase(2);
        break;
      case 'did-start-navigation':
        this._setPhase(4);
        break;
      case 'did-finish-load':
        // Transition smoothly: loading overlay fades, real view revealed
        this._setPhase(7);
        this._emitDiag('GODS_EYE_VIEWER_READY', evt.url);
        setTimeout(() => {
          this._showLoading(false);
          const viewer = this.viewerEl;
          if (viewer) viewer.classList.add('has-view');
          // Crossfade: loading layer fades out
          const layer = this.overlay && this.overlay.querySelector('#jarvis-gods-eye-loading');
          if (layer) { layer.style.transition = 'opacity 0.45s ease'; layer.style.opacity = '0'; setTimeout(()=>{ if(layer.style.opacity==='0') layer.style.display='none'; layer.style.opacity='1'; }, 500); }
        }, 350);
        this.state = STATES.READY;
        this.serverState = 'READY';
        this._setStatus('READY');
        break;
      case 'did-fail-load':
        if (evt.isMainFrame !== false) {
          this.state = STATES.ERROR;
          this._setError("GOD'S EYE STARTUP FAILED", `Load failed: ${evt.desc} (${evt.code}) ${evt.url}`);
          this._emitDiag('GODS_EYE_HEALTH_FAILED', `${evt.desc} ${evt.code}`);
        }
        break;
      case 'render-process-gone':
        this.state = STATES.ERROR;
        this._setError("GOD'S EYE CRASHED", evt.details ? evt.details.reason : 'render gone');
        this._emitDiag('GODS_EYE_PROCESS_EXITED', evt.details?.reason);
        break;
      case 'health-ready':
        this._setPhase(3);
        break;
      case 'health-failed':
        this.state = STATES.RECOVERING;
        this._setPhase(2);
        this._emitDiag('GODS_EYE_HEALTH_FAILED', evt.error);
        break;
      case 'recovery-succeeded':
        this.state = STATES.READY;
        this._setPhase(7);
        this._setStatus('READY');
        break;
      case 'window-resize':
        this._updateBounds();
        break;
      default: break;
    }
  }

  _computeBounds() {
    if (!this.viewerEl || !this.overlay || !this.overlay.classList.contains('visible')) return null;
    const r = this.viewerEl.getBoundingClientRect();
    return { x: Math.round(r.left), y: Math.round(r.top), width: Math.round(r.width), height: Math.round(r.height) };
  }

  async _updateBounds() {
    if (!this._isElectron || !this._viewAttached) return;
    const b = this._computeBounds();
    if (!b || b.width < 50 || b.height < 50) return;
    try { await window.electronAPI.godsEye.setBounds(b); } catch (e) { console.warn('[GodsEye] setBounds failed', e); }
  }

  async healthCheck() {
    const ok = await this.healthChecker.checkOnce();
    this.metrics.lastHealthLatency = this.healthChecker.lastLatency;
    this.serverState = ok ? 'READY' : 'OFFLINE';
    return ok;
  }

  async _ensureServer(timeoutMs = 45000) {
    // Duplicate protection: detect before spawn
    this._setPhase(2);
    this.state = STATES.STARTING;
    this._setStatus('STARTING');
    this._showLoading(true);
    const ok = await this.processManager.ensureStarted(timeoutMs);
    if (ok) {
      this.endpoint = this.processManager.endpointResolved || GODS_EYE_URL;
      this.serverState = 'READY';
      this.state = STATES.READY;
      this._setPhase(3);
      this._setStatus('READY');
      const urlEl = this.overlay && this.overlay.querySelector('#gods-eye-url');
      if (urlEl) urlEl.textContent = this.endpoint;
      this._emitDiag('GODS_EYE_READY', this.endpoint);
      return true;
    }
    this.serverState = 'FAILED';
    this.state = STATES.ERROR;
    const err = this.processManager.lastError || 'health timeout';
    const isConflict = err.includes('PORT CONFLICT');
    const msg = isConflict ? `PORT CONFLICT: ${GodsEyeConfig.port} occupied by another process. Close it or set GODS_EYE_PORT.` : `Not reachable at ${this.endpoint} after ${timeoutMs/1000}s. ${err.slice(0,120)}`;
    this._setError("GOD'S EYE STARTUP FAILED", msg);
    this._emitDiag('GODS_EYE_START_FAILED', msg);
    return false;
  }

  async initialize(force = false) {
    this._ensureOverlay();
    if (!force && (this.state === STATES.READY || this.state === STATES.OPEN)) {
      const ok = await this.healthCheck();
      if (ok) return true;
    }
    this.state = STATES.INITIALIZING;
    this._setStatus('INITIALIZING');
    this._setPhase(0);
    this._showLoading(true);
    const ok = await this._ensureServer();
    return ok;
  }

  // ---- Public API (spec: ensureStarted, ensureReady, getEndpoint, open, close, openFullscreen, stop) ----
  async ensureStarted() { return this._ensureServer(45000); }
  async ensureReady(timeoutMs=45000) { return this._ensureServer(timeoutMs); }
  getEndpoint() { return this.endpoint; }
  getStatus() {
    return {
      state: this.state,
      serverState: this.serverState,
      viewState: this.viewState,
      active: this.active,
      url: this.endpoint,
      endpoint: this.endpoint,
      error: this.lastError ? this.lastError.message : null,
      metrics: this.metrics,
      proc: this.processManager.getStatus(),
    };
  }

  async open() {
    this._ensureOverlay();
    if (this.active && this.viewState === 'OPEN') {
      this._updateBounds();
      this._emitDiag('GODS_EYE_OPENED', 'already open, reuse');
      return true;
    }
    this.active = true;
    this.viewState = 'OPEN';
    this.overlay.classList.add('visible');
    this.overlay.setAttribute('aria-hidden', 'false');
    document.addEventListener('keydown', this._boundEscape, true);
    this.state = STATES.OPEN;
    this._setStatus('OPENING');
    this._showLoading(true);
    this._setPhase(0);
    this._emitDiag('GODS_EYE_OPENED', 'popup opening');

    // Ensure server ready (real HTTP) before exposing iframe/view
    const ready = await this.initialize();
    if (!ready) {
      // Keep holographic error layer visible, do NOT show white screen or ERR_CONNECTION_REFUSED
      this._emitDiag('GODS_EYE_START_FAILED', this.lastError?.message);
      return false;
    }

    // Now embed — loading layer stays above until did-finish-load hides it
    if (this._isElectron) {
      try {
        if (!this._viewExists) {
          const cr = await window.electronAPI.godsEye.create();
          this._viewExists = !!cr.exists;
        }
        await new Promise(r => setTimeout(r, 420)); // let overlay transition
        let b = this._computeBounds();
        if (!b || b.width < 50) { await new Promise(r => setTimeout(r, 200)); b = this._computeBounds(); }
        this._setPhase(4); // CONNECTING TO VIEWER
        // Pre-load correct URL (ensures no ERR_CONNECTION_REFUSED visible)
        try { await window.electronAPI.godsEye.load(this.endpoint); } catch(_){}
        const res = await window.electronAPI.godsEye.show(b);
        this._viewAttached = true;
        this._setPhase(5); // LOADING ORBITAL VIEW
        setTimeout(() => this._updateBounds(), 80);
        setTimeout(() => this._updateBounds(), 250);
        window.addEventListener('resize', this._boundResize || (this._boundResize = () => this._updateBounds()));
        this.metrics.lastOpenTime = Date.now();
        this._emitDiag('GODS_EYE_OPENED', 'WebContentsView attached');
        // Viewer will hide loading on did-finish-load event; fallback hide after 8s
        setTimeout(() => {
          if (this.viewState === 'OPEN' && this.overlay && this.overlay.querySelector('#jarvis-gods-eye-loading')?.style.display !== 'none') {
            this._setPhase(6);
          }
        }, 2000);
        return true;
      } catch (e) {
        this._setError("GOD'S EYE EMBED FAILED", String(e).slice(0,200));
        this.state = STATES.ERROR;
        this._emitDiag('GODS_EYE_START_FAILED', String(e));
        return false;
      }
    } else {
      // Browser fallback: iframe with holographic layer above until load
      try {
        if (this._iframe) { this._iframe.remove(); this._iframe = null; }
        this._setPhase(4);
        const iframe = document.createElement('iframe');
        iframe.src = this.endpoint;
        iframe.style.cssText = 'position:absolute; inset:0; width:100%; height:100%; border:none; background:#000; opacity:0; transition: opacity 0.45s ease;';
        iframe.setAttribute('allow', 'fullscreen');
        let loadTimer = setTimeout(() => {
          this._setError("GOD'S EYE STARTUP FAILED", `Viewer did not load at ${this.endpoint} within 12s`);
        }, 12000);
        iframe.onload = () => {
          clearTimeout(loadTimer);
          this._setPhase(6);
          // Smooth crossfade from holographic loading to real globe
          this._showLoading(false);
          setTimeout(() => { iframe.style.opacity = '1'; this.viewerEl.classList.add('has-view'); }, 100);
          this.state = STATES.READY;
          this._setStatus('READY');
          this._emitDiag('GODS_EYE_READY', 'iframe loaded');
        };
        iframe.onerror = () => {
          clearTimeout(loadTimer);
          this._setError("GOD'S EYE LOAD FAILED", `Cannot load ${this.endpoint}`);
          this._emitDiag('GODS_EYE_START_FAILED', 'iframe error');
        };
        this.viewerEl.appendChild(iframe);
        this._iframe = iframe;
        // Keep loading visible for at least 600ms so user sees holographic transition, not white flash
        this._showLoading(true);
        this._setPhase(5);
        return true;
      } catch (e) {
        this._setError("GOD'S EYE EMBED FAILED", String(e));
        return false;
      }
    }
  }

  close() {
    if (!this.overlay || !this.active) return;
    this.active = false;
    this.viewState = 'CLOSED';
    this.state = STATES.CLOSING;
    this._setStatus('CLOSING');
    this._emitDiag('GODS_EYE_CLOSED', 'popup closing');
    this.overlay.classList.remove('visible');
    this.overlay.setAttribute('aria-hidden', 'true');
    document.removeEventListener('keydown', this._boundEscape, true);
    if (this._boundResize) window.removeEventListener('resize', this._boundResize);
    if (this._isElectron && this._viewAttached) {
      try { window.electronAPI.godsEye.hide(); this._viewAttached = false; const v = this.viewerEl; if(v) v.classList.remove('has-view'); } catch(e){ console.warn('[GodsEye] hide failed',e); }
      // Keep server alive for fast reopen (do NOT kill)
    } else {
      // Browser: keep iframe for fast reopen, just hide overlay (do not destroy view)
      // Reset iframe opacity so next open crossfades again
      if (this._iframe) this._iframe.style.opacity = '0';
    }
    this.state = STATES.READY;
    this.serverState = 'READY';
    this._setStatus('READY');
    try { document.getElementById('jarvis-radar')?.focus(); } catch(_){}
  }

  toggle() { return this.active ? this.close() : this.open(); }

  async openFullscreen() {
    const url = this.endpoint;
    this._emitDiag('GODS_EYE_FULLSCREEN', url);
    // Must wait for real readiness
    if (this.serverState !== 'READY') {
      this._setPhase(2);
      const ready = await this._ensureServer(30000);
      if (!ready) {
        this._setError("GOD'S EYE NOT READY", 'Cannot open fullscreen — server not reachable');
        return false;
      }
    }
    try {
      if (this._isElectron && window.electronAPI.godsEye.openExternal) {
        await window.electronAPI.godsEye.openExternal(url);
        return true;
      }
      const win = window.open(url, '_blank', 'noopener');
      if (win) return true;
      window.location.href = url;
      return true;
    } catch (e) {
      try { window.open(url, '_blank'); } catch(_){}
      return false;
    }
  }

  stop() {
    this.processManager.stop();
    this.state = STATES.NOT_RUNNING;
    this.serverState = 'STOPPED';
    this._setStatus('OFFLINE');
  }

  _retry() {
    this.state = STATES.RECOVERING;
    this._showLoading(true);
    this._setPhase(1);
    this._setStatus('RECOVERING');
    this._emitDiag('GODS_EYE_RECOVERY_STARTED', 'retry clicked');
    setTimeout(() => this.open(), 300);
  }

  execute(action = {}) {
    if (action.type === 'open' || action.type === 'show') return this.open();
    if (action.type === 'close') { this.close(); return true; }
    if (action.type === 'fullscreen') return this.openFullscreen();
    return false;
  }
}

export { STATES as GODS_EYE_STATES };
export const GodsEyeLifecycleManager = GodsEyeController;
