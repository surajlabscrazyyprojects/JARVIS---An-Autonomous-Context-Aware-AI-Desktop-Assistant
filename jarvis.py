#!/usr/bin/env python3
"""J.A.R.V.I.S. - single-file launcher
===================================

One file does everything:

  1. Serves the HUD (hologram_environment.html) + MediaPipe hand-tracking
     assets over a local HTTP server (required so the ES modules + .wasm load).
  2. Runs a live WebSocket backend on ws://localhost:8765 that speaks the same
     protocol the HUD expects: it answers chat with a real LLM (Groq/Gemini)
     and performs a few direct actions (open app, volume, mute).
  3. Opens the hologram HUD in a dedicated fullscreen Chrome window.

Everything shuts down cleanly when the HUD window is closed.

Run it:  python jarvis.py    (double-click also works)
"""
from __future__ import annotations

import asyncio
import base64
import ctypes
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid
import requests
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from agent import ComputerAgent, Memory, doctor as agent_doctor
from routine_engine import RoutineEngine
from reminder_intel import ReminderIntel
from jarvis.context import ContextFusionEngine
from jarvis.proactivity import ProactivityEngine
from jarvis.reasoning import RequirementDiscoveryEngine
from jarvis.runtime import Capability, CapabilityRegistry, EventStore, TaskStore
from jarvis.observer import DesktopObserver
from jarvis.tools import BrowserTool, DevelopmentToolAdapter, TaskPromptGenerator, register_development_tools
from jarvis.world_state import WorldStateManager
from jarvis.core.task_orchestrator import TaskOrchestrator, TaskStatus

ROOT = Path(__file__).resolve().parent
HUD_FILE = ROOT / "hologram_environment.html"
WS_PORT = 8765
PROFILE_DIR = ROOT / ".jarvis_browser_profile"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
THEMES_DIR = ROOT / "jarvis hud difrrent themes"


def build_themes():
    """Scan the dedicated themes folder for image/video/gif backgrounds."""
    themes = []
    seen = set()
    if not THEMES_DIR.exists():
        return themes
    for dirpath, dirnames, filenames in os.walk(THEMES_DIR):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in IMAGE_EXTS:
                t = "image"
            elif ext in VIDEO_EXTS:
                t = "video"
            else:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            if rel in seen:
                continue
            seen.add(rel)
            url = "/" + urllib.parse.quote(rel)
            themes.append({"url": url, "type": t, "name": fn})
    return themes


THEMES = build_themes()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("jarvis")

# --- Make double-clicking use the project's virtualenv (has the deps) -------
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"


def _running_in_venv():
    """True if the current interpreter can import the backend dependencies."""
    try:
        import websockets  # noqa: F401
        import openai  # noqa: F401
        return True
    except Exception:
        return False


# Load .env if present (GROQ_API_KEY / GEMINI_API_KEY / provider / model)
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

# ==========================================================================
# 1) HUD web server
# ==========================================================================

class _HudHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".glb": "model/gltf-binary",
        ".gltf": "model/gltf+json",
        ".bin": "application/octet-stream",
        ".wasm": "application/wasm",
        ".json": "application/json",
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/themes.json":
            self._json(THEMES)
            return
        if path == "/hud_state":
            self._json({"positions": {}})
            return
        if path == "/api_status":
            self._json(CURRENT_API_STATUS)
            return
        if path == "/jarvis_ws_url":
            self._json({"ws_url": CURRENT_WS_URL})
            return
        if path == "/api/memory":
            # Read-only, structured memory surface for the HUD. No raw audio
            # or secrets are exposed; activity is bounded to recent records.
            try:
                def read_json(name, default):
                    p = ROOT / "memory" / name
                    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
                activity = []
                ap = ROOT / "memory" / "activity.jsonl"
                if ap.exists():
                    for line in ap.read_text(encoding="utf-8").splitlines()[-100:]:
                        try: activity.append(json.loads(line))
                        except Exception: pass
                self._json({
                    "conversations": {"items": activity},
                    "preferences": {"items": read_json("memories.json", {})},
                    "memory": read_json("memories.json", {}),
                    "tasks": read_json("tasks.json", {}),
                })
            except Exception as exc:
                self._json({"error": str(exc), "conversations": {"items": []}, "preferences": {"items": {}}, "memory": {}})
            return
        super().do_GET()

    def _json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _start_http() -> int | None:
    for port in range(8767, 8781):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), _HudHandler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            log.info("HTTP server bound to 127.0.0.1:%d (secure context for getUserMedia)", port)
            return port
        except OSError as e:
            log.debug("HTTP port %d busy: %s", port, e)
            continue
    log.error("Could not bind HTTP server on 8767-8780 — all ports busy")
    return None


def _start_tts() -> bool:
    # Fish Audio gateway on 8766 is the ONE authoritative TTS provider.
    # A previous fallback started a different (chatterbox) engine on the same
    # port when the gateway was down, silently replacing Fish with an
    # incompatible API — that fallback is removed. If no healthy gateway
    # answers, report it truthfully so the user starts start_voice.py.
    try:
        import urllib.request as _ur

        with _ur.urlopen("http://127.0.0.1:8766/health", timeout=1.5) as resp:
            body = resp.read(2048).decode("utf-8", "replace")
        if resp.status == 200 and "provider" in body:
            log.info("Local TTS gateway already running on 8766 — reusing it (single gateway).")
            return True
    except Exception:
        pass
    log.error("No Fish TTS gateway on 127.0.0.1:8766. Voice replies will show as text only. "
              "Start it with: python start_voice.py (it holds FISH_API_KEY server-side).")
    return False

# ==========================================================================
# 2) Backend brain (LLM) + direct actions
# ==========================================================================

# Default models. NOTE: verified against the live Groq account — llama-3.3-70b
# is NOT available on this key; openai/gpt-oss-120b IS and returns 200.
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
GROQ_FALLBACK_MODELS = ["openai/gpt-oss-20b", "allam-2-7b", "qwen/qwen3.6-27b"]
GEMINI_DEFAULT_MODEL = "gemini-1.5-flash"
GEMINI_FALLBACK_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash-latest"]

# Capability contract. The HUD MUST verify these before using a feature;
# a backend without 'stt_audio' is too old for voice and must be restarted.
# Bump BUILD_ID whenever the WS contract changes.
BUILD_ID = "2026-09-10+voice-capture-manager2"
BACKEND_CAPS = ["stt_audio", "stt_ping", "stt_partial", "voice_diag", "personality_v1", "detail_replies"]

# Holds the last live API status, shared with the /api_status HTTP endpoint.
CURRENT_API_STATUS: dict = {"groq": "unknown", "gemini": "unknown", "active": None}
CURRENT_WS_URL = f"ws://127.0.0.1:{WS_PORT}"


def _read_txt_key(path: Path):
    """Load an API key from one of the loose 'api txt' files as a fallback.

    groq api.txt embeds its key inside a JSON blob; gemini api.txt is a bare
    key line. Returns None if unreadable.
    """
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        if raw.startswith("{"):
            data = json.loads(raw)
            for m in data.get("custom_models", []):
                if m.get("api_key"):
                    return str(m["api_key"]).strip()
        return raw
    except Exception:  # noqa: BLE001
        return None


class Brain:
    """Minimal LLM client (Groq or Gemini, OpenAI-compatible).

    Keys are resolved from the environment first, then from the loose
    api txt files (groq api.txt / gemini api.txt) in the project folder.
    """

    def __init__(self) -> None:
        self.client = None
        self.model = None
        self.provider = None
        self._groq_key = None
        self._gemini_key = None
        self._fallbacks: list = []

        provider = (os.environ.get("JARVIS_CONVERSATION_PROVIDER") or "groq").lower().strip()
        if provider != "gemini":
            provider = "groq"

        groq_key = os.environ.get("GROQ_API_KEY") or _read_txt_key(ROOT / "groq api.txt")
        gemini_key = os.environ.get("GEMINI_API_KEY") or _read_txt_key(ROOT / "gemini api.txt")
        self._groq_key = (groq_key or "").strip() or None
        self._gemini_key = (gemini_key or "").strip() or None

        # Prefer Gemini only when explicitly asked for AND its key is present;
        # otherwise fall back to Groq (verified working).
        if provider == "gemini" and self._gemini_key:
            try:
                from openai import OpenAI

                self.client = OpenAI(
                    api_key=self._gemini_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                )
                self.model = os.environ.get("JARVIS_CONVERSATION_MODEL") or GEMINI_DEFAULT_MODEL
                self.provider = "gemini"
                self._fallbacks = list(GEMINI_FALLBACK_MODELS)
                log.info("Brain configured via gemini (%s)", self.model)
            except Exception as exc:  # noqa: BLE001
                log.warning("Gemini client init failed, falling back to Groq: %s", exc)
                provider = "groq"

        if provider == "groq" and self._groq_key:
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=self._groq_key, base_url="https://api.groq.com/openai/v1")
                self.model = os.environ.get("JARVIS_CONVERSATION_MODEL") or GROQ_DEFAULT_MODEL
                self.provider = "groq"
                self._fallbacks = list(GROQ_FALLBACK_MODELS)
                log.info("Brain configured via groq (%s)", self.model)
            except Exception as exc:  # noqa: BLE001
                log.warning("Groq client init failed: %s", exc)

        if self.client is None:
            log.warning("No working LLM provider - using offline fallback responses.")

    async def respond(self, text: str) -> str:
        # Shared personality gate so every conversational path sounds like one system.
        try:
            from personality import (PERSONALITY_BLOCK, estimate_tone,
                                     format_for_speech, personality_directive)
            _persona = True
        except Exception:
            _persona = False
        if self.client is not None:
            tried = []
            models = [self.model, *self._fallbacks]
            for model in models:
                if model in tried:
                    continue
                tried.append(model)
                try:
                    system = (
                        "You are J.A.R.V.I.S., Tony Stark's personal AI. "
                        "Be concise, witty, and helpful. Address the user as 'sir' "
                        "occasionally. Keep replies under 60 words."
                    )
                    if _persona:
                        tone = estimate_tone(text)
                        system += "\n" + PERSONALITY_BLOCK + "\n" + personality_directive(tone)
                    stream = self.client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": text},
                        ],
                        max_tokens=300,
                        stream=True,
                    )
                    chunks = []
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content or ""
                        if delta:
                            chunks.append(delta)
                    reply = "".join(chunks).strip()
                    if reply:
                        if _persona:
                            try:
                                speak, _ = format_for_speech(reply, kind="answer",
                                                             tone=estimate_tone(text))
                                return speak
                            except Exception:
                                pass
                        return reply
                    log.warning("Model %s returned empty content; trying next.", model)
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)
                    # Only model-not-found is worth falling back on; auth/other
                    # errors indicate a deeper problem, so stop trying models.
                    if "model_not_found" in err or "does not exist" in err:
                        log.warning("Model %s unavailable (%s); trying next.", model, err)
                        continue
                    log.warning("LLM error with %s: %s", model, err)
                    break
        return (
            f"Understood, sir: {text}. "
            "(The live LLM provider is unavailable right now — this reply is "
            "the local offline fallback.)"
        )

    def verify(self) -> dict:
        """Live-probe both configured providers and return a status dict.

        Uses requests with a browser-like User-Agent so Cloudflare does not
        false-positive (urllib gets blocked with Cloudflare error 1010).
        """
        result = {"groq": "inactive", "gemini": "inactive", "active": self.provider}
        try:
            import requests
        except Exception:  # noqa: BLE001
            return result

        if self._groq_key:
            try:
                r = requests.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={
                        "Authorization": f"Bearer {self._groq_key}",
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                        ),
                    },
                    timeout=25,
                )
                result["groq"] = "ok" if r.status_code == 200 else f"http{r.status_code}"
            except Exception:  # noqa: BLE001
                result["groq"] = "error"

        if self._gemini_key:
            try:
                r = requests.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={self._gemini_key}",
                    timeout=25,
                )
                result["gemini"] = "ok" if r.status_code == 200 else f"http{r.status_code}"
            except Exception:  # noqa: BLE001
                result["gemini"] = "error"

        global CURRENT_API_STATUS
        CURRENT_API_STATUS = dict(result)
        return result

# --- Windows master volume via winmm (no extra dependencies) ----------------

def _set_windows_volume(percent: int) -> int:
    try:
        winmm = ctypes.WinDLL("winmm")
        percent = max(0, min(100, int(percent)))
        vol = int(round(percent * 65535 / 100))
        val = (vol << 16) | vol
        winmm.waveOutSetVolume(0, val)
        return percent
    except Exception:
        return -1


def _get_windows_volume() -> int:
    try:
        winmm = ctypes.WinDLL("winmm")
        val = ctypes.c_uint32()
        winmm.waveOutGetVolume(0, ctypes.byref(val))
        left = val.value & 0xFFFF
        return int(round(left * 100 / 65535))
    except Exception:
        return 50


APP_LAUNCH_ALIASES = {
    "vscode": "Code", "vs code": "Code", "visual studio code": "Code",
    "chrome": "chrome", "google chrome": "chrome", "the chrome": "chrome",
    "notepad": "notepad", "notebook": "notepad", "notepad++": "notepad++",
    "calculator": "calc", "calc": "calc",
    "file explorer": "explorer", "explorer": "explorer",
    "word": "winword", "microsoft word": "winword", "excel": "excel",
    "powerpoint": "powerpnt", "edge": "msedge", "firefox": "firefox",
    "spotify": "Spotify", "whatsapp": "WhatsApp",
    "premiere pro": "Adobe Premiere Pro", "premiere": "Adobe Premiere Pro",
    "after effects": "AfterFX", "ae": "AfterFX",
    "paint": "mspaint", "task manager": "taskmgr", "control panel": "control",
    "settings": "ms-settings:",
}


def _open_app(target: str) -> bool:
    """Open a Windows application or URL via START, with a small alias map.

    Returns True on success. This is the OFFLINE fast path — no network, no LLM.
    """
    t = (target or "").strip()
    if not t:
        return False
    alias = APP_LAUNCH_ALIASES.get(t.lower(), t)
    # Bare URL? open it directly in the default browser.
    if re.match(r"^(https?://|www\.)", t, re.IGNORECASE):
        try:
            subprocess.Popen(["cmd", "/c", "start", "", t], shell=False)
            return True
        except Exception:  # noqa: BLE001
            return False
    try:
        subprocess.Popen(["cmd", "/c", "start", "", alias], shell=False)
        return True
    except Exception:  # noqa: BLE001
        try:
            subprocess.Popen([alias])
            return True
        except Exception:  # noqa: BLE001
            return False


def _direct_action(text: str) -> str | None:
    """Return a spoken reply for a simple command, or None to pass to the LLM.

    This is the OFFLINE FAST path: simple "open X", volume and mute are handled
    here with zero network / zero LLM, so they feel instant even without a
    working internet connection or API key.
    """
    t = text.strip().lower()
    if t.startswith("open "):
        target = text.strip()[5:].strip()
        if not target:
            return None
        if _open_app(target):
            return f"Opening {target}."
        # Couldn't launch it offline: return None so the backend can escalate to
        # the LLM agent (jarvis mode), or stay quiet (non-jarvis fast mode).
        return None
    if "mute" in t and "unmute" not in t:
        _set_windows_volume(0)
        return "Muted, sir."
    if "unmute" in t:
        _set_windows_volume(50)
        return "Unmuted."
    if "volume up" in t or "increase volume" in t:
        v = min(100, _get_windows_volume() + 10)
        _set_windows_volume(v)
        return f"Volume at {v} percent."
    if "volume down" in t or "decrease volume" in t:
        v = max(0, _get_windows_volume() - 10)
        _set_windows_volume(v)
        return f"Volume at {v} percent."
    m = re.search(r"volume(?: to| at)?\s*(\d{1,3})", t)
    if m and ("set" in t or "volume to" in t or "volume at" in t):
        v = int(m.group(1))
        _set_windows_volume(v)
        return f"Volume set to {v} percent."
    return None

# ==========================================================================
# 2b) Server-side STT (faster-whisper) for runtimes without Web Speech API
# ==========================================================================
# Electron's Chromium has no usable SpeechRecognition (start() always fails
# with `not-allowed`), so the HUD records mic utterances itself (16 kHz mono
# WAV) and sends them over the existing WebSocket as {type:'stt_audio'}.
# This keeps ONE authoritative connection and zero new ports.
STT_PROVIDER = (os.environ.get("JARVIS_STT_PROVIDER") or "auto").strip().lower()
# Groq is the preferred fast final recognizer when it is configured.  Local
# faster-whisper remains a deliberate offline fallback, not a second listener.
STT_MODEL_NAME = (os.environ.get("JARVIS_STT_MODEL") or "whisper-large-v3-turbo").strip() or "whisper-large-v3-turbo"
STT_GROQ_FALLBACK_MODEL = "whisper-large-v3"
# Fast small model for LIVE interim words while the user is still speaking.
# Final transcripts always use STT_MODEL_NAME (accuracy); partials favor speed.
STT_PARTIAL_MODEL = (os.environ.get("JARVIS_STT_PARTIAL_MODEL") or "tiny").strip() or "tiny"
STT_DEVICE = (os.environ.get("JARVIS_STT_DEVICE") or "cpu").strip() or "cpu"
STT_MAX_BYTES = 10 * 1024 * 1024  # ~5 min of 16 kHz mono 16-bit; utterances are seconds

_stt_models: dict = {}
_stt_locks: dict = {}
_stt_locks_guard = threading.Lock()
_stt_load_error: dict = {}
# Recent stt_audio results by req_id (bounded). The HUD watchdog retries an
# unanswered utterance with the SAME req_id; a slow original may still land.
# Re-sending the cached result avoids a wasted re-transcription AND a duplicate
# transcript downstream (one utterance -> one AI request).
_stt_recent_results: dict = {}
_STT_RECENT_MAX = 100


def _get_stt_lock(name: str) -> threading.Lock:
    with _stt_locks_guard:
        return _stt_locks.setdefault(name, threading.Lock())


def _get_stt_model(name: str = None):
    """Lazily load a faster-whisper model (downloads once, then offline)."""
    name = name or STT_MODEL_NAME
    if _stt_models.get(name) is not None:
        return _stt_models[name]
    if _stt_load_error.get(name) is not None:
        raise RuntimeError(_stt_load_error[name])
    try:
        from faster_whisper import WhisperModel
        log.info("STT loading faster-whisper model=%r device=%r (first run downloads it, then offline)...",
                 name, STT_DEVICE)
        t0 = time.time()
        _stt_models[name] = WhisperModel(name, device=STT_DEVICE, compute_type="int8")
        log.info("STT model %r ready in %.1fs", name, time.time() - t0)
        return _stt_models[name]
    except Exception as exc:  # noqa: BLE001
        _stt_load_error[name] = f"{type(exc).__name__}: {exc}"
        log.error("STT model load failed: %s", _stt_load_error[name])
        raise RuntimeError(_stt_load_error[name])


# Back-compat alias (single-model callers)
_stt_model = None
_stt_lock = threading.Lock()


def _transcribe_wav_bytes(data: bytes, model_name: str = None) -> tuple:
    """Transcribe WAV bytes. Returns (text, wav_seconds, actual_provider_model)."""
    if not data or len(data) < 1000:
        return "", 0.0, "none"
    if data[:4] != b"RIFF" or len(data) > STT_MAX_BYTES:
        raise ValueError("reject: not a WAV payload or too large")
    requested_model = model_name or STT_MODEL_NAME
    # A single submitted chunk is transcribed by exactly one provider.  Groq
    # model fallback is attempted only when the primary request itself fails.
    groq_key = (os.environ.get("GROQ_API_KEY") or "").strip()
    use_groq = STT_PROVIDER in ("auto", "groq") and bool(groq_key) and requested_model != STT_PARTIAL_MODEL
    if use_groq:
        try:
            text, duration = _transcribe_groq_wav(data, requested_model, groq_key)
            return text, duration, f"groq:{requested_model}"
        except Exception as exc:  # noqa: BLE001
            log.warning("Groq STT primary %s failed: %s", requested_model, exc)
            if requested_model == STT_MODEL_NAME:
                try:
                    text, duration = _transcribe_groq_wav(data, STT_GROQ_FALLBACK_MODEL, groq_key)
                    return text, duration, f"groq:{STT_GROQ_FALLBACK_MODEL}"
                except Exception as fallback_exc:  # noqa: BLE001
                    log.warning("Groq STT fallback %s failed: %s", STT_GROQ_FALLBACK_MODEL, fallback_exc)
            if STT_PROVIDER == "groq":
                raise RuntimeError("Groq STT unavailable; local fallback disabled by JARVIS_STT_PROVIDER=groq") from exc
    # Offline fallback has separate model names: Groq's public names are not
    # faster-whisper model identifiers.
    local_model = (os.environ.get("JARVIS_LOCAL_STT_MODEL") or "base").strip() or "base"
    model = _get_stt_model(local_model if requested_model == STT_MODEL_NAME else requested_model)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        with _get_stt_lock(local_model if requested_model == STT_MODEL_NAME else requested_model):  # serialize per model
            segments, info = model.transcribe(tmp.name, language="en", beam_size=1,
                                              condition_on_previous_text=False)
            parts = [s.text for s in segments if s.text and s.text.strip()]
        return " ".join(parts).strip(), float(getattr(info, "duration", 0.0) or 0.0), f"local:{local_model}"
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _transcribe_groq_wav(data: bytes, model: str, api_key: str) -> tuple:
    """Use Groq's file transcription endpoint; callers own segmentation.

    This intentionally provides no fake streaming abstraction: partial and
    final requests are explicitly independent chunks managed by the browser's
    VoiceCaptureManager.
    """
    if not data or data[:4] != b"RIFF":
        raise ValueError("Groq STT accepts only valid WAV chunks")
    started = time.monotonic()
    response = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": ("utterance.wav", data, "audio/wav")},
        data={"model": model, "response_format": "json", "language": "en"},
        timeout=(5, 45),
    )
    if not response.ok:
        raise RuntimeError(f"Groq HTTP {response.status_code}: {response.text[:240]}")
    payload = response.json()
    text = str(payload.get("text") or "").strip()
    # WAV PCM duration comes from the header used by the client. Keep this
    # diagnostic only; never infer successful transcription from duration.
    duration = max(0.0, (len(data) - 44) / 32000)
    log.info("Groq STT model=%s completed in %.0fms", model, (time.monotonic() - started) * 1000)
    return text, duration


def _warmup_stt():
    try:
        # Do not mark Groq ready merely because a recognizer object exists.
        # Its authentication/model validation occurs on the first real audio
        # chunk, while local fallback can be warmed independently.
        local_model = (os.environ.get("JARVIS_LOCAL_STT_MODEL") or "base").strip() or "base"
        _get_stt_model(local_model)
        log.info("STT local fallback warmup complete (model=%s); provider=%s primary=%s",
                 local_model, STT_PROVIDER, STT_MODEL_NAME)
        try:
            _get_stt_model(STT_PARTIAL_MODEL)
            log.info("STT partial model ready (%s) — live interim words enabled", STT_PARTIAL_MODEL)
        except Exception as exc:  # noqa: BLE001
            log.warning("STT partial model unavailable (live words off, finals unaffected): %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("STT warmup failed (server transcription unavailable): %s", exc)


# ==========================================================================
# 3) WebSocket backend
# ==========================================================================

class Backend:
    def __init__(self) -> None:
        self.brain = Brain()
        self.memory = Memory()
        self.agent = ComputerAgent(self.brain, self.memory, request_permission=self.request_permission)
        self.task_store = TaskStore(ROOT / "memory" / "tasks.json")
        self.event_store = EventStore(ROOT / "memory" / "events.jsonl")
        self.world_state = WorldStateManager(DesktopObserver())
        self.context_fusion = ContextFusionEngine(self.world_state)
        self.requirements = RequirementDiscoveryEngine(self.context_fusion)
        self.browser = BrowserTool(headless=False)
        self.proactivity = ProactivityEngine(enabled=os.environ.get("JARVIS_PROACTIVE_NOTIFICATIONS", "0") == "1")
        self.project_requirements: dict = {}
        recovered_tasks = self.task_store.recover_interrupted()
        self.active_task_id: Optional[str] = recovered_tasks[-1]["task_id"] if recovered_tasks else None
        self.task_runs: dict[str, asyncio.Task] = {}
        self.capability_registry = CapabilityRegistry()
        self.capability_registry.register(Capability("filesystem", "Read and write authorized project files", availability="available"))
        self.capability_registry.register(Capability("terminal", "Run authorized development commands", executable="python"))
        register_development_tools(self.capability_registry)
        self.development_adapters = {
            name: DevelopmentToolAdapter(name, self.capability_registry.get(name).executable)
            for name in ("OpenCode", "Codex", "Antigravity")
            if self.capability_registry.get(name)
        }
        self.prompt_generator = TaskPromptGenerator()
        self.task_os = TaskOrchestrator()
        self.task_os_runs: dict[str, asyncio.Task] = {}
        self._task_os_perm_requests: dict[str, dict] = {}
        self._task_os_perm_futures: dict[str, asyncio.Future] = {}
        self.world_state.apply_event("TOOLS_CHANGED", {"tools": self.capability_registry.available()})
        self.routine = RoutineEngine()
        self.intel = ReminderIntel(self.routine)
        self._conv_history: list = []
        self.clients: set = set()
        self._lock = asyncio.Lock()
        self.stop = asyncio.Event()
        self._perm_future = None

    async def _send(self, ws, payload):
        try:
            await ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    async def _send_all(self, payload):
        raw = json.dumps(payload, ensure_ascii=False)
        async with self._lock:
            targets = list(self.clients)
        for ws in targets:
            try:
                await ws.send(raw)
            except Exception:
                pass

    async def _task_event(self, event: str, task_id: str, **details) -> None:
        record = self.event_store.append(event, task_id=task_id, **details)
        self.world_state.apply_event(event, record)
        await self._send_all({"type": "task_event", "task": record})
        task = self.task_store.get(task_id)
        if task:
            await self._send_all({"type": "task_snapshot", "task": task})
        await self._send_all({"type": "world_state", "state": self.world_state.snapshot()})
        await self._send_all({"type": "context_snapshot", "context": self.context_fusion.snapshot().to_dict()})
        decision = self.proactivity.evaluate(event, verified=event == "TASK_COMPLETED", user_available=True)
        await self._send_all({"type": "proactivity", "decision": decision.__dict__})
        if decision.action == "SPEAK" and event == "TASK_COMPLETED":
            await self._send_all({"type": "conversation", "text": "The task completed and passed its execution verification.", "voice_streaming": False})

    # --- TaskOS (Spec §1-§98): persistent autonomous task-owning system -------
    def _task_os_on_progress(self, payload: dict) -> None:
        try:
            asyncio.create_task(self._send_all({"type": "task_os_progress", **payload}))
        except Exception:
            pass

    def _task_os_on_permission(self, payload: dict) -> None:
        tid = payload.get("task_id")
        if tid:
            self._task_os_perm_requests[tid] = payload

    def _task_os_cancel_all(self) -> None:
        if self.task_os.active_task_id:
            try:
                self.task_os.cancel_task(self.task_os.active_task_id)
            except Exception:
                pass
        for fut in self._task_os_perm_futures.values():
            if not fut.done():
                try:
                    fut.set_result(False)
                except Exception:
                    pass
        for run in list(self.task_os_runs.values()):
            if not run.done():
                run.cancel()

    def _task_os_new_run(self, task_id: str) -> None:
        run = self.task_os_runs.get(task_id)
        if run is None or run.done():
            self.task_os_runs[task_id] = asyncio.ensure_future(self._task_os_run_loop(task_id))

    async def _task_os_run_loop(self, task_id: str) -> None:
        try:
            while True:
                task = await self.task_os.execute_task_loop(
                    task_id,
                    on_progress=self._task_os_on_progress,
                    on_permission_required=self._task_os_on_permission,
                )
                if task.status not in (TaskStatus.WAITING_FOR_PERMISSION, TaskStatus.READY):
                    break
                if task.status == TaskStatus.WAITING_FOR_PERMISSION:
                    req = self._task_os_perm_requests.pop(task_id, {})
                    await self._send_all({
                        "type": "task_os_permission",
                        "task_id": task_id,
                        "step_id": req.get("step_id", 0),
                        "prompt": req.get("prompt", "Authorization is required to continue this step."),
                    })
                    fut = self._task_os_perm_futures.get(task_id)
                    if fut is None or fut.done():
                        fut = asyncio.get_event_loop().create_future()
                        self._task_os_perm_futures[task_id] = fut
                    granted = await fut
                    self.task_os.grant_permission(task_id, bool(granted))
                    continue
            await self._deliver_task_os_final(task)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.error("[TaskOS] run loop error for %s: %s", task_id, exc)
            try:
                await self._send_all({"type": "task_os_error", "task_id": task_id, "error": str(exc)})
            except Exception:
                pass

    async def _deliver_task_os_final(self, task) -> None:
        status = task.status.value if task.status else TaskStatus.FAILED.value
        goal = task.goal
        if status == TaskStatus.COMPLETED.value:
            message = f"Sir, the task is complete and verified: '{goal}'."
        elif status == TaskStatus.BLOCKED.value:
            message = f"Sir, '{goal}' is waiting on your authorization before continuing."
        elif status == TaskStatus.CANCELLED.value:
            message = f"Sir, task '{goal}' was cancelled as requested."
        elif status == TaskStatus.PAUSED.value:
            message = f"Sir, task '{goal}' is paused. Say continue when ready."
        elif status == TaskStatus.FAILED.value:
            reason = (task.errors or ["unknown reason"])[-1]
            message = f"Sir, '{goal}' hit a blocker: {reason}. I stopped rather than guess."
        else:
            message = f"Sir, task '{goal}' is now in state {status}."
        try:
            await self._send_all({"type": "task_os_final", "task_id": task.task_id, "status": status, "goal": goal})
            if status in (TaskStatus.COMPLETED.value, TaskStatus.BLOCKED.value, TaskStatus.FAILED.value):
                await self._send_all({"type": "conversation", "text": message, "voice_streaming": False})
                await self._send_all({"type": "done", "text": ""})
        except Exception:
            pass

    def _task_os_goal_phrase(self, text: str) -> bool:
        low = text.lower()
        triggers = (
            "find a small business", "find me a small local business", "find me a local business",
            "find a local business", "find a business that would benefit",
            "business that would benefit", "benefit from a website", "find a business and",
            "find a business", "outreach and website",
        )
        return any(t in low for t in triggers)

    def _hook_task_os_control(self, text: str):
        """Return (message, handled) when the user's words steer the active TaskOS objective."""
        task_id = self.task_os.active_task_id
        if not task_id:
            return None
        task = self.task_os.tasks.get(task_id)
        if not task:
            return None
        low = text.lower().strip()
        if low in ("continue", "resume", "go on", "keep going") and task.status in (
            TaskStatus.PAUSED, TaskStatus.BLOCKED, TaskStatus.WAITING_FOR_PERMISSION,
        ):
            self.task_os.resume_task(task_id)
            self._task_os_new_run(task_id)
            return ("Resuming the active objective, sir.", True)
        res = self.task_os.handle_user_instruction(text, task_id=task_id)
        acted = res.get("action") in ("cancelled", "paused", "status", "updated")
        return (res.get("message", ""), bool(acted))

    async def _handle_task_os(self, ws, msg) -> None:
        action = msg.get("action")
        if action == "accept":
            goal = (msg.get("goal") or "").strip()
            if not goal:
                await self._send(ws, {"type": "error", "text": "task_os accept requires a goal"})
                return
            task = self.task_os.accept_goal(goal, request_id=msg.get("request_id", ""), priority=msg.get("priority", "NORMAL"))
            self._task_os_new_run(task.task_id)
            await self._send_all({"type": "task_os_started", "task": task.to_dict(),
                                  "message": f"Understood, sir. I've chartered the objective with {task.total_steps} verified steps."})
            await self._send_all({"type": "done", "text": ""})
            return
        if action == "status":
            tid = msg.get("task_id") or self.task_os.active_task_id
            task = self.task_os.tasks.get(tid) if tid else None
            if task:
                summary = self.task_os.journal.generate_status_summary(task.task_id, goal=task.goal)
                await self._send(ws, {"type": "task_os_text", "task_id": tid, "status": task.status.value,
                                      "text": summary, "completed": len(task.completed_steps), "total": task.total_steps})
            else:
                await self._send(ws, {"type": "task_os_text", "text": "No task is currently active, sir."})
            return
        if action == "instruction":
            res = self.task_os.handle_user_instruction(msg.get("text", ""), task_id=msg.get("task_id"))
            await self._send_all({"type": "conversation", "text": res.get("message", ""), "voice_streaming": False})
            await self._send_all({"type": "done", "text": ""})
            return
        if action == "permission":
            target = msg.get("task_id") or self.task_os.active_task_id
            if target:
                self.task_os.grant_permission(target, bool(msg.get("granted", False)))
                fut = self._task_os_perm_futures.get(target)
                if fut and not fut.done():
                    fut.set_result(bool(msg.get("granted", False)))
            else:
                await self._send(ws, {"type": "error", "text": "no active task to authorize"})
            return
        if action == "pause":
            tid = msg.get("task_id") or self.task_os.active_task_id
            if tid and self.task_os.tasks.get(tid):
                self.task_os.pause_task(tid)
                await self._send_all({"type": "task_os_text", "text": "Task paused as requested, sir."})
            return
        if action == "resume":
            tid = msg.get("task_id") or self.task_os.active_task_id
            if tid and self.task_os.resume_task(tid):
                self._task_os_new_run(tid)
                await self._send_all({"type": "task_os_text", "text": "Resuming the task, sir."})
            return
        if action == "cancel":
            self._task_os_cancel_all()
            await self._send_all({"type": "task_os_text", "text": "Task cancelled as requested, sir."})
            return
        await self._send(ws, {"type": "error", "text": f"unknown task_os action {action}"})

    async def _world_event(self, event: str, **details) -> None:
        record = self.event_store.append(event, **details)
        self.world_state.apply_event(event, record)
        await self._send_all({"type": "world_event", "event": record})
        await self._send_all({"type": "world_state", "state": self.world_state.snapshot()})
        await self._send_all({"type": "context_snapshot", "context": self.context_fusion.snapshot().to_dict()})

    async def _cancel_active_task(self, reason: str = "user_cancelled") -> None:
        task_id = self.active_task_id
        if not task_id:
            return
        run = self.task_runs.get(task_id)
        if run and not run.done():
            run.cancel()
        task = self.task_store.get(task_id)
        if task and task.get("status") not in {"completed_verified", "failed", "cancelled"}:
            self.task_store.update(task_id, cancellation_reason=reason)
            self.task_store.transition(task_id, "cancelled")
            await self._task_event("USER_INTERRUPTED", task_id, reason=reason, status="cancelled")
        self.active_task_id = None

    async def _pause_active_task(self) -> None:
        task_id = self.active_task_id
        task = self.task_store.get(task_id) if task_id else None
        if not task:
            return
        run = self.task_runs.get(task_id)
        if run and not run.done():
            run.cancel()
        if task.get("status") not in {"completed_verified", "failed", "cancelled", "paused"}:
            self.task_store.transition(task_id, "paused")
            await self._task_event("TASK_PAUSED", task_id, status="paused")

    async def _resume_active_task(self) -> bool:
        task_id = self.active_task_id
        task = self.task_store.get(task_id) if task_id else None
        if not task or task.get("status") not in {"paused", "recovery_required", "waiting_for_user"}:
            return False
        self.task_store.transition(task_id, "ready")
        await self._task_event("TASK_RESUMED", task_id, status="ready", next_action=task.get("next_action"))
        return True

    async def _begin_parent_task(self, goal: str, context: Any, discovery: Any) -> str:
        if self.active_task_id:
            current = self.task_store.get(self.active_task_id)
            if current and current.get("status") not in {"completed_verified", "failed", "cancelled"}:
                return self.active_task_id
        steps = [
            {"id": "discovery", "title": "Understand the referenced business"},
            {"id": "requirements", "title": "Resolve high-value website requirements"},
            {"id": "project", "title": "Create and verify the project directory"},
            {"id": "tool", "title": "Select and verify a development environment"},
            {"id": "implementation", "title": "Submit the implementation prompt and monitor work"},
            {"id": "verification", "title": "Build, test, and verify the finished site"},
        ]
        task = self.task_store.create(goal, steps=steps)
        self.active_task_id = task["task_id"]
        self.task_store.update(self.active_task_id, context=context.to_dict(), requirements=discovery.to_dict())
        self.task_store.transition(self.active_task_id, "understanding")
        await self._task_event("TASK_CREATED", self.active_task_id, goal=goal, status="understanding")
        self.task_store.transition(self.active_task_id, "waiting_for_user")
        await self._task_event("TASK_WAITING_FOR_USER", self.active_task_id, status="waiting_for_user", questions=discovery.questions)
        return self.active_task_id

    async def context_loop(self) -> None:
        last_window = None
        last_browser = None
        try:
            while not self.stop.is_set():
                window = await asyncio.to_thread(self.world_state.observer.get_active_window_info)
                window_key = (window.get("title", ""), window.get("application", ""))
                if window_key != last_window:
                    last_window = window_key
                    await self._world_event("ACTIVE_WINDOW_CHANGED", **window)

                browser_result = await asyncio.to_thread(self.browser.inspect_current_page)
                if browser_result.success:
                    page = browser_result.output
                    browser_key = (page.get("target_id", ""), page.get("url", ""), page.get("title", ""), page.get("text", ""))
                    if browser_key != last_browser:
                        event = "BROWSER_TAB_CHANGED" if last_browser is None or browser_key[:1] != last_browser[:1] else "PAGE_CONTEXT_CHANGED"
                        last_browser = browser_key
                        await self._world_event(event, **page, confidence=0.95, availability="available")
                elif last_browser is not None:
                    last_browser = None
                    await self._world_event("BROWSER_TAB_CHANGED", active=False, availability="unavailable", confidence=0.0)
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    async def handler(self, ws, *args):
        async with self._lock:
            self.clients.add(ws)
        try:
            await self._send(ws, {"type": "welcome", "server": "jarvis-singlefile",
                                  "version": "1.0.0", "ts": time.time(),
                                  "build": BUILD_ID, "caps": BACKEND_CAPS})
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    await self._send(ws, {"type": "error", "code": "malformed"})
                    continue
                await self.dispatch(ws, msg)
        except Exception:
            pass
        finally:
            async with self._lock:
                self.clients.discard(ws)

    async def dispatch(self, ws, msg):
        mtype = msg.get("type")
        if mtype == "permission":
            if self._perm_future is not None and not self._perm_future.done():
                self._perm_future.set_result(bool(msg.get("granted")))
            return
        if mtype == "voice_diag":
            # Frontend microphone/audio-graph evidence. This is intentionally
            # telemetry-only: it never triggers an AI task or changes state.
            log.info("[VOICE_TRACE] FRONTEND_DIAG state=%s permission=%s audio_active=%s frames=%s severity=%s detail=%s",
                     msg.get("state"), msg.get("permission"), msg.get("audio_active"),
                     msg.get("frame_count"), msg.get("severity"), msg.get("detail"))
            return
        if mtype == "task_os":
            await self._handle_task_os(ws, msg)
            return
        if mtype in ("hello", "state.sync", "visibility_changed", "character_change"):
            if mtype == "hello":
                log.info("[WS] hello from %s — sending welcome + routine + reminders", ws.remote_address if hasattr(ws, 'remote_address') else 'client')
                await self._send(ws, {"type": "welcome_ack", "ts": time.time()})
            # Push authoritative routine + reminder state to the (re)connecting client.
            await self._send(ws, {"type": "routine", "state": self.routine.compute_state()})
            await self._send(ws, {"type": "reminders", "list": self.routine.get_reminders()})
            await self._send(ws, {"type": "world_state", "state": self.world_state.snapshot()})
            await self._send(ws, {"type": "context_snapshot", "context": self.context_fusion.snapshot().to_dict()})
            g = self.routine.get_greeting_if_due()
            if g:
                await self._send(ws, g)
            return
        if mtype == "cancel" or mtype == "stop":
            # Global cancellation (spec section 50) — immediate, no questions asked.
            from agent import WATCHDOG as _WATCH
            try:
                _WATCH.release_all()
            except Exception:
                pass
            await self._cancel_active_task("user_cancelled")
            self._task_os_cancel_all()
            await self._send_all({"type": "state", "status": "cancelled"})
            await self._send_all({"type": "conversation", "text": "Stopped, sir.", "voice_streaming": False})
            await self._send_all({"type": "done", "text": ""})
            return
        if mtype == "stt_ping":
            # Round-trip proof that this backend speaks the voice contract.
            await self._send(ws, {"type": "stt_pong", "req_id": msg.get("req_id"),
                                  "build": BUILD_ID, "caps": BACKEND_CAPS})
            return
        if mtype == "stt_partial":
            # LIVE interim words while the user is still speaking. Fast tiny
            # model; fire-and-forget (no watchdog — finals are authoritative).
            req_id = msg.get("req_id")
            try:
                b64 = msg.get("audio_b64") or ""
                if len(b64) > (STT_MAX_BYTES * 4) // 3 + 64:
                    raise ValueError("reject: audio payload too large")
                raw = base64.b64decode(b64, validate=True)
                text, _, actual_model = await asyncio.to_thread(_transcribe_wav_bytes, raw, STT_PARTIAL_MODEL)
                await self._send(ws, {"type": "stt_partial_result", "req_id": req_id,
                                      "utt": msg.get("utt"), "text": text, "model": actual_model})
            except Exception as exc:  # partials are best-effort; final survives
                log.warning("[WS] stt_partial %s failed: %s", req_id, exc)
            return
        if mtype == "stt_audio":
            # Server-side transcription for HUD runtimes without Web Speech API.
            # Payload: {type:'stt_audio', req_id, audio_b64 (16 kHz mono WAV), sample_rate}
            req_id = msg.get("req_id")
            trace = {key: msg.get(key) for key in ("session_id", "turn_id") if msg.get(key)}
            t0 = time.time()
            try:
                if req_id and req_id in _stt_recent_results:
                    cached = _stt_recent_results[req_id]
                    log.info("[WS] stt_audio %s duplicate (retry) -> cached result resent", req_id)
                    await self._send(ws, {"type": "stt_result", "req_id": req_id, **trace,
                                          "text": cached["text"], "wav_seconds": cached["wav_seconds"],
                                          "latency_ms": 0, "model": cached["model"],
                                          "sentinel": bool(msg.get("sentinel")), "cached": True})
                    return
                b64 = msg.get("audio_b64") or ""
                if len(b64) > (STT_MAX_BYTES * 4) // 3 + 64:
                    raise ValueError("reject: audio payload too large")
                raw = base64.b64decode(b64, validate=True)
                text, dur, actual_model = await asyncio.to_thread(_transcribe_wav_bytes, raw)
                log.info("[WS] stt_audio %s -> %r (wav %.1fs, took %.1fs)",
                         req_id, text[:120], dur, time.time() - t0)
                if req_id:
                    _stt_recent_results[req_id] = {"text": text, "wav_seconds": round(dur, 2),
                                                   "model": actual_model}
                    while len(_stt_recent_results) > _STT_RECENT_MAX:
                        _stt_recent_results.pop(next(iter(_stt_recent_results)))
                await self._send(ws, {"type": "stt_result", "req_id": req_id, **trace,
                                      "text": text, "wav_seconds": round(dur, 2),
                                      "latency_ms": int((time.time() - t0) * 1000),
                                      "model": actual_model,
                                      "sentinel": bool(msg.get("sentinel"))})
            except Exception as exc:  # noqa: BLE001
                log.warning("[WS] stt_audio %s failed: %s", req_id, exc)
                await self._send(ws, {"type": "stt_error", "req_id": req_id, **trace,
                                      "error": "transcription failed"})
            return
        if mtype in ("command", "chat"):
            text = (msg.get("text") or "").strip()
            log.info("[WS] command/chat received: %r via_jarvis=%s", text[:120], msg.get("via_jarvis"))
            if text:
                log.info("[VOICE_TRACE] AI_REQUEST_RECEIVED req=%s session=%s turn=%s text=%r",
                         msg.get("req_id"), msg.get("session_id"), msg.get("turn_id"), text[:120])
                await self._world_event("TRANSCRIPT_FINAL", text=text, permission="granted", confidence=1.0)
                context = self.context_fusion.snapshot(text)
                if self._task_os_goal_phrase(text):
                    task = self.task_os.accept_goal(text, request_id=f"REQ-{int(time.time()) % 10000:04d}")
                    self._task_os_new_run(task.task_id)
                    await self._send_all({"type": "task_os_started", "task": task.to_dict(),
                                          "message": f"Understood, sir. I've chartered a {task.total_steps}-step objective and begun executing."})
                    await self._send_all({"type": "done", "text": ""})
                    return
                if self.task_os.active_task_id:
                    hook = self._hook_task_os_control(text)
                    if hook is not None:
                        message, acted = hook
                        if acted:
                            await self._send_all({"type": "conversation", "text": message, "voice_streaming": False})
                            await self._send_all({"type": "done", "text": ""})
                            return
                if context.user_intent == "build_website":
                    discovery = self.requirements.discover(text, context)
                    self.project_requirements = discovery.to_dict()
                    self.project_requirements["business_context"] = context.referenced_entity
                    task_id = await self._begin_parent_task(text, context, discovery)
                    await self._send_all({"type": "requirements", "requirements": self.project_requirements})
                    await self._send_all({"type": "task_state", "task_id": task_id, "status": "waiting_for_user", "next_action": "answer_high_value_requirements"})
                    await self._send_all({"type": "conversation", "text": "I have the current business context. Before I build, I need the highest-impact choices: the visual direction, the site's main goal, and whether you need reservations or online ordering.", "voice_streaming": False})
                    await self._send_all({"type": "done", "text": ""})
                    return
                elif self.project_requirements:
                    self._update_requirements_from_answer(text)
                    await self._send_all({"type": "requirements", "requirements": self.project_requirements})
                    normalized = text.lower().strip()
                    if normalized in ("continue", "resume", "go on"):
                        await self._resume_active_task()
                        return
                    requested_tool = next((name for name in ("OpenCode", "Codex", "Antigravity") if name.lower() in normalized), None)
                    if requested_tool and self.active_task_id:
                        capability = self.capability_registry.detect(requested_tool)
                        if capability and capability.availability == "available":
                            self.task_store.update(self.active_task_id, selected_tool=requested_tool)
                            await self._continue_with_development_tool(requested_tool)
                        else:
                            self.task_store.transition(self.active_task_id, "blocked")
                            await self._task_event("TASK_BLOCKED", self.active_task_id, status="blocked", reason=f"{requested_tool} unavailable")
                            available = [name for name in self.capability_registry.available() if name in ("OpenCode", "Codex", "Antigravity")]
                            alternatives = ", ".join(available) or "none"
                            await self._send_all({"type": "conversation", "text": f"{requested_tool} is not available on this machine. Detected alternatives: {alternatives}.", "voice_streaming": False})
                        await self._send_all({"type": "done", "text": ""})
                        return
                    if self.active_task_id:
                        await self._send_all({"type": "conversation", "text": "Got it. I updated the active task requirements and kept the next verified step pending.", "voice_streaming": False})
                        await self._send_all({"type": "done", "text": ""})
                        return
            # Voice diagnostics command (professional voice isolation check)
            low = text.lower()
            if any(k in low for k in ("voice diagnostics", "voice diagnostic", "audio diagnostics", "mic diagnostics")):
                try:
                    # Truthful live-architecture report (HUD owns mic/STT frontend,
                    # this backend owns Whisper STT + LLM + Fish TTS gateway check).
                    diag_lines = ["JARVIS Voice Diagnostics (live):"]
                    # Backend (Groq/Gemini) status — live probe, cached by /api_status loop
                    try:
                        b = self.brain.verify() if hasattr(self.brain, "verify") else {"groq": "unknown"}
                        diag_lines.append(f"Brain ........ {b.get('active','?')} ({b})")
                    except Exception as e:
                        diag_lines.append(f"Brain ........ error: {e}")
                    # Microphones visible to this machine (HUD captures via browser)
                    try:
                        import pyaudio
                        pa = pyaudio.PyAudio()
                        try:
                            di = pa.get_default_input_device_info()
                            diag_lines.append(f"Default mic .. {di.get('name','?')} (index {di.get('index','?')})")
                            n = pa.get_device_count()
                            ins = [pa.get_device_info_by_index(i).get('name','?')
                                   for i in range(n)
                                   if pa.get_device_info_by_index(i).get('maxInputChannels', 0) > 0][:4]
                            diag_lines.append(f"Input devs ... {', '.join(ins) or 'none'}")
                        finally:
                            pa.terminate()
                    except Exception as e:
                        diag_lines.append(f"Microphones .. error: {type(e).__name__}")
                    # Server STT (authoritative transcriber for Electron HUD)
                    try:
                        local_name = (os.environ.get("JARVIS_LOCAL_STT_MODEL") or "base").strip() or "base"
                        loaded = "loaded" if _stt_models.get(local_name) is not None else "lazy (loads on first utterance)"
                        ploaded = "loaded" if _stt_models.get(STT_PARTIAL_MODEL) is not None else "lazy"
                        diag_lines.append(f"Server STT ... provider={STT_PROVIDER} primary={STT_MODEL_NAME} local-fallback={local_name} [{loaded}] live={STT_PARTIAL_MODEL} [{ploaded}] device={STT_DEVICE}")
                    except Exception as e:
                        diag_lines.append(f"Server STT ... error: {e}")
                    # Fish TTS gateway (authoritative voice)
                    try:
                        import urllib.request as _ur
                        with _ur.urlopen("http://127.0.0.1:8766/health", timeout=3) as resp:
                            import json as _js
                            h = _js.loads(resp.read(1024).decode("utf-8", "replace"))
                        diag_lines.append(f"Fish TTS ..... {h.get('status','?')} voice={str(h.get('voice','?'))[:8]}... char={h.get('character','?')}")
                    except Exception:
                        diag_lines.append("Fish TTS ..... UNREACHABLE on 127.0.0.1:8766 (start: python start_voice.py)")
                    # Voice ownership (the real architecture)
                    diag_lines.append("Mic owner .... HUD only (ServerSTT in Electron, Web Speech in browser)")
                    diag_lines.append("STT .......... backend faster-whisper via WS stt_audio (no wake word in session)")
                    report = "\n".join(diag_lines)
                    await self._send_all({"type": "conversation", "text": report, "voice_streaming": False})
                    await self._send_all({"type": "done", "text": ""})
                    return
                except Exception as exc:
                    await self._send_all({"type": "conversation", "text": f"Diagnostics failed: {exc}", "voice_streaming": False})
                    await self._send_all({"type": "done", "text": ""})
                    return
            # Global "Stop" spoken as a command must also cancel immediately.
            low_text = text.strip().lower()
            if low_text in ("stop", "stop jarvis", "cancel", "abort", "halt", "pause", "wait", "hold on", "don't do that", "stop that", "stand down", "quiet"):
                from agent import WATCHDOG as _WATCH2
                try:
                    _WATCH2.release_all()
                except Exception:
                    pass
                if low_text in ("pause", "wait", "hold on"):
                    await self._pause_active_task()
                    status = "paused"
                    message = "Paused. I kept the task state and will resume from the last verified step."
                else:
                    await self._cancel_active_task("user_cancelled")
                    status = "cancelled"
                    message = "Stopped, sir. The completed work is preserved."
                await self._send_all({"type": "state", "status": status})
                await self._send_all({"type": "conversation", "text": message, "voice_streaming": False})
                await self._send_all({"type": "done", "text": ""})
                return
            # Developer test mode: fire a reminder in 10s to exercise the
            # full trigger pipeline (sound + animation + voice) without waiting.
            if text.upper() == "REMINDER_IN_10_SECONDS":
                r = self.routine.create_test_reminder(10, "Dev Test Reminder")
                await self._send_all({"type": "reminders", "list": self.routine.get_reminders()})
                await self._send_all({"type": "reminder_created", "reminder": r,
                                      "list": self.routine.get_reminders()})
                await self._send_all({"type": "conversation",
                                      "text": "Reminder set for the dev test, sir. It will trigger in 10 seconds.",
                                      "voice_streaming": False})
                await self._send_all({"type": "done", "text": ""})
                return
            # 1) Conversation-reminder mode toggle (OFF / CONFIRM / AUTO).
            mode = self.intel.detect_mode_command(text)
            if mode:
                self.routine.set_conversation_mode(mode)
                await self._send_all({"type": "conversation",
                                      "text": f"Understood, sir. Conversation-based reminders are now {mode}.",
                                      "voice_streaming": False})
                await self._send_all({"type": "done", "text": ""})
                return
            # 2) Explicit "remind me ..." style commands (deterministic, no LLM).
            intent_reply = self.routine.handle_intent(text)
            if intent_reply:
                await self._send_all({"type": "conversation", "text": intent_reply, "voice_streaming": False})
                await self._send_all({"type": "reminders", "list": self.routine.get_reminders()})
                await self._send_all({"type": "routine", "state": self.routine.compute_state()})
                await self._send_all({"type": "done", "text": ""})
                return
            # 3) Implicit conversational reminder detection (the intelligence).
            self._conv_history.append(text)
            self._conv_history = self._conv_history[-8:]
            result = self.intel.process_message(text, history=self._conv_history[:-1])
            note = None
            if result and result.get("action") not in (None, "none"):
                note = await self._apply_intel(result)
            # 4) Continue the normal conversation (Groq) with an optional note
            #    so JARVIS can weave the reminder action into its reply.
            await self.handle_command(text, note=note,
                                      character=(msg.get("character") or "IRON_MAN"),
                                      request_id=msg.get("req_id"))
            return
        if mtype == "direct_action":
            action = (msg.get("action") or msg.get("intent") or "")
            params = msg.get("params") or {}
            phrase = f"{action} {params}".strip()
            reply = _direct_action(phrase) or f"Action {action} acknowledged."
            await self._send_all({"type": "conversation", "text": reply, "voice_streaming": False})
            await self._send_all({"type": "done", "text": ""})
            return
        if mtype == "routine":
            await self._handle_routine(ws, msg)
            return
        if mtype == "reminder":
            await self._handle_reminder(ws, msg)
            return
        if mtype == "greeting_ack":
            self.routine.ack_greeting(msg.get("date") or "")
            return
        log.debug("Unhandled message type: %r", mtype)

    # ----- Routine / Reminder message handlers -----------------------
    async def _handle_routine(self, ws, msg):
        action = msg.get("action") or msg.get("cmd")
        try:
            if action == "get" or action is None:
                await self._send(ws, {"type": "routine", "state": self.routine.compute_state()})
            elif action == "override":
                st = self.routine.apply_override(msg.get("block_id"), msg.get("op") or msg.get("override_action"), **(msg.get("params") or {}))
                await self._send_all({"type": "routine", "state": st})
            elif action == "set_mode":
                st = self.routine.set_completion_mode(msg.get("mode"))
                await self._send_all({"type": "routine", "state": st})
            elif action == "completion":
                st = self.routine.completion_response(msg.get("block_id"), msg.get("outcome", "good"))
                await self._send_all({"type": "routine", "state": st})
            elif action == "resume":
                st = self.routine.resume()
                await self._send_all({"type": "routine", "state": st})
            else:
                await self._send(ws, {"type": "error", "text": f"unknown routine action {action}"})
        except Exception as exc:  # noqa: BLE001
            await self._send(ws, {"type": "error", "text": f"routine error: {exc}"})

    async def _handle_reminder(self, ws, msg):
        action = msg.get("action") or msg.get("cmd")
        try:
            if action == "list" or action is None:
                await self._send(ws, {"type": "reminders", "list": self.routine.get_reminders()})
            elif action == "create":
                r = self.routine.create_reminder(msg.get("time"), msg.get("topic"),
                                                repeat=msg.get("repeat", "none"),
                                                category=msg.get("category", ""),
                                                source=msg.get("source", "MANUAL"),
                                                date=msg.get("date"))
                await self._send_all({"type": "reminders", "list": self.routine.get_reminders()})
                await self._send_all({"type": "reminder_created", "reminder": r,
                                      "list": self.routine.get_reminders()})
            elif action == "update":
                self.routine.update_reminder(msg.get("id"), **{k: msg[k] for k in ("time", "topic", "enabled", "repeat", "category") if k in msg})
                await self._send_all({"type": "reminders", "list": self.routine.get_reminders()})
            elif action == "delete":
                self.routine.delete_reminder(msg.get("id"))
                await self._send_all({"type": "reminders", "list": self.routine.get_reminders()})
            elif action == "ack":
                self.routine.ack_reminder(msg.get("id"), msg.get("event_id", ""), msg.get("status", "dismissed"))
                await self._send_all({"type": "reminders", "list": self.routine.get_reminders()})
            else:
                await self._send(ws, {"type": "error", "text": f"unknown reminder action {action}"})
        except Exception as exc:  # noqa: BLE001
            await self._send(ws, {"type": "error", "text": f"reminder error: {exc}"})

    async def request_permission(self, prompt: str) -> bool:
        # Auto-grant — user requested JARVIS execute directly without permission step.
        return True

    async def handle_command(self, text: str, note: str = None, character: str = "IRON_MAN", request_id: str = None) -> None:
        if not text:
            return
        t = text.lower().strip()
        if t in ("doctor", "health", "healthcheck", "system check", "diag"):
            checks = agent_doctor()
            lines = ["J.A.R.V.I.S. system check:"]
            for c in checks:
                lines.append(f"  [{'OK' if c['ok'] else 'FAIL'}] {c['name']} {c.get('info', '')}")
            report = "\n".join(lines)
            await self._send_all({"type": "conversation", "text": report, "voice_streaming": False})
            await self._send_all({"type": "done", "text": ""})
            return
        if any(phrase in t for phrase in ("how's it going", "hows it going", "task status", "what am i working on")):
            task = self.task_store.get(self.active_task_id) if self.active_task_id else None
            if task:
                next_action = task.get("next_action") or "final verification"
                response = f"The task is {task.get('status')}. Next verified step: {next_action.get('title', next_action) if isinstance(next_action, dict) else next_action}."
            else:
                response = "There is no active parent task."
            await self._send_all({"type": "conversation", "text": response, "voice_streaming": False})
            await self._send_all({"type": "done", "text": ""})
            return
        # Everything else is routed through the real execution agent.
        asyncio.create_task(self._run_agent(text, note=note, character=character, request_id=request_id))

    async def _apply_intel(self, result: dict) -> Optional[str]:
        """Persist the conversational reminder outcome and push HUD events.

        Returns a short `note` string the conversation layer can use to make
        JARVIS acknowledge the action naturally (never claim creation before
        it actually succeeded).
        """
        note = None
        if result.get("created"):
            for r in result["created"]:
                await self._send_all({"type": "reminder_created", "reminder": r,
                                      "list": self.routine.get_reminders()})
            topics = ", ".join(f"{r['topic']} at {r['time']}" for r in result["created"])
            note = (f"You just set a reminder for {topics}. Briefly and naturally "
                    f"acknowledge it within your reply; do not say 'reminder created' "
                    f"like a robot.")
        elif result.get("updated"):
            for r in result["updated"]:
                await self._send_all({"type": "reminder_updated", "reminder": r,
                                      "list": self.routine.get_reminders()})
            topics = ", ".join(f"{r['topic']} at {r['time']}" for r in result["updated"])
            note = f"You just updated a reminder to {topics}. Briefly acknowledge it naturally."
        elif result.get("clarify"):
            c = result["clarify"]
            await self._send_all({"type": "reminder_suggest", "mode": "clarify",
                                  "candidate": c, "list": self.routine.get_reminders()})
            note = (f"Ask the user a short question about what time their "
                    f"{c.get('topic', 'event')} is. Do not assume a time.")
        elif result.get("suggest"):
            c = result["suggest"]
            await self._send_all({"type": "reminder_suggest", "mode": "confirm",
                                  "candidate": c, "list": self.routine.get_reminders()})
            note = (f"The user may want a reminder for {c.get('topic')} at {c.get('time')}. "
                    f"Politely ask if they would like you to set it.")
        return note

    def _update_requirements_from_answer(self, text: str) -> None:
        lowered = text.lower()
        confirmed = self.project_requirements.setdefault("confirmed", [])
        unknown = self.project_requirements.setdefault("unknown", [])
        if "premium" in lowered or "minimal" in lowered or "warm" in lowered or "cozy" in lowered:
            style = "premium" if "premium" in lowered else "warm/local" if "warm" in lowered or "cozy" in lowered else "modern minimal"
            confirmed[:] = [item for item in confirmed if not item.startswith("design direction:")]
            confirmed.append(f"design direction: {style}")
            unknown[:] = [item for item in unknown if item != "design direction"]
        if "reservation" in lowered or "booking" in lowered:
            confirmed.append("reservations: enabled")
            unknown[:] = [item for item in unknown if item != "required business features"]
        if "no online ordering" in lowered or "without online ordering" in lowered:
            confirmed.append("online ordering: disabled")
        elif "online ordering" in lowered or "ordering" in lowered:
            confirmed.append("online ordering: enabled")
            unknown[:] = [item for item in unknown if item != "required business features"]

    async def _continue_with_development_tool(self, tool_name: str) -> None:
        task_id = self.active_task_id
        if not task_id:
            return
        task = self.task_store.get(task_id)
        adapter = self.development_adapters.get(tool_name)
        if not task or not adapter:
            return
        title = (self.project_requirements.get("business_context") or {}).get("title") or "website"
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "website"
        project_dir = ROOT / "projects" / f"{slug}-website"
        try:
            project_dir.mkdir(parents=True, exist_ok=True)
            if not project_dir.is_dir():
                raise OSError("project directory was not created")
        except OSError as exc:
            self.task_store.transition(task_id, "blocked")
            await self._task_event("TASK_BLOCKED", task_id, status="blocked", reason=str(exc))
            return
        self.task_store.add_artifact(task_id, {"type": "project_directory", "path": str(project_dir), "verified": True})
        self.task_store.checkpoint(task_id, 1)
        self.task_store.update(task_id, selected_tool=tool_name, project_path=str(project_dir))
        await self._task_event("PROJECT_CREATED", task_id, path=str(project_dir), verified=True)

        launch = adapter.launch(project_dir)
        if not launch.get("verified"):
            self.task_store.transition(task_id, "blocked")
            await self._task_event("TASK_BLOCKED", task_id, status="blocked", reason=launch.get("error", "tool launch not verified"))
            return
        self.task_store.transition(task_id, "executing")
        await self._task_event("TOOL_OPENED", task_id, tool=tool_name, pid=launch.get("pid"), workspace=str(project_dir))
        prompt = self.prompt_generator.generate(
            task["goal"],
            self.context_fusion.snapshot().to_dict(),
            self.project_requirements,
            tool_name,
        )
        submission = adapter.send_instruction(prompt)
        if not submission.get("verified"):
            self.task_store.transition(task_id, "waiting_for_permission")
            await self._task_event("PROMPT_SUBMISSION_UNVERIFIED", task_id, status="waiting_for_permission", tool=tool_name)
            await self._send_all({"type": "conversation", "text": f"{tool_name} is open and the workspace is verified, but its prompt acceptance is not yet verifiable through the available adapter. I have paused before claiming the build started.", "voice_streaming": False})

    async def _run_agent(self, text: str, note: str = None, character: str = "IRON_MAN", request_id: str = None) -> None:
        task = self.task_store.create(text, total_steps=1)
        task_id = task["task_id"]
        request_id = request_id or str(uuid.uuid4())
        self.task_store.transition(task_id, "planning")
        await self._task_event("TASK_STARTED", task_id, request_id=request_id, goal=text)
        await self._send_all({"type": "task_state", "task_id": task_id, "status": "planning", "goal": text})
        try:
            prompt = text
            if note:
                prompt = f"{text}\n[System note for JARVIS only: {note}]"
            self.task_store.transition(task_id, "executing")
            await self._task_event("TASK_EXECUTING", task_id, request_id=request_id)
            log.info("[VOICE_TRACE] AI_MODEL_CALLED req=%s task=%s character=%s", request_id, task_id, character)
            result = await self.agent.run(prompt, self._send_all, character=character)
            log.info("[VOICE_TRACE] AI_RESPONSE_RECEIVED req=%s task=%s chars=%d", request_id, task_id, len(result or ""))
            failed = bool(re.search(r"(?i)\b(fail|could not|unable|error|blocked|not found)\b", result or ""))
            if failed:
                self.task_store.transition(task_id, "failed")
                await self._task_event("TASK_FAILED", task_id, request_id=request_id, result=result)
                await self._send_all({"type": "task_state", "task_id": task_id, "status": "failed", "goal": text})
                return
            self.task_store.transition(task_id, "verifying")
            await self._task_event("TASK_VERIFYING", task_id, request_id=request_id)
            self.task_store.transition(task_id, "completed_verified")
            await self._task_event("TASK_COMPLETED", task_id, request_id=request_id, result=result)
            log.info("[VOICE_TRACE] AI_RESPONSE_SENT req=%s task=%s", request_id, task_id)
            await self._send_all({"type": "task_state", "task_id": task_id, "status": "completed_verified", "goal": text})
        except Exception as exc:  # noqa: BLE001
            log.error("Agent fault: %s", exc)
            try:
                self.task_store.transition(task_id, "failed")
            except Exception:
                pass
            await self._task_event("TASK_FAILED", task_id, request_id=request_id, error=str(exc)[:200])
            await self._send_all({"type": "task_state", "task_id": task_id, "status": "failed", "goal": text})
            await self._send_all({"type": "error", "text": "Agent fault: " + str(exc)[:200]})
            await self._send_all({"type": "done", "text": ""})

    async def heartbeat(self):
        try:
            while not self.stop.is_set():
                await self._send_all({"type": "system_status", "ts": time.time(), "healthy": True})
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass

    # ----- Daily Routine + Reminder scheduler -------------------------
    async def routine_loop(self):
        """Deterministic scheduler. Emits routine/reminder/greeting events.

        Besides transitions, we periodically re-push the authoritative routine
        + reminder state so the HUD's live countdown always reflects the real
        schedule (covers gaps, overrides, midnight reset, reconnect drift)
        without relying on the browser to infer anything.
        """
        last_state_push = 0.0
        last_reminder_push = 0.0
        try:
            while not self.stop.is_set():
                try:
                    events = self.routine.tick()
                    for ev in events:
                        await self._send_all(ev)
                    if events:
                        pushed_routine = False
                        pushed_reminders = False
                        for ev in events:
                            etype = ev.get("type", "")
                            if not pushed_routine and etype.startswith("routine_"):
                                await self._send_all({"type": "routine", "state": self.routine.compute_state()})
                                pushed_routine = True
                            if not pushed_reminders and etype == "reminder_triggered":
                                await self._send_all({"type": "reminders", "list": self.routine.get_reminders()})
                                pushed_reminders = True
                    now = time.monotonic()
                    if now - last_state_push >= 5.0:
                        await self._send_all({"type": "routine", "state": self.routine.compute_state()})
                        last_state_push = now
                    if now - last_reminder_push >= 5.0:
                        await self._send_all({"type": "reminders", "list": self.routine.get_reminders()})
                        last_reminder_push = now
                except Exception as exc:  # noqa: BLE001
                    log.error("Routine tick error: %s", exc)
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

# ==========================================================================
# 4) Launch Chrome with the HUD
# ==========================================================================

def _find_chrome():
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Chromium\Application\chrome.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _grant_permissions(http_port):
    """Pre-seed the Chrome profile to allow camera + mic for our origin.

    This avoids both the permission prompt (which is hidden in --app fullscreen)
    and the unsupported-flag warning bar. Seeds for all possible HUD ports plus
    wildcard so a port change never breaks permission. Call once before Chrome
    launch — Chrome must not be running with this profile at that moment.
    """
    try:
        default_dir = PROFILE_DIR / "Default"
        default_dir.mkdir(parents=True, exist_ok=True)
        prefs_path = default_dir / "Preferences"
        prefs = {}
        if prefs_path.exists():
            try:
                prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
            except Exception:
                prefs = {}
        profile = prefs.setdefault("profile", {})
        cs = profile.setdefault("content_settings", {})
        exc = cs.setdefault("exceptions", {})
        cam = exc.setdefault("media_stream_camera", {})
        mic = exc.setdefault("media_stream_mic", {})
        # Seed for every possible HUD port + wildcard origins. Chrome matches
        # the exact origin string, so we must cover the actual http_port plus
        # a one-time wildcard set. Also set default values to allow.
        origins = set()
        for p in range(8767, 8781):
            origins.add(f"http://127.0.0.1:{p}")
            origins.add(f"http://localhost:{p}")
        # wildcard / port-less variants Chrome sometimes checks
        origins.update([
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://127.0.0.1",
            "http://localhost",
        ])
        # also include the actual bound port explicitly (redundant but safe)
        origins.add(f"http://127.0.0.1:{http_port}")
        for store in (cam, mic):
            for origin in origins:
                for key in (f"{origin},*", f"{origin}:80,*", origin):
                    store[key] = {"last_used": 0, "setting": 1}
        # also allow by default — some Chrome versions check this
        dcs = profile.setdefault("default_content_setting_values", {})
        dcs["media_stream_mic"] = 1
        dcs["media_stream_camera"] = 1
        prefs_path.write_text(json.dumps(prefs), encoding="utf-8")
        log.info("Pre-seeded camera/mic permission for %d origins (active port %d)", len(origins), http_port)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not pre-seed camera/mic permission: %s", exc)


def _find_electron():
    # Prefer local electron from node_modules
    candidates = [
        ROOT / "node_modules" / ".bin" / "electron.cmd",
        ROOT / "node_modules" / "electron" / "dist" / "electron.exe",
        ROOT / ".venv" / "Scripts" / "electron.cmd",
    ]
    for cand in candidates:
        try:
            if cand.exists():
                return cand
        except: pass
    # also try npx on PATH
    try:
        import shutil
        npx = shutil.which("npx")
        if npx:
            # check if electron is resolvable via npx
            return Path(npx)
    except: pass
    return None

def launch_electron(hud_url, http_port):
    if os.environ.get("JARVIS_NO_ELECTRON"):
        log.info("Skipping Electron launch (JARVIS_NO_ELECTRON set)")
        return None
    electron = _find_electron()
    if not electron:
        log.info("Electron not found — will fallback to Chrome. Install with: npm install electron")
        return None
    # If electron binary exists, launch it. electron_main.js will start its own HTTP server and backend.
    # We pass hud_url as hint via env, but electron_main ignores and uses its own port.
    try:
        # Use cmd /c for .cmd on Windows
        if str(electron).lower().endswith('.cmd'):
            # On Windows, .cmd needs shell via cmd /c
            proc = subprocess.Popen(["cmd", "/c", str(electron), "."], cwd=str(ROOT), creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        elif "npx" in str(electron).lower():
            proc = subprocess.Popen([str(electron), "electron", "."], cwd=str(ROOT), creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        else:
            proc = subprocess.Popen([str(electron), "."], cwd=str(ROOT))
        log.info("Electron launched (PID %s) — HUD will load via Electron WebContentsView (Spidey Tracker embedded)", proc.pid)
        return proc
    except Exception as exc:
        log.warning("Electron launch failed (%s), falling back to Chrome: %s", electron, exc)
        return None

def launch_chrome(hud_url, http_port):
    if os.environ.get("JARVIS_NO_CHROME"):
        log.info("Skipping Chrome launch (JARVIS_NO_CHROME set) - backend will stay alive for testing")
        return None
    chrome = _find_chrome()
    if not chrome:
        log.error("Chrome not found. Open this URL manually in Chrome: %s", hud_url)
        return None
    if not HUD_FILE.exists():
        log.error("HUD file missing: %s", HUD_FILE)
        return None
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _grant_permissions(http_port)
    # 127.0.0.1 is already a secure context for getUserMedia, so no
    # --unsafely-treat-insecure-origin-as-secure needed (that flag triggers
    # the "unsupported command-line flag" banner you saw). We only need the
    # fake UI flag to auto-grant the hidden prompt in --app fullscreen.
    args = [
        chrome,
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run", "--no-default-browser-check", "--disable-extensions",
        "--disable-translate", "--disable-infobars", "--disable-session-crashed-bubble",
        "--disable-features=TranslateUI", "--noerrdialogs",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-popup-blocking",
        "--remote-debugging-port=9223",
        "--start-fullscreen", f"--app={hud_url}",
    ]
    try:
        proc = subprocess.Popen(args)
        log.info("Chrome launched (PID %s) -> %s", proc.pid, hud_url)
        return proc
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to launch Chrome: %s", exc)
        return None


# ==========================================================================
# 5) Main
# ==========================================================================

async def main():
    http_port = _start_http()
    if http_port is None:
        log.error("Could not start the HUD HTTP server.")
        return
    hud_url = f"http://127.0.0.1:{http_port}/hologram_environment.html"
    log.info("HUD served at %s", hud_url)

    # Start the local expressive TTS server on port 8766
    _start_tts()

    import websockets  # local import; fails loudly only if truly missing

    # --- CONFIG VALIDATION (publication-safe) ---
    missing = []
    if not (os.environ.get("GROQ_API_KEY") or Path(ROOT / "groq api.txt").exists()):
        # Also check .env via os.getenv already loaded, so just check env
        if not os.environ.get("GROQ_API_KEY"):
            missing.append("GROQ_API_KEY")
    if not (os.environ.get("FISH_API_KEY") or os.environ.get("FISH_AUDIO_API_KEY") or Path(ROOT / "fish audio api.txt").exists()):
        if not (os.environ.get("FISH_API_KEY") or os.environ.get("FISH_AUDIO_API_KEY")):
            missing.append("FISH_API_KEY / FISH_AUDIO_API_KEY")
    if missing:
        log.warning("CONFIGURATION ERROR Missing: %s — set them in .env (see .env.example) or environment. Running in degraded/offline mode.", ", ".join(missing))
        # Do NOT print values, just names
    else:
        log.info("Configuration OK — required keys present")

    backend = Backend()
    # Try WS_PORT and fallback ports 8765-8775 to handle stale bind (crash log showed 10048)
    ws_server = None
    ws_port_used = WS_PORT
    for try_port in range(WS_PORT, WS_PORT + 10):
        try:
            ws_server = await websockets.serve(backend.handler, "127.0.0.1", try_port, max_size=8 * 1024 * 1024)
            ws_port_used = try_port
            if try_port != WS_PORT:
                log.warning("WS port %d busy, bound to %d instead (update HUD if it hardcodes 8765)", WS_PORT, try_port)
            break
        except OSError as e:
            log.warning("WS port %d busy (%s), trying next...", try_port, e)
            continue
    if ws_server is None:
        log.error("Could not bind WebSocket server on ports %d-%d. Check if another JARVIS instance is running.", WS_PORT, WS_PORT+9)
        log.error("Hint: kill stale python.exe holding 8765 or restart PC. See jarvis_crash.log for last bind error.")
        return
    global CURRENT_WS_URL
    CURRENT_WS_URL = f"ws://127.0.0.1:{ws_port_used}"
    log.info("J.A.R.V.I.S. backend ready at %s", CURRENT_WS_URL)
    # If we bound to non-default port, also try to inform HUD via http handler (HUD will try 8765 by default, so log clearly)
    if ws_port_used != WS_PORT:
        log.info("HUD WS_URL was updated via /jarvis_ws_url to %s; this avoids stale 8765 assumptions.", CURRENT_WS_URL)

    # Live API-key status check (runs in a background thread so it doesn't
    # block startup). Logs clearly whether Groq / Gemini are actually live.
    def _api_verify():
        try:
            status = backend.brain.verify()
            log.info("API STATUS (live): %s | active provider = %s",
                     {k: v for k, v in status.items() if k != "active"}, status.get("active"))
            if status.get("groq") != "ok":
                log.warning("GROQ is NOT live (status=%s). Agent LLM replies will fall back to offline text.",
                            status.get("groq"))
            if status.get("gemini") != "ok":
                log.warning("GEMINI is NOT live (status=%s). The configured Gemini key does not validate.",
                            status.get("gemini"))
        except Exception as exc:  # noqa: BLE001
            log.warning("API status check failed: %s", exc)

    threading.Thread(target=_api_verify, daemon=True).start()

    # STT warmup in background: first utterance must not pay model-load cost.
    threading.Thread(target=_warmup_stt, daemon=True).start()

    # Prefer Electron (WebContentsView) for Spidey Tracker embedded view; fallback to Chrome --app
    proc = launch_electron(hud_url, http_port)
    if proc is None:
        proc = launch_chrome(hud_url, http_port)
    else:
        log.info("Running in Electron mode — Spidey Tracker will use real WebContentsView (no iframe, no CSP bypass)")
    hb = asyncio.create_task(backend.heartbeat())
    rt = asyncio.create_task(backend.routine_loop())
    cx = asyncio.create_task(backend.context_loop())

    try:
        while True:
            if proc is not None and proc.poll() is not None:
                log.info("HUD window closed.")
                break
            await asyncio.sleep(1)
    finally:
        backend.stop.set()
        hb.cancel()
        rt.cancel()
        cx.cancel()
        try:
            if ws_server:
                ws_server.close()
                await ws_server.wait_closed()
                log.info("WebSocket server on %d closed", ws_port_used)
        except Exception as e:
            log.debug("WS close error: %s", e)
        if proc is not None and proc.poll() is None:
            proc.terminate()
        log.info("J.A.R.V.I.S. shut down.")


if __name__ == "__main__":
    # Relaunch under the project virtualenv if the current interpreter lacks deps
    # (e.g. when double-clicked and opened with the system Python).
    if not _running_in_venv() and VENV_PY.exists():
        try:
            os.execv(str(VENV_PY), [str(VENV_PY), __file__, *sys.argv[1:]])
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to relaunch with the virtualenv Python: %s", exc)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except OSError as e:  # noqa: BLE001 - port bind etc
        import traceback
        tb = traceback.format_exc()
        log.error("Fatal OS error (likely port bind): %s\n%s", e, tb)
        try:
            with open(ROOT / "jarvis_crash.log", "w", encoding="utf-8") as fh:
                fh.write(f"OSError: {e}\n" + tb)
                fh.write("\nHint: netstat -ano | findstr 8765 to find holder, then taskkill /PID <pid> /F\n")
        except Exception:
            pass
        if sys.stdout.isatty():
            input(f"J.A.R.V.I.S. port error {e} - press Enter to close. See jarvis_crash.log.")
    except Exception:  # noqa: BLE001
        import traceback

        tb = traceback.format_exc()
        log.error("Fatal error:\n%s", tb)
        try:
            with open(ROOT / "jarvis_crash.log", "w", encoding="utf-8") as fh:
                fh.write(tb)
        except Exception:
            pass
        if sys.stdout.isatty():
            input("J.A.R.V.I.S. hit an error - press Enter to close. See jarvis_crash.log.")





