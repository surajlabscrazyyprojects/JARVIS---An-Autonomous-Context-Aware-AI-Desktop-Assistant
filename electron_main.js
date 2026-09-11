/**
 * JARVIS Electron Main — proper embedded Chromium view via WebContentsView
 *
 * - Uses current WebContentsView API (not deprecated BrowserView / webview)
 * - One single WebContentsView for https://spideytracker.net/intl/in/
 * - Isolated: nodeIntegration false, contextIsolation true, sandbox true, webSecurity true
 * - No CSP disabling, no unsafe flags, no script injection
 * - Bounds exactly match the holographic popup inner content area
 * - Handles did-start-navigation / did-finish-load / did-fail-load / render-process-gone / destroyed
 * - Keeps main HUD, voice, camera, God's Eye fully independent
 * - GodsEye orchestration: background startup, real HTTP readiness, holographic loading, no white screen
 */

const { app, BrowserWindow, WebContentsView, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const url = require('url');
const { spawn } = require('child_process');

const ROOT = __dirname;
const SPIDEY_URL = 'https://spideytracker.net/intl/in/';
const SPIDEY_ORIGIN = 'https://spideytracker.net';

// ---- GodsEye Config Discovery ----
function resolveGodsEyeConfig() {
  let port = 4173;
  try {
    if (process.env.GODS_EYE_PORT) port = parseInt(process.env.GODS_EYE_PORT, 10) || 4173;
    else if (process.env.VITE_GODS_EYE_URL) {
      const u = new URL(process.env.VITE_GODS_EYE_URL);
      if (u.port) port = parseInt(u.port, 10) || 4173;
    } else if (process.env.PORT) {
      const gevEnvPath = path.join(ROOT, 'gods-eye-view', '.env');
      if (fs.existsSync(gevEnvPath)) {
        const envText = fs.readFileSync(gevEnvPath, 'utf8');
        if (/PORT\s*=/.test(envText)) port = parseInt(process.env.PORT, 10) || 4173;
      }
    }
  } catch (_) {}
  if (!Number.isFinite(port) || port < 1024 || port > 65535) port = 4173;
  const host = (process.env.GODS_EYE_HOST || process.env.HOST || 'localhost').includes('0.0.0.0') ? 'localhost' : 'localhost';
  const urlStr = 'http://' + host + ':' + port + '/';
  const origin = 'http://' + host + ':' + port;
  return { port, host, url: urlStr, origin, viteDir: path.join(ROOT, 'gods-eye-view') };
}
const _gevCfg = resolveGodsEyeConfig();
const GODSEYE_URL = _gevCfg.url;
const GODSEYE_ORIGIN = _gevCfg.origin;
const GODSEYE_PORT = _gevCfg.port;
const GODSEYE_HOST = _gevCfg.host;
console.log('[GodsEye] resolved endpoint', GODSEYE_URL, 'origin', GODSEYE_ORIGIN);

let mainWindow = null;
let spideyView = null;
let spideyAttached = false;
let spideyLastUrl = null;
let spideyLastBounds = null;
let godsEyeView = null;
let godsEyeAttached = false;
let godsEyeLastUrl = null;
let godsEyeLastBounds = null;
let httpServer = null;
let httpPort = null;
let backendProc = null;

// ---- Windows unicode path helper (OneDrive Japanese etc) ----
function getShortPathSync(longPath) {
  try {
    if (process.platform !== 'win32') return longPath;
    if (!longPath || !fs.existsSync(longPath)) return longPath;
    const { execSync } = require('child_process');
    // Use cmd to resolve 8.3 short path (ASCII) to avoid EINVAL on unicode cwd
    const out = execSync(`for %A in ("${longPath.replace(/"/g, '""')}") do @echo %~sA`, { encoding: 'utf8', shell: 'cmd.exe' }).trim().split(/\r?\n/).pop().trim();
    if (out && out.length > 3 && !out.includes('%')) return out;
  } catch (_) {}
  return longPath;
}

// ---- GodsEye Runtime Manager (single source of truth) ----
const GodsEyeRuntime = {
  state: 'NOT_RUNNING',
  endpoint: GODSEYE_URL,
  port: GODSEYE_PORT,
  host: GODSEYE_HOST,
  origin: GODSEYE_ORIGIN,
  pid: null,
  proc: null,
  startedByJarvis: false,
  lastError: null,
  lastHealthAt: 0,
  healthLatencyMs: 0,
  startupAttempts: 0,
  maxStartupAttempts: 3,
  recoveryAttempts: 0,
  diagnostics: [],
};

function pushGodsEyeDiag(event, detail, state) {
  const entry = { ts: new Date().toISOString(), event, detail: String(detail||'').slice(0,500), state: state||GodsEyeRuntime.state };
  GodsEyeRuntime.diagnostics.push(entry);
  if (GodsEyeRuntime.diagnostics.length > 120) GodsEyeRuntime.diagnostics.shift();
  console.log('[GodsEye][diag]', event, detail||'', '->', state||GodsEyeRuntime.state);
  try { if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('godsEye:event', { type: 'diagnostic', event, detail, state: GodsEyeRuntime.state, endpoint: GodsEyeRuntime.endpoint }); } catch(_){}
  try { if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('godsEye:diag', entry); } catch(_){}
}

function emitGodsEyeEvent(type, payload) {
  try { if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('godsEye:event', { type, ...payload }); } catch(_){}
}

function socketProbe(port, host, timeoutMs) {
  return new Promise((res)=>{
    const net = require('net');
    const s = new net.Socket();
    let done=false;
    const to=setTimeout(()=>{ if(!done){done=true; try{s.destroy();}catch(_){} res(false); }}, timeoutMs);
    s.setTimeout(timeoutMs);
    s.on('connect',()=>{ if(!done){done=true; clearTimeout(to); s.destroy(); res(true); }});
    s.on('error',()=>{ if(!done){done=true; clearTimeout(to); try{s.destroy();}catch(_){} res(false); }});
    s.on('timeout',()=>{ if(!done){done=true; try{s.destroy();}catch(_){} clearTimeout(to); res(false); }});
    try{ s.connect(port, host); }catch(_){ if(!done){done=true; clearTimeout(to); res(false);} }
  });
}

function httpHealthCheck(endpoint, timeoutMs) {
  return new Promise((resolve)=>{
    const start = Date.now();
    const parsed = new URL(endpoint);
    const opts = { hostname: parsed.hostname, port: parsed.port, path: parsed.pathname, method: 'GET', timeout: timeoutMs, headers: { 'Cache-Control': 'no-store' } };
    const req = http.request(opts, (res)=>{
      let body='';
      res.on('data', c=>{ body+=c.toString(); if(body.length>8192) { req.destroy(); }});
      res.on('end',()=>{
        const latency = Date.now()-start;
        GodsEyeRuntime.healthLatencyMs = latency;
        GodsEyeRuntime.lastHealthAt = Date.now();
        const ok = res.statusCode>=200 && res.statusCode<400;
        const validBody = ok && body.length>50;
        resolve({ ok: ok && validBody, status: res.statusCode, latency, bodyLen: body.length, headers: res.headers });
      });
    });
    req.on('error',(e)=>{ resolve({ ok:false, error: String(e.message||e), status: 0 }); });
    req.setTimeout(timeoutMs, ()=>{ req.destroy(); resolve({ ok:false, error: 'timeout', status: 0 }); });
    req.end();
  });
}

async function checkGodsEyeReady(timeoutMs){
  const r = await httpHealthCheck(GodsEyeRuntime.endpoint, timeoutMs||2500);
  if(r.ok){ if(GodsEyeRuntime.state==='STARTING' || GodsEyeRuntime.state==='HEALTH_CHECKING') GodsEyeRuntime.state='READY'; return true; }
  return false;
}

async function pollGodsEyeHealth(opts){
  const maxWaitMs = opts.maxWaitMs;
  const baseDelayMs = opts.baseDelayMs||600;
  const backoffFactor = opts.backoffFactor||1.25;
  const start = Date.now();
  let delay = baseDelayMs;
  let attempt=0;
  GodsEyeRuntime.state='HEALTH_CHECKING';
  pushGodsEyeDiag('GODS_EYE_HEALTH_CHECK_STARTED', 'polling '+GodsEyeRuntime.endpoint, 'HEALTH_CHECKING');
  while(Date.now()-start < maxWaitMs){
    attempt++;
    const hc = await httpHealthCheck(GodsEyeRuntime.endpoint, 2000);
    if(hc.ok){
      GodsEyeRuntime.state='READY';
      pushGodsEyeDiag('GODS_EYE_HEALTH_CHECK_PASSED', 'ok '+hc.status+' latency '+hc.latency+'ms', 'READY');
      emitGodsEyeEvent('health-ready', { url: GodsEyeRuntime.endpoint, latency: hc.latency });
      scheduleHealthMonitor();
      return { ok:true, attempt, latency: hc.latency };
    }
    if(attempt % 3 === 0){
      const sock = await socketProbe(GodsEyeRuntime.port, 'localhost', 800);
      if(sock && !hc.ok){
        pushGodsEyeDiag('GODS_EYE_PORT_CONFLICT','port '+GodsEyeRuntime.port+' socket open but http not ready status '+hc.status, 'HEALTH_CHECKING');
      }
    }
    const elapsed = Date.now()-start;
    if(elapsed + delay >= maxWaitMs) break;
    await new Promise(r=>setTimeout(r, delay));
    delay = Math.min(delay * backoffFactor, 3000);
  }
  return { ok:false, attempt };
}

let _healthMonitorTimer=null;
function scheduleHealthMonitor(){
  if(_healthMonitorTimer) clearInterval(_healthMonitorTimer);
  _healthMonitorTimer = setInterval(async ()=>{
    if(GodsEyeRuntime.state!=='READY') return;
    const hc = await httpHealthCheck(GodsEyeRuntime.endpoint, 1800);
    if(!hc.ok){
      pushGodsEyeDiag('GODS_EYE_HEALTH_FAILED','periodic check failed status '+hc.status+' '+ (hc.error||''), 'RECOVERING');
      GodsEyeRuntime.state='RECOVERING';
      emitGodsEyeEvent('health-failed', { error: hc.error||String(hc.status) });
      attemptGodsEyeRecovery();
    }
  }, 15000);
  if(_healthMonitorTimer.unref) _healthMonitorTimer.unref();
}

async function attemptGodsEyeRecovery(){
  if(GodsEyeRuntime.recoveryAttempts >= 2){
    pushGodsEyeDiag('GODS_EYE_RECOVERY_FAILED','max recovery attempts reached', 'FAILED');
    GodsEyeRuntime.state='FAILED';
    return;
  }
  GodsEyeRuntime.recoveryAttempts++;
  pushGodsEyeDiag('GODS_EYE_RECOVERY_STARTED','attempt '+GodsEyeRuntime.recoveryAttempts, 'RECOVERING');
  const alive = GodsEyeRuntime.proc && !GodsEyeRuntime.proc.killed && GodsEyeRuntime.proc.exitCode===null;
  if(!alive && GodsEyeRuntime.startedByJarvis){
    const ok = await startGodsEyeServerInternal({ force:true, reason:'recovery' });
    if(ok){
      pushGodsEyeDiag('GODS_EYE_RECOVERY_SUCCEEDED','restart succeeded', 'READY');
      GodsEyeRuntime.state='READY';
      GodsEyeRuntime.recoveryAttempts=0;
      emitGodsEyeEvent('recovery-succeeded', { endpoint: GodsEyeRuntime.endpoint });
    } else {
      pushGodsEyeDiag('GODS_EYE_RECOVERY_FAILED','restart failed', 'FAILED');
      GodsEyeRuntime.state='FAILED';
    }
  } else {
    const res = await pollGodsEyeHealth({ maxWaitMs: 10000, baseDelayMs: 700, backoffFactor: 1.3 });
    if(res.ok){
      pushGodsEyeDiag('GODS_EYE_RECOVERY_SUCCEEDED','http recovered', 'READY');
      GodsEyeRuntime.state='READY';
      GodsEyeRuntime.recoveryAttempts=0;
    } else {
      pushGodsEyeDiag('GODS_EYE_RECOVERY_FAILED','http still failing', 'FAILED');
      GodsEyeRuntime.state='FAILED';
    }
  }
}

async function startGodsEyeServerInternal(opts){
  const force = opts && opts.force;
  const reason = opts && opts.reason;
  const alreadyReady = await checkGodsEyeReady(1800);
  if(alreadyReady && !force){
    pushGodsEyeDiag('GODS_EYE_PROCESS_DETECTED','already healthy at '+GodsEyeRuntime.endpoint, 'READY');
    GodsEyeRuntime.state='READY';
    return true;
  }
  const sockOpen = await socketProbe(GodsEyeRuntime.port, 'localhost', 800);
  if(sockOpen && !alreadyReady){
    pushGodsEyeDiag('GODS_EYE_PORT_CONFLICT','port '+GodsEyeRuntime.port+' occupied by non-ready process', GodsEyeRuntime.state);
    const poll = await pollGodsEyeHealth({ maxWaitMs: 8000, baseDelayMs: 600 });
    if(poll.ok){ GodsEyeRuntime.state='READY'; return true; }
    GodsEyeRuntime.lastError='PORT CONFLICT: '+GodsEyeRuntime.port+' occupied but not serving GodsEye';
    return false;
  }
  if(sockOpen && alreadyReady){
    GodsEyeRuntime.state='READY';
    return true;
  }
  if(GodsEyeRuntime.proc && !GodsEyeRuntime.proc.killed && !force){
    pushGodsEyeDiag('GODS_EYE_START_REQUESTED','already starting pid '+GodsEyeRuntime.pid, GodsEyeRuntime.state);
    return false;
  }
  const godsEyeDir = _gevCfg.viteDir;
  const batPath = path.join(godsEyeDir, 'START_GODS_EYE_VIEW.bat');
  const pkgPath = path.join(godsEyeDir, 'package.json');
  if(!fs.existsSync(pkgPath)){
    GodsEyeRuntime.lastError='gods-eye-view/package.json not found at '+pkgPath;
    pushGodsEyeDiag('GODS_EYE_START_FAILED', GodsEyeRuntime.lastError, 'FAILED');
    GodsEyeRuntime.state='FAILED';
    return false;
  }
  GodsEyeRuntime.state='STARTING';
  GodsEyeRuntime.startupAttempts++;
  pushGodsEyeDiag('GODS_EYE_START_REQUESTED', (reason||'auto')+' spawning npm run dev in '+godsEyeDir+' attempt '+GodsEyeRuntime.startupAttempts, 'STARTING');
  if(GodsEyeRuntime.startupAttempts > GodsEyeRuntime.maxStartupAttempts){
    GodsEyeRuntime.lastError='max startup attempts exceeded';
    pushGodsEyeDiag('GODS_EYE_START_FAILED', GodsEyeRuntime.lastError, 'FAILED');
    GodsEyeRuntime.state='FAILED';
    return false;
  }
  const logDir = path.join(ROOT, 'logs');
  try{ fs.mkdirSync(logDir, { recursive:true }); }catch(_){}
  const logFile = path.join(logDir, 'gods-eye-electron.log');
  // Use long unicode path for cwd (preserves Vite fs.allow), but spawn via cmd.exe to avoid EINVAL on npm.cmd
  // Verified: spawn('npm.cmd', ..., {cwd: unicode, shell:false}) => EINVAL, but spawn('cmd.exe', ..., {cwd: unicode}) => OK
  const out = fs.openSync(logFile, 'a');
  let proc=null;
  try{
    const env = { ...process.env, PORT: String(GodsEyeRuntime.port), GODS_EYE_PORT: String(GodsEyeRuntime.port), HOST: String(GodsEyeRuntime.host) };
    try {
      // Primary: cmd.exe /d /s /c "npm run dev" with long unicode cwd (avoids Vite 403 from short path)
      proc = spawn('cmd.exe', ['/d', '/s', '/c', 'npm run dev'], { cwd: godsEyeDir, detached: false, stdio: ['ignore', out, out], windowsHide: true, env, shell: false });
    } catch (e1) {
      try{ if(proc && !proc.killed) try{proc.kill();}catch(_){} }catch(_){}
      pushGodsEyeDiag('GODS_EYE_SPAWN_RETRY', 'cmd.exe spawn failed: '+String(e1)+' retrying with shell:true npm.cmd', 'STARTING');
      // Fallback: shell:true with npm.cmd and short path (if long still fails)
      const shortCwd = getShortPathSync(godsEyeDir);
      const npmCmd = process.platform==='win32' ? 'npm.cmd' : 'npm';
      proc = spawn(npmCmd, ['run','dev'], { cwd: shortCwd, detached: false, stdio: ['ignore', out, out], windowsHide: true, env, shell: true });
    }
  }catch(e){
    try{ fs.closeSync(out);}catch(_){}
    GodsEyeRuntime.lastError='spawn failed: '+String(e)+' cwd='+godsEyeDir;
    pushGodsEyeDiag('GODS_EYE_START_FAILED', GodsEyeRuntime.lastError, 'FAILED');
    GodsEyeRuntime.state='FAILED';
    return false;
  }
  if (!proc || !proc.pid) {
    try{ fs.closeSync(out);}catch(_){}
    GodsEyeRuntime.lastError='spawn failed: no pid (EINVAL likely, cwd='+godsEyeDir+')';
    pushGodsEyeDiag('GODS_EYE_START_FAILED', GodsEyeRuntime.lastError, 'FAILED');
    GodsEyeRuntime.state='FAILED';
    return false;
  }
  GodsEyeRuntime.proc = proc;
  GodsEyeRuntime.pid = proc.pid;
  GodsEyeRuntime.startedByJarvis = true;
  pushGodsEyeDiag('GODS_EYE_PROCESS_STARTED','pid '+proc.pid+' log '+logFile, 'STARTING');
  emitGodsEyeEvent('process-started', { pid: proc.pid, endpoint: GodsEyeRuntime.endpoint });
  proc.on('exit',(code,signal)=>{
    pushGodsEyeDiag('GODS_EYE_PROCESS_EXITED','code '+code+' signal '+signal, 'RECOVERING');
    emitGodsEyeEvent('process-exited', { code, signal });
    if(GodsEyeRuntime.state!=='STOPPING' && GodsEyeRuntime.state!=='STOPPED'){
      GodsEyeRuntime.state='RECOVERING';
      GodsEyeRuntime.proc=null;
      GodsEyeRuntime.pid=null;
    }
  });
  proc.on('error',(e)=>{
    pushGodsEyeDiag('GODS_EYE_START_FAILED','proc error '+String(e), 'FAILED');
    GodsEyeRuntime.state='FAILED';
    GodsEyeRuntime.lastError=String(e);
  });
  GodsEyeRuntime.state='HEALTH_CHECKING';
  pushGodsEyeDiag('GODS_EYE_HEALTH_CHECK_STARTED','waiting for '+GodsEyeRuntime.endpoint, 'HEALTH_CHECKING');
  const poll = await pollGodsEyeHealth({ maxWaitMs: 45000, baseDelayMs: 700, backoffFactor: 1.3 });
  if(poll.ok){
    pushGodsEyeDiag('GODS_EYE_READY','ready after '+poll.attempt+' polls latency '+poll.latency+'ms', 'READY');
    emitGodsEyeEvent('ready', { endpoint: GodsEyeRuntime.endpoint, pid: GodsEyeRuntime.pid });
    try{ if(mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('godsEye:event', { type:'did-finish-load', url: GodsEyeRuntime.endpoint }); }catch(_){}
    return true;
  } else {
    GodsEyeRuntime.lastError='health timeout after '+poll.attempt+' attempts';
    pushGodsEyeDiag('GODS_EYE_START_FAILED', GodsEyeRuntime.lastError, 'FAILED');
    GodsEyeRuntime.state='FAILED';
    return false;
  }
}

async function ensureGodsEyeStarted(timeoutMs){
  if(GodsEyeRuntime.state==='READY'){
    const ok = await checkGodsEyeReady(1500);
    if(ok) return true;
    GodsEyeRuntime.state='RECOVERING';
  }
  if(GodsEyeRuntime.state==='STARTING' || GodsEyeRuntime.state==='HEALTH_CHECKING'){
    const res = await pollGodsEyeHealth({ maxWaitMs: timeoutMs||45000, baseDelayMs: 600 });
    return res.ok;
  }
  const ok = await startGodsEyeServerInternal({ force:false, reason:'ensureStarted' });
  return ok;
}

function stopGodsEyeIfOwned(){
  if(GodsEyeRuntime.proc && GodsEyeRuntime.startedByJarvis && !GodsEyeRuntime.proc.killed){
    pushGodsEyeDiag('GODS_EYE_STOPPING','killing pid '+GodsEyeRuntime.pid, 'STOPPING');
    GodsEyeRuntime.state='STOPPING';
    try{ GodsEyeRuntime.proc.kill(); }catch(_){}
    try{ if(_healthMonitorTimer) clearInterval(_healthMonitorTimer);}catch(_){}
    GodsEyeRuntime.proc=null;
    GodsEyeRuntime.pid=null;
    GodsEyeRuntime.state='STOPPED';
    pushGodsEyeDiag('GODS_EYE_STOPPED','stopped', 'STOPPED');
  } else {
    if(GodsEyeRuntime.proc) console.log('[GodsEye] not stopping — not owned by JARVIS');
  }
}

// ---- MIME ----
const MIME = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.glb': 'model/gltf-binary',
  '.gltf': 'model/gltf+json',
  '.bin': 'application/octet-stream',
  '.wasm': 'application/wasm',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.ico': 'image/x-icon',
};

function findAvailablePort(start, end) {
  return new Promise((resolve) => {
    let p = start;
    const tryNext = () => {
      if (p > end) return resolve(null);
      const srv = http.createServer(() => {});
      srv.once('error', () => { p++; tryNext(); });
      srv.once('listening', () => srv.close(() => resolve(p)));
      srv.listen(p, '127.0.0.1');
    };
    tryNext();
  });
}

function startHttpServer() {
  return new Promise(async (resolve, reject) => {
    const port = await findAvailablePort(8767, 8781);
    if (!port) return reject(new Error('No HTTP port available 8767-8781'));

    const server = http.createServer((req, res) => {
      try {
        const parsed = url.parse(req.url);
        let pathname = decodeURIComponent(parsed.pathname);

        // API endpoints (mirror jarvis.py)
        if (pathname === '/themes.json') {
          // Build themes list lazily — scan themes folder
          try {
            const themesDir = path.join(ROOT, 'jarvis hud difrrent themes');
            const themes = [];
            const seen = new Set();
            const IMG = new Set(['.jpg','.jpeg','.png','.gif','.webp','.bmp','.avif']);
            const VID = new Set(['.mp4','.webm','.mov','.avi','.mkv']);
            function walk(dir) {
              if (!fs.existsSync(dir)) return;
              for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
                const full = path.join(dir, entry.name);
                if (entry.isDirectory()) walk(full);
                else {
                  const ext = path.extname(entry.name).toLowerCase();
                  let t = null;
                  if (IMG.has(ext)) t = 'image';
                  else if (VID.has(ext)) t = 'video';
                  else continue;
                  const rel = path.relative(ROOT, full).replace(/\\/g, '/');
                  if (seen.has(rel)) continue;
                  seen.add(rel);
                  themes.push({ url: '/' + rel.split('/').map(encodeURIComponent).join('/'), type: t, name: entry.name });
                }
              }
            }
            walk(themesDir);
            res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
            res.end(JSON.stringify(themes));
          } catch (e) {
            res.writeHead(500); res.end('themes error');
          }
          return;
        }
        if (pathname === '/hud_state' || pathname === '/api_status') {
          res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
          res.end(JSON.stringify(pathname === '/hud_state' ? { positions: {} } : { groq: 'unknown', gemini: 'unknown', active: null }));
          return;
        }

        // Normalize
        if (pathname === '/') pathname = '/hologram_environment.html';
        // Prevent directory traversal
        const safePath = path.normalize(pathname).replace(/^(\.\.[\/\\])+/, '');
        let filePath = path.join(ROOT, safePath);

        // If path is a directory, try index
        try {
          const st = fs.statSync(filePath);
          if (st.isDirectory()) filePath = path.join(filePath, 'hologram_environment.html');
        } catch (_) {}

        if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
          res.writeHead(404, { 'Content-Type': 'text/plain' });
          res.end('Not found');
          return;
        }

        const ext = path.extname(filePath).toLowerCase();
        const mime = MIME[ext] || 'application/octet-stream';
        // Always no-cache in dev for JS to ensure God’s Eye fallback and icon updates are fresh; offline viewer must load instantly
        const isNoCache = true;
        const stream = fs.createReadStream(filePath);
        res.writeHead(200, {
          'Content-Type': mime,
          'Cache-Control': isNoCache ? 'no-cache, no-store, must-revalidate' : 'public, max-age=3600',
          'X-Content-Type-Options': 'nosniff',
        });
        stream.pipe(res);
        stream.on('error', () => {
          res.writeHead(500); res.end('read error');
        });
      } catch (e) {
        res.writeHead(500); res.end('server error');
      }
    });

    server.listen(port, '127.0.0.1', () => {
      console.log(`[Electron] HTTP server listening on http://127.0.0.1:${port}`);
      httpServer = server;
      httpPort = port;
      resolve(port);
    });
    server.on('error', reject);
  });
}

function maybeSpawnBackend() {
  // Try to detect if WS 8765 already has a listener; if not, spawn jarvis.py with NO_CHROME
  const net = require('net');
  const sock = new net.Socket();
  let done = false;
  const timeout = setTimeout(() => {
    if (done) return;
    done = true;
    try { sock.destroy(); } catch (_) {}
    spawnBackend();
  }, 800);
  sock.setTimeout(800);
  sock.on('connect', () => {
    if (done) return;
    done = true;
    clearTimeout(timeout);
    sock.destroy();
    console.log('[Electron] WS backend already running on 8765 — not spawning');
  });
  sock.on('error', () => {
    if (done) return;
    done = true;
    clearTimeout(timeout);
    try { sock.destroy(); } catch (_) {}
    spawnBackend();
  });
  sock.on('timeout', () => {
    if (done) return;
    done = true;
    try { sock.destroy(); } catch (_) {}
    clearTimeout(timeout);
    spawnBackend();
  });
  try { sock.connect(8765, '127.0.0.1'); } catch (_) {
    if (!done) { done = true; clearTimeout(timeout); spawnBackend(); }
  }

  function spawnBackend() {
    try {
      const pyCandidates = [
        path.join(ROOT, '.venv', 'Scripts', 'python.exe'),
        'python',
        'python3',
      ];
      let py = pyCandidates.find(p => {
        if (p.includes('.venv')) return fs.existsSync(p);
        return true;
      }) || 'python';
      // Prefer .venv if exists
      if (fs.existsSync(path.join(ROOT, '.venv', 'Scripts', 'python.exe'))) {
        py = path.join(ROOT, '.venv', 'Scripts', 'python.exe');
      }
      console.log(`[Electron] Spawning backend: ${py} jarvis.py (JARVIS_NO_CHROME=1 JARVIS_NO_ELECTRON=1)`);
      backendProc = spawn(py, ['jarvis.py'], {
        cwd: ROOT,
        env: { ...process.env, JARVIS_NO_CHROME: '1', JARVIS_NO_ELECTRON: '1' },
        stdio: 'ignore',
        detached: false,
      });
      backendProc.on('error', (e) => console.error('[Electron] backend spawn error', e));
      backendProc.on('exit', (code) => console.log('[Electron] backend exited', code));
    } catch (e) {
      console.error('[Electron] Failed to spawn backend', e);
    }
  }
}

// Media permissions (top-level so createWindow can call it): the HUD needs
// microphone (+camera for hand tracking). Default Electron denies
// getUserMedia without an explicit handler, which surfaces in the renderer
// as NotAllowedError and kills the entire voice pipeline. Allow
// audio/video capture ONLY for our local HUD origin.
function allowMediaForHud(contents) {
  try {
    contents.session.setPermissionRequestHandler((webContents, permission, callback, details) => {
      try {
        const url = (details && details.requestingUrl) || (webContents && webContents.getURL && webContents.getURL()) || '';
        const isHud = url.startsWith('http://127.0.0.1:') || url.startsWith('http://localhost:') || url.startsWith('file:');
        if (permission === 'media' && isHud) {
          const types = (details && details.mediaTypes) || [];
          console.log('[Electron][perm] ALLOW media for HUD', url, types.join(','));
          return callback(true);
        }
        if ((permission === 'audioCapture' || permission === 'videoCapture') && isHud) {
          console.log('[Electron][perm] ALLOW', permission, 'for HUD', url);
          return callback(true);
        }
        console.warn('[Electron][perm] DENY', permission, 'for', url);
        callback(false);
      } catch (e) {
        console.warn('[Electron][perm] handler error', e);
        callback(false);
      }
    });
    contents.session.setPermissionCheckHandler((webContents, permission, requestingOrigin, details) => {
      try {
        const url = (details && details.requestingUrl) || requestingOrigin || '';
        const isHud = url.startsWith('http://127.0.0.1:') || url.startsWith('http://localhost:') || url.startsWith('file:');
        if ((permission === 'media' || permission === 'audioCapture' || permission === 'videoCapture') && isHud) return true;
        if (permission === 'mediaKeySystem' || permission === 'geolocation') return false;
        return true;
      } catch (_) { return false; }
    });
  } catch (e) {
    console.warn('[Electron][perm] Could not install permission handlers', e);
  }
}

function ensureSpideyView() {
  if (spideyView && !spideyView.webContents.isDestroyed()) return spideyView;
  if (spideyView) {
    try { spideyView.webContents.close(); } catch (_) {}
    spideyView = null;
    spideyAttached = false;
  }

  console.log('[Spidey] Creating single WebContentsView (isolated)');
  spideyView = new WebContentsView({
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      // Do NOT disable CSP, do NOT expose Node
      // partition: keep separate from main window storage (optional)
      partition: 'persist:spidey',
    },
  });

  // Security: no Node, isolated
  // Block unexpected window.open from taking over main window
  spideyView.webContents.setWindowOpenHandler(({ url: targetUrl }) => {
    try {
      const u = new URL(targetUrl);
      // Allow navigation inside the view for same-origin or spideytracker links
      if (u.origin === SPIDEY_ORIGIN) {
        console.log('[Spidey] window.open same-origin -> load in view', targetUrl);
        // We'll load it in the same view; deny new window
        setTimeout(() => {
          if (spideyView && !spideyView.webContents.isDestroyed()) spideyView.webContents.loadURL(targetUrl);
        }, 0);
        return { action: 'deny' };
      }
      // External -> open in system browser, not in JARVIS
      console.log('[Spidey] window.open external -> shell.openExternal', targetUrl);
      shell.openExternal(targetUrl);
    } catch (_) {
      try { shell.openExternal(targetUrl); } catch (e2) { console.warn('[Spidey] openExternal failed', e2); }
    }
    return { action: 'deny' };
  });

  // Navigation guard: only allow appropriate navigations inside the spidey view.
  // Prevent the view from navigating to arbitrary origins that might be phishing,
  // but generally allow spideytracker and its CDN. For now, allow all but log,
  // and ensure main window never navigates.
  spideyView.webContents.on('will-navigate', (event, navUrl) => {
    console.log('[Spidey] will-navigate', navUrl);
    // Allow — this is the embedded browser's job. We just log.
    // If we wanted to restrict, we could check origin here and deny undesired.
    // We MUST NOT allow navigation to take over main window — this handler is
    // on the view's webContents, so it won't affect mainWindow.
  });

  // Forward lifecycle events to renderer for loading / error UI
  const send = (payload) => {
    try {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('spidey:event', payload);
      }
    } catch (_) {}
  };

  spideyView.webContents.on('did-start-navigation', (event, urlNav, isInPlace, isMainFrame) => {
    if (isMainFrame) {
      console.log('[Spidey] did-start-navigation', urlNav);
      send({ type: 'did-start-navigation', url: urlNav, isInPlace, isMainFrame });
    }
  });
  spideyView.webContents.on('did-navigate', (event, urlNav) => {
    console.log('[Spidey] did-navigate', urlNav);
    send({ type: 'did-navigate', url: urlNav });
  });
  spideyView.webContents.on('did-finish-load', () => {
    console.log('[Spidey] did-finish-load');
    send({ type: 'did-finish-load', url: spideyView.webContents.getURL() });
  });
  spideyView.webContents.on('did-stop-loading', () => {
    // Fallback: some sites fire did-stop-loading without did-finish-load in certain edge cases
    // If still showing loading and no error, treat as finished to hide spinner
    console.log('[Spidey] did-stop-loading');
    try {
      const curUrl = spideyView.webContents.getURL();
      if (curUrl && curUrl.includes('spideytracker.net')) {
        // Forward as finish to ensure UI updates even if primary event was missed
        send({ type: 'did-finish-load', url: curUrl });
      }
    } catch (_) {}
  });
  spideyView.webContents.on('did-fail-load', (event, code, desc, validatedURL, isMainFrame) => {
    if (isMainFrame) {
      // Ignore -3 ERR_ABORTED which is normal for same-document navigations
      if (code === -3) {
        console.log('[Spidey] did-fail-load ignored abort', code, validatedURL);
        return;
      }
      console.warn('[Spidey] did-fail-load', code, desc, validatedURL);
      send({ type: 'did-fail-load', code, desc, url: validatedURL, isMainFrame });
    }
  });
  spideyView.webContents.on('render-process-gone', (event, details) => {
    console.error('[Spidey] render-process-gone', details);
    send({ type: 'render-process-gone', details });
  });
  spideyView.webContents.on('destroyed', () => {
    console.log('[Spidey] webContents destroyed');
    send({ type: 'destroyed' });
    spideyView = null;
    spideyAttached = false;
  });
  spideyView.webContents.on('crashed', (e, killed) => {
    console.error('[Spidey] crashed', killed);
    send({ type: 'crashed', killed });
  });

  return spideyView;
}

function attachSpidey(bounds) {
  const view = ensureSpideyView();
  if (!mainWindow || mainWindow.isDestroyed()) return { ok: false, error: 'no window' };
  // Attach to contentView if not already attached
  if (!spideyAttached) {
    try {
      mainWindow.contentView.addChildView(view);
      spideyAttached = true;
      console.log('[Spidey] attached to contentView');
    } catch (e) {
      console.error('[Spidey] attach failed', e);
      return { ok: false, error: String(e) };
    }
  }
  if (bounds && typeof bounds.x === 'number') {
    spideyLastBounds = { ...bounds };
    try {
      // Clamp to positive ints
      const b = {
        x: Math.round(bounds.x),
        y: Math.round(bounds.y),
        width: Math.max(0, Math.round(bounds.width)),
        height: Math.max(0, Math.round(bounds.height)),
      };
      view.setBounds(b);
      // console.log('[Spidey] setBounds', b);
    } catch (e) {
      console.error('[Spidey] setBounds failed', e);
    }
  }
  // Load if needed
  const currentUrl = (() => { try { return view.webContents.getURL(); } catch (_) { return ''; } })();
  const needsLoad = !currentUrl || currentUrl === 'about:blank' || (spideyLastUrl && spideyLastUrl !== SPIDEY_URL && currentUrl !== SPIDEY_URL);
  // Actually we want to load SPIDEY_URL once, and not reload on every show unless explicitly requested
  if (!currentUrl || currentUrl === 'about:blank') {
    console.log('[Spidey] loading', SPIDEY_URL);
    spideyLastUrl = SPIDEY_URL;
    view.webContents.loadURL(SPIDEY_URL).catch(e => console.error('[Spidey] loadURL failed', e));
  } else if (spideyLastUrl === SPIDEY_URL && currentUrl !== SPIDEY_URL) {
    // Already loaded something else? Keep it (user navigated), don't force reload
  } else if (!spideyLastUrl) {
    spideyLastUrl = currentUrl;
  }
  return { ok: true, url: currentUrl };
}

function detachSpidey() {
  if (!spideyView || !spideyAttached || !mainWindow || mainWindow.isDestroyed()) {
    return { ok: true, detached: false };
  }
  try {
    mainWindow.contentView.removeChildView(spideyView);
    spideyAttached = false;
    console.log('[Spidey] detached (hidden, not destroyed)');
    return { ok: true, detached: true };
  } catch (e) {
    console.error('[Spidey] detach failed', e);
    return { ok: false, error: String(e) };
  }
}

function destroySpidey() {
  if (!spideyView) return { ok: true };
  try {
    if (spideyAttached && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.contentView.removeChildView(spideyView);
    }
  } catch (_) {}
  try {
    const wc = spideyView.webContents;
    if (wc && !wc.isDestroyed()) wc.close();
  } catch (_) {}
  spideyView = null;
  spideyAttached = false;
  spideyLastUrl = null;
  spideyLastBounds = null;
  console.log('[Spidey] destroyed');
  return { ok: true };
}

// ===== GOD'S EYE WebContentsView (single instance, isolated) =====
function ensureGodsEyeView() {
  if (godsEyeView && !godsEyeView.webContents.isDestroyed()) return godsEyeView;
  if (godsEyeView) { try { godsEyeView.webContents.close(); } catch(_){} godsEyeView=null; godsEyeAttached=false; }
  console.log('[GodsEye] Creating single WebContentsView (isolated)');
  godsEyeView = new WebContentsView({
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      partition: 'persist:godseye',
    },
  });
  // Fix mic permission for God's Eye Realtime (every time) — the HUD's mic + God's Eye voice both need audioCapture
  try { allowMediaForHud(godsEyeView.webContents); } catch (_) {}
  // Also ensure the view itself is considered secure for getUserMedia
  try {
    godsEyeView.webContents.session.setPermissionRequestHandler((wc, perm, cb, details) => {
      const url = (details && details.requestingUrl) || '';
      const isGodEye = url.startsWith(GODSEYE_ORIGIN) || url.startsWith('https://api.openai.com') || url.includes('localhost:4173');
      if ((perm === 'media' || perm === 'audioCapture' || perm === 'videoCapture') && (isGodEye || url.startsWith(GODSEYE_ORIGIN))) {
        return cb(true);
      }
      // Fallback to main HUD handler
      try { return allowMediaForHud(wc); } catch (_) { return cb(false); }
    });
  } catch (_) {}
  godsEyeView.webContents.setWindowOpenHandler(({url: targetUrl}) => {
    try {
      const u = new URL(targetUrl);
      if (u.origin === GODSEYE_ORIGIN) {
        setTimeout(()=>{ if(godsEyeView && !godsEyeView.webContents.isDestroyed()) godsEyeView.webContents.loadURL(targetUrl); },0);
        return {action:'deny'};
      }
      shell.openExternal(targetUrl);
    } catch(_){ try{shell.openExternal(targetUrl);}catch(e){} }
    return {action:'deny'};
  });
  godsEyeView.webContents.on('will-navigate', (e, navUrl)=>{ console.log('[GodsEye] will-navigate', navUrl); });
  const send = (payload)=>{ try{ if(mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('godsEye:event', payload); }catch(_){} };
  godsEyeView.webContents.on('did-start-navigation', (e, urlNav, isInPlace, isMainFrame)=>{ if(isMainFrame){ console.log('[GodsEye] did-start-navigation', urlNav); send({type:'did-start-navigation', url:urlNav}); }});
  godsEyeView.webContents.on('did-navigate', (e, urlNav)=>{ console.log('[GodsEye] did-navigate', urlNav); send({type:'did-navigate', url:urlNav}); });
  godsEyeView.webContents.on('did-finish-load', ()=>{ console.log('[GodsEye] did-finish-load'); send({type:'did-finish-load', url: godsEyeView.webContents.getURL()}); });
  godsEyeView.webContents.on('did-stop-loading', ()=>{ console.log('[GodsEye] did-stop-loading'); try{ const cur=godsEyeView.webContents.getURL(); if(cur && cur.includes('localhost:4173')) send({type:'did-finish-load', url:cur}); }catch(_){} });
  godsEyeView.webContents.on('did-fail-load', (e, code, desc, validatedURL, isMainFrame)=>{ if(isMainFrame && code!==-3){ console.warn('[GodsEye] did-fail-load', code, desc, validatedURL); send({type:'did-fail-load', code, desc, url:validatedURL}); }});
  godsEyeView.webContents.on('render-process-gone', (e, details)=>{ console.error('[GodsEye] render-process-gone', details); send({type:'render-process-gone', details}); });
  godsEyeView.webContents.on('destroyed', ()=>{ console.log('[GodsEye] destroyed'); send({type:'destroyed'}); godsEyeView=null; godsEyeAttached=false; });
  godsEyeView.webContents.on('crashed', (e, killed)=>{ console.error('[GodsEye] crashed', killed); send({type:'crashed', killed}); });
  return godsEyeView;
}
function attachGodsEye(bounds){
  const view = ensureGodsEyeView();
  if(!mainWindow || mainWindow.isDestroyed()) return {ok:false, error:'no window'};
  if(!godsEyeAttached){
    try{ mainWindow.contentView.addChildView(view); godsEyeAttached=true; console.log('[GodsEye] attached'); }catch(e){ console.error('[GodsEye] attach failed',e); return {ok:false, error:String(e)}; }
  }
  if(bounds && typeof bounds.x==='number'){
    godsEyeLastBounds={...bounds};
    try{ view.setBounds({x:Math.round(bounds.x), y:Math.round(bounds.y), width:Math.max(0,Math.round(bounds.width)), height:Math.max(0,Math.round(bounds.height))}); }catch(e){ console.error('[GodsEye] setBounds failed',e); }
  }
  const curUrl = (()=>{ try{ return view.webContents.getURL(); }catch(_){ return ''; }})();
  // Respect explicit load target (fallback offline) if already set via load()
  const pendingUrl = godsEyeLastUrl;
  if(!curUrl || curUrl==='about:blank'){
    const target = pendingUrl || GODSEYE_URL;
    console.log('[GodsEye] loading', target, pendingUrl ? '(from pending)' : '(default)');
    godsEyeLastUrl=target;
    view.webContents.loadURL(target).catch(e=>console.error('[GodsEye] loadURL failed',e));
  } else if(!godsEyeLastUrl){
    godsEyeLastUrl=curUrl;
  }
  return {ok:true, url:curUrl};
}
function detachGodsEye(){
  if(!godsEyeView || !godsEyeAttached || !mainWindow || mainWindow.isDestroyed()) return {ok:true, detached:false};
  try{ mainWindow.contentView.removeChildView(godsEyeView); godsEyeAttached=false; console.log('[GodsEye] detached'); return {ok:true, detached:true}; }catch(e){ console.error('[GodsEye] detach failed',e); return {ok:false, error:String(e)}; }
}
function destroyGodsEye(){
  if(!godsEyeView) return {ok:true};
  try{ if(godsEyeAttached && mainWindow && !mainWindow.isDestroyed()) mainWindow.contentView.removeChildView(godsEyeView); }catch(_){}
  try{ const wc=godsEyeView.webContents; if(wc && !wc.isDestroyed()) wc.close(); }catch(_){}
  godsEyeView=null; godsEyeAttached=false; godsEyeLastUrl=null; godsEyeLastBounds=null;
  console.log('[GodsEye] destroyed');
  return {ok:true};
}


// ---- IPC ----
ipcMain.handle('spidey:create', () => {
  ensureSpideyView();
  return { ok: true, exists: !!spideyView };
});
ipcMain.handle('spidey:show', (_e, bounds) => attachSpidey(bounds));
ipcMain.handle('spidey:hide', () => detachSpidey());
ipcMain.handle('spidey:setBounds', (_e, bounds) => {
  if (!spideyView || !spideyAttached) return { ok: false, error: 'not attached' };
  spideyLastBounds = { ...bounds };
  try {
    spideyView.setBounds({
      x: Math.round(bounds.x),
      y: Math.round(bounds.y),
      width: Math.max(0, Math.round(bounds.width)),
      height: Math.max(0, Math.round(bounds.height)),
    });
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
});
ipcMain.handle('spidey:load', (_e, targetUrl) => {
  const view = ensureSpideyView();
  const u = targetUrl || SPIDEY_URL;
  spideyLastUrl = u;
  return view.webContents.loadURL(u).then(() => ({ ok: true })).catch(e => ({ ok: false, error: String(e) }));
});
ipcMain.handle('spidey:reload', () => {
  if (!spideyView || spideyView.webContents.isDestroyed()) return { ok: false, error: 'no view' };
  try { spideyView.webContents.reload(); return { ok: true }; } catch (e) { return { ok: false, error: String(e) }; }
});
ipcMain.handle('spidey:destroy', () => destroySpidey());
ipcMain.handle('spidey:getState', () => ({
  exists: !!spideyView && !spideyView.webContents.isDestroyed(),
  attached: spideyAttached,
  url: (() => { try { return spideyView ? spideyView.webContents.getURL() : null; } catch (_) { return null; } })(),
  bounds: spideyLastBounds,
  lastUrl: spideyLastUrl,
}));
ipcMain.handle('spidey:getWindowBounds', () => {
  if (!mainWindow || mainWindow.isDestroyed()) return null;
  try { return mainWindow.getContentBounds(); } catch (_) { return null; }
});
ipcMain.handle('godsEye:create', () => { ensureGodsEyeView(); return {ok:true, exists: !!godsEyeView}; });
ipcMain.handle('godsEye:show', (_e, bounds) => attachGodsEye(bounds));
ipcMain.handle('godsEye:hide', () => detachGodsEye());
ipcMain.handle('godsEye:setBounds', (_e, bounds) => {
  if(!godsEyeView || !godsEyeAttached) return {ok:false, error:'not attached'};
  godsEyeLastBounds={...bounds};
  try{ godsEyeView.setBounds({x:Math.round(bounds.x), y:Math.round(bounds.y), width:Math.max(0,Math.round(bounds.width)), height:Math.max(0,Math.round(bounds.height))}); return {ok:true}; }catch(e){ return {ok:false, error:String(e)}; }
});
ipcMain.handle('godsEye:load', (_e, url) => {
  const view=ensureGodsEyeView();
  const u=url||GODSEYE_URL;
  godsEyeLastUrl=u;
  return view.webContents.loadURL(u).then(()=>({ok:true})).catch(e=>({ok:false, error:String(e)}));
});
ipcMain.handle('godsEye:reload', () => {
  if(!godsEyeView || godsEyeView.webContents.isDestroyed()) return {ok:false, error:'no view'};
  try{ godsEyeView.webContents.reload(); return {ok:true}; }catch(e){ return {ok:false, error:String(e)}; }
});
ipcMain.handle('godsEye:destroy', () => destroyGodsEye());
ipcMain.handle('godsEye:getState', () => ({
  exists: !!godsEyeView && !godsEyeView.webContents.isDestroyed(),
  attached: godsEyeAttached,
  url: (()=>{ try{ return godsEyeView? godsEyeView.webContents.getURL(): null; }catch(_){ return null; }})(),
  bounds: godsEyeLastBounds,
  lastUrl: godsEyeLastUrl,
  runtime: {
    state: GodsEyeRuntime.state,
    endpoint: GodsEyeRuntime.endpoint,
    port: GodsEyeRuntime.port,
    origin: GodsEyeRuntime.origin,
    pid: GodsEyeRuntime.pid,
    startedByJarvis: GodsEyeRuntime.startedByJarvis,
    lastError: GodsEyeRuntime.lastError,
    healthLatencyMs: GodsEyeRuntime.healthLatencyMs,
    lastHealthAt: GodsEyeRuntime.lastHealthAt,
    startupAttempts: GodsEyeRuntime.startupAttempts,
    diagnostics: GodsEyeRuntime.diagnostics.slice(-20),
  }
}));
ipcMain.handle('godsEye:getRuntime', () => ({
  state: GodsEyeRuntime.state,
  endpoint: GodsEyeRuntime.endpoint,
  port: GodsEyeRuntime.port,
  origin: GodsEyeRuntime.origin,
  pid: GodsEyeRuntime.pid,
  startedByJarvis: GodsEyeRuntime.startedByJarvis,
  lastError: GodsEyeRuntime.lastError,
  healthLatencyMs: GodsEyeRuntime.healthLatencyMs,
  lastHealthAt: GodsEyeRuntime.lastHealthAt,
  startupAttempts: GodsEyeRuntime.startupAttempts,
  procAlive: !!(GodsEyeRuntime.proc && !GodsEyeRuntime.proc.killed && GodsEyeRuntime.proc.exitCode===null),
  diagnostics: GodsEyeRuntime.diagnostics.slice(-30),
}));
ipcMain.handle('godsEye:healthCheck', async () => {
  const hc = await httpHealthCheck(GodsEyeRuntime.endpoint, 2500);
  return { ok: hc.ok, status: hc.status, latency: hc.latency, error: hc.error, endpoint: GodsEyeRuntime.endpoint, state: GodsEyeRuntime.state };
});
ipcMain.handle('godsEye:ensureStarted', async (_e, opts) => {
  const timeout = (opts && opts.timeoutMs) || 45000;
  pushGodsEyeDiag('GODS_EYE_START_REQUESTED', 'ensureStarted via IPC timeout '+timeout, GodsEyeRuntime.state);
  const ok = await ensureGodsEyeStarted(timeout);
  return { ok, state: GodsEyeRuntime.state, endpoint: GodsEyeRuntime.endpoint, pid: GodsEyeRuntime.pid, error: GodsEyeRuntime.lastError };
});
ipcMain.handle('godsEye:startServer', async () => {
  pushGodsEyeDiag('GODS_EYE_START_REQUESTED', 'startServer IPC called', GodsEyeRuntime.state);
  const ok = await startGodsEyeServerInternal({ force:false, reason:'ipc:startServer' });
  if (ok) return { ok:true, started: GodsEyeRuntime.startedByJarvis, pid: GodsEyeRuntime.pid, url: GodsEyeRuntime.endpoint, state: GodsEyeRuntime.state, method: 'npm run dev' };
  // Check if already ready (duplicate protection)
  const ready = await checkGodsEyeReady(1500);
  if (ready) return { ok:true, alreadyRunning:true, url: GodsEyeRuntime.endpoint, state: GodsEyeRuntime.state };
  return { ok:false, error: GodsEyeRuntime.lastError||'failed to start', state: GodsEyeRuntime.state, portConflict: GodsEyeRuntime.lastError && GodsEyeRuntime.lastError.includes('PORT CONFLICT') };
});
ipcMain.handle('godsEye:stop', async () => {
  if (!GodsEyeRuntime.startedByJarvis) return { ok:false, error:'not owned by JARVIS (started externally)', state: GodsEyeRuntime.state };
  stopGodsEyeIfOwned();
  return { ok:true, state: GodsEyeRuntime.state };
});
ipcMain.handle('godsEye:openExternal', async (_e, url) => {
  const target = url || GodsEyeRuntime.endpoint;
  // Ensure readiness before opening fullscreen
  const ready = await checkGodsEyeReady(1800);
  if (!ready && GodsEyeRuntime.state!=='READY') {
    pushGodsEyeDiag('GODS_EYE_FULLSCREEN', 'not ready yet, ensuring started before openExternal', GodsEyeRuntime.state);
    const ok = await ensureGodsEyeStarted(30000);
    if (!ok) return { ok:false, error:'Gods Eye not ready after ensureStarted: '+(GodsEyeRuntime.lastError||'timeout'), state: GodsEyeRuntime.state };
  }
  try{ await shell.openExternal(target); pushGodsEyeDiag('GODS_EYE_FULLSCREEN','opened '+target, GodsEyeRuntime.state); return {ok:true, url:target}; }catch(e){ return {ok:false, error:String(e)}; }
});
// Prevent main window navigation from being hijacked
function guardMainNavigation() {
  if (!mainWindow) return;
  mainWindow.webContents.on('will-navigate', (event, navUrl) => {
    // Allow only our HUD origin (http 127.0.0.1 or file)
    try {
      const u = new URL(navUrl);
      const isHud = (u.hostname === '127.0.0.1' || u.hostname === 'localhost') && u.pathname.includes('hologram');
      const isFile = u.protocol === 'file:';
      if (!isHud && !isFile) {
        console.warn('[Guard] Blocked main window will-navigate to', navUrl);
        event.preventDefault();
        // Open externals in system browser
        shell.openExternal(navUrl);
      }
    } catch (e) {
      event.preventDefault();
    }
  });
  mainWindow.webContents.setWindowOpenHandler(({ url: targetUrl }) => {
    console.log('[Guard] main window window.open -> external', targetUrl);
    shell.openExternal(targetUrl);
    return { action: 'deny' };
  });
}

async function createWindow() {
  const port = await startHttpServer();
  const hudUrl = `http://127.0.0.1:${port}/hologram_environment.html`;

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#000000',
    show: false,
    title: 'JARVIS Holographic Environment',
    frame: false,
    fullscreen: true,
    kiosk: false,
    autoHideMenuBar: true,
    backgroundColor: '#000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
    },
  });

  guardMainNavigation();
  allowMediaForHud(mainWindow.webContents);

  // Update Spidey bounds on window resize immediately
  const onResize = () => {
    if (spideyAttached && spideyView && spideyLastBounds) {
      try { mainWindow.webContents.send('spidey:event', { type: 'window-resize' }); } catch (_) {}
    }
  };
  const onGodsEyeResize = () => {
    if (godsEyeAttached && godsEyeView && godsEyeLastBounds) {
      try { mainWindow.webContents.send('godsEye:event', { type: 'window-resize' }); } catch (_) {}
    }
  };
  mainWindow.on('resize', onResize);
  mainWindow.on('move', onResize);
  mainWindow.on('maximize', onResize);
  mainWindow.on('unmaximize', onResize);
  mainWindow.on('enter-full-screen', onResize);
  mainWindow.on('leave-full-screen', onResize);
  mainWindow.on('resize', onGodsEyeResize);
  mainWindow.on('move', onGodsEyeResize);
  mainWindow.on('maximize', onGodsEyeResize);
  mainWindow.on('unmaximize', onGodsEyeResize);

  mainWindow.on('close', () => {
    // Hide spidey and godsEye cleanly before close
    try { detachSpidey(); } catch (_) {}
    try { detachGodsEye(); } catch (_) {}
  });
  mainWindow.on('closed', () => {
    mainWindow = null;
    destroySpidey();
    destroyGodsEye();
  });

  await mainWindow.loadURL(hudUrl);
  mainWindow.show();
  try { mainWindow.setFullScreen(true); } catch(_) {}
  console.log('[Electron] HUD loaded fullscreen (no frame) ', hudUrl);

  // Optionally spawn backend WS if not present
  maybeSpawnBackend();

  // Auto-start God's Eye in background (JARVIS owns orchestration — BAT not required)
  // Non-blocking: JARVIS HUD becomes ready immediately, GodsEye initializes async
  setTimeout(async () => {
    try {
      pushGodsEyeDiag('GODS_EYE_START_REQUESTED', 'background auto-start after HUD ready', GodsEyeRuntime.state);
      const ok = await ensureGodsEyeStarted(45000);
      if (ok) pushGodsEyeDiag('GODS_EYE_READY', 'background auto-start succeeded at '+GodsEyeRuntime.endpoint, 'READY');
      else pushGodsEyeDiag('GODS_EYE_START_FAILED', 'background auto-start failed: '+(GodsEyeRuntime.lastError||'timeout'), 'FAILED');
    } catch(e){ pushGodsEyeDiag('GODS_EYE_START_FAILED', String(e), 'FAILED'); console.warn('[GodsEye] background auto-start failed', e); }
  }, 1800);

  // Ensure spidey view is created lazily but ready on demand; don't create at startup to save resources
}

app.whenReady().then(createWindow).catch(e => {
  console.error('[Electron] whenReady failed', e);
  dialog.showErrorBox('JARVIS Electron failed', String(e));
});

app.on('window-all-closed', () => {
  try { destroySpidey(); } catch (_) {}
  try { destroyGodsEye(); } catch (_) {}
  try { if (httpServer) httpServer.close(); } catch (_) {}
  try { if (backendProc && !backendProc.killed) backendProc.kill(); } catch (_) {}
  try { stopGodsEyeIfOwned(); } catch(_){}
  try { if(_healthMonitorTimer) clearInterval(_healthMonitorTimer);}catch(_){}
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  try { destroySpidey(); } catch (_) {}
  try { destroyGodsEye(); } catch (_) {}
  try { if (httpServer) httpServer.close(); } catch (_) {}
  try { if (backendProc && !backendProc.killed) backendProc.kill(); } catch (_) {}
  try { stopGodsEyeIfOwned(); } catch(_){}
  try { if(_healthMonitorTimer) clearInterval(_healthMonitorTimer);}catch(_){}
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// Security: disallow remote module, etc. — default is secure
app.on('web-contents-created', (_e, contents) => {
  contents.on('will-attach-webview', (event) => {
    // Deny webview tag (deprecated) — we use WebContentsView
    event.preventDefault();
  });
});
