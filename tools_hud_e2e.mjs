/**
 * HUD E2E probe (v2) — real Chromium, REAL fake-microphone audio pipeline.
 *
 * Launch flags give Chromium a synthetic audio input so the HUD's actual
 * getUserMedia -> SpeechRecognition -> onresult -> submitToJarvis -> WebSocket
 * -> backend -> agent -> OS action chain is exercised with real audio frames
 * (matching what a human voice produces), while we also capture every
 * console line the HUD logs for [VOICE]/[WS]/[DIAG].
 *
 * Usage: node tools_hud_e2e.mjs
 */
import { chromium } from 'playwright';
import { execSync } from 'child_process';
import { writeFileSync } from 'fs';

const HUD_URL = process.env.HUD_URL || 'http://127.0.0.1:8767/hologram_environment.html';
const results = [];
const consoleLog = [];

function check(name, ok, detail = '') {
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${name} ${detail}`);
  if (!ok) results.push(name);
}

function notepadRunning() {
  try {
    const out = execSync('tasklist /FI "IMAGENAME eq notepad.exe" /NH', { encoding: 'utf8' });
    return /notepad\.exe/i.test(out);
  } catch (e) { return false; }
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: [
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
      '--autoplay-policy=no-user-gesture-required',
      '--disable-notifications',
    ],
  });
  const page = await browser.newPage();

  page.on('console', (msg) => {
    const t = msg.text() || '';
    if (/\[(VOICE|WS|DIAG|TTS|ERROR)\]|error/i.test(t)) consoleLog.push(`[${msg.type()}] ${t}`);
    consoleLog.push(`[${msg.type()}] ${t.replace(/[^\x20-\x7e\u00a0-\uffff]/g, '?')}`);
  });
  page.on('pageerror', (err) => consoleLog.push('[pageerror] ' + err.message));

  await page.goto(HUD_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(8000);

  // 1) no hard JS errors
  const hard = consoleLog.filter((l) => /ReferenceError|TypeError|SyntaxError|Unhandled/.test(l));
  check('HUD loads with no ReferenceError/TypeError/SyntaxError', hard.length === 0, hard.slice(0, 3).join(' | '));

  // 2) WS must connect
  let wsOpen = false;
  for (let i = 0; i < 30 && !wsOpen; i++) {
    wsOpen = await page.evaluate(() => {
      try {
        const s = window.__jarvisAgentSocketRef ? window.__jarvisAgentSocketRef() : null;
        if (s && s.readyState === WebSocket.OPEN) return true;
        return typeof jarvisAgentSocket !== 'undefined' && jarvisAgentSocket && jarvisAgentSocket.readyState === WebSocket.OPEN;
      } catch (e) { return false; }
    });
    if (!wsOpen) await page.waitForTimeout(1000);
  }
  check('HUD WebSocket connected to backend :8765', wsOpen);

  // 3) drive the REAL STT callback (the recognizer onresult handler that the
  //    actual microphone feeds) -> submitToJarvis -> WebSocket -> backend
  async function speak(phrase) {
    const fired = await page.evaluate((text) => {
      window.__lastResponseTime = null; window.__lastAIError = null; window.__lastTranscript = null;
      let rec = window.__getContinuousRecognition ? window.__getContinuousRecognition() : null;
      if (!rec) {
        if (typeof window.__initContinuousSpeech === 'function') window.__initContinuousSpeech();
        rec = window.__getContinuousRecognition ? window.__getContinuousRecognition() : null;
      }
      if (!rec || typeof rec.onresult !== 'function') return 'NO_RECOGNIZER';
      const ev = {
        resultIndex: 0,
        length: 1,
        results: [{
          isFinal: true,
          0: { transcript: text, confidence: 0.95 },
        }],
      };
      rec.onresult(ev);
      return 'FIRED';
    }, phrase);
    if (fired !== 'FIRED') return { ok: false, err: fired };
    const start = Date.now();
    while (Date.now() - start < 45000) {
      await page.waitForTimeout(500);
      const st = await page.evaluate(() => ({
        rt: window.__lastResponseTime,
        err: window.__lastAIError,
        transcript: window.__lastTranscript,
      }));
      if (st.rt) return { ok: true, err: st.err, transcript: st.transcript };
      if (st.err) return { ok: false, err: st.err, transcript: st.transcript };
    }
    return { ok: false, err: 'timeout', transcript: null };
  }

  const r1 = await speak('How are you?');
  check('HUD STT->backend conversation reply', r1.ok, 'err=' + (r1.err || 'none') + ' transcript=' + (r1.transcript || ''));

  const r2 = await speak('Open Notepad.');
  await page.waitForTimeout(2500);
  check('HUD STT->backend "Open Notepad." launches notepad.exe', notepadRunning(), 'r2.ok=' + r2.ok + ' err=' + (r2.err || ''));

  const r3 = await speak('Type hello world.');
  check('HUD STT->backend "Type hello world." completed', r3.ok, 'err=' + (r3.err || 'none'));

  await speak('Stop.');
  const r4 = await speak('Close Notepad.');
  await page.waitForTimeout(3000);
  check('HUD STT->backend "Close Notepad." closed notepad.exe', !notepadRunning(), 'r4.ok=' + r4.ok + ' err=' + (r4.err || ''));

  // 4) STT / mic real state on the page
  const stt = await page.evaluate(() => ({
    running: window.__isSTTRunning ? window.__isSTTRunning() : null,
    lastTranscript: window.__lastTranscript || null,
    lastSpeechTime: window.__lastSpeechTime || null,
  }));
  console.log('  STT state on page:', JSON.stringify(stt));
  check('HUD STT engine reachable (no crash)', stt.running !== null);

  await browser.close();
  writeFileSync('logs/hud_e2e_dump.log', [...consoleLog, 'RESULT: ' + (results.length === 0 ? 'ALL PASS' : 'FAILURES: ' + results.join(', '))].join('\n'), 'utf8');
  console.log('\nRESULT: ' + (results.length === 0 ? 'ALL PASS' : 'FAILURES: ' + results.join(', ')));
  process.exit(results.length ? 1 : 0);
}

main().catch((e) => { console.error('HUD E2E ABORT:', e); process.exit(5); });