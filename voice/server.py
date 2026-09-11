"""
Local TTS HTTP gateway (localhost-only, one active voice service).

The HUD POSTs speech requests to http://127.0.0.1:8766/tts (JSON
{text, emotion, intensity, speaking_rate, character}). This server runs the full
local voice pipeline and returns WAV audio (or a WAV stream on /stream). It is
bound to 127.0.0.1 ONLY and must never be exposed on the LAN.

Routes:
  POST /tts            -> WAV audio (or 4xx/5xx)
  POST /speak          -> enqueue async reply (202 + item_id)
  GET  /health         -> JSON status (VOICE_* state, metrics, emotion)
  GET  /voices         -> list engine voices
  POST /voice/set      -> {voice}
  POST /emotion/set    -> {emotion, mode, intensity}
  GET  /emotion/state  -> shared emotion state
  POST /warmup         -> load/verify model
  POST /stop           -> interrupt all speech
  POST /pause /resume  -> pause/resume playback
  GET  /config         -> public config
"""
from __future__ import annotations

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .config import VoiceConfig
from .engine import VoiceEngine
from .emotion import normalize_emotion
from .log import logger
from .service import VoiceService
from .tts_backend import TTSError, TTSUnavailable


class _Handler(BaseHTTPRequestHandler):
    cfg: Optional[VoiceConfig] = None
    service: Optional[VoiceService] = None


    # ---- CORS (browser HUD on :8767 may fetch the TTS gateway on :8766) ----
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Requested-With, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self):
        """Answer the browser CORS preflight for the HUD's /tts POST."""
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ---- helpers ----
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _audio(self, data: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Amplitude", "%.3f" % self.service.playback.amplitude())
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def log_message(self, *args):
        pass  # quiet; use our own logger

    # ---- routes ----
    def do_GET(self):
        if self.path.startswith("/health"):
            self._json(self.service.health())
        elif self.path.startswith("/voices"):
            try:
                from .character_registry import list_characters
                chars = list_characters()
            except Exception:
                chars = {}
            self._json({"voices": self.service.engine.list_voices(),
                        "voice": self.cfg.voice,
                        "character": getattr(self.service.engine, "current_character", "iron_man"),
                        "characters": chars})
        elif self.path.startswith("/character"):
            self._json(self.service.get_current_voice() if hasattr(self.service, "get_current_voice") else {"character": "iron_man"})
        elif self.path.startswith("/config"):
            self._json(self.cfg.public())
        elif self.path.startswith("/emotion/state"):
            self._json(self.service.emotion.to_dict())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        body = self._read_body()
        if self.path.startswith("/tts"):
            self._tts(body)
        elif self.path.startswith("/speak"):
            text = (body or {}).get("text", "").strip()
            if not text:
                self._json({"error": "missing text"}, 400)
                return
            char = body.get("character") or body.get("voice") or None
            iid = self.service.speak(text, character=char, emotion=normalize_emotion(body.get("emotion")),
                                     priority=body.get("priority", "normal"))
            self._json({"ok": True, "item_id": iid}, 202)
        elif self.path.startswith("/stream"):
            self._stream(body)
        elif self.path.startswith("/stop"):
            self.service.stop()
            self._json({"ok": True})
        elif self.path.startswith("/pause"):
            self.service.pause()
            self._json({"ok": True})
        elif self.path.startswith("/resume"):
            self.service.resume()
            self._json({"ok": True})
        elif self.path.startswith("/warmup"):
            ok, detail = self.service.warmup()
            self._json({"ok": ok, "detail": detail, "state": self.service.state},
                       200 if ok else 503)
        elif self.path.startswith("/character/set"):
            char = (body or {}).get("character") or (body or {}).get("voice")
            ok = self.service.set_character(char) if char else False
            self._json({"ok": ok, "character": getattr(self.service.engine, "current_character", "iron_man")}, 200 if ok else 400)
        elif self.path.startswith("/voice/set"):
            vid = (body or {}).get("voice")
            # Try character first, then voice
            if vid and hasattr(self.service, "set_character"):
                # If vid looks like character name, treat as character
                from .character_registry import normalize_character
                try:
                    norm = normalize_character(vid)
                    if norm in ("iron_man", "spider_man", "thor", "thanos"):
                        ok = self.service.set_character(vid)
                        self._json({"ok": ok, "character": norm}, 200 if ok else 400)
                        return
                except Exception:
                    pass
            ok = self.service.engine.set_voice(vid) if vid else False
            self._json({"ok": ok, "voice": self.cfg.voice}, 200 if ok else 400)
        elif self.path.startswith("/emotion/set"):
            self.service.engine.set_emotion(
                emotion=body.get("emotion"), mode=body.get("mode"),
                intensity=body.get("intensity"))
            self._json({"ok": True})
        elif self.path.startswith("/clear"):
            if hasattr(self.service, "clear_queue"):
                self.service.clear_queue()
            else:
                self.service.stop()
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)

    def _tts(self, body: dict):
        text = (body.get("text") or "").strip()
        if not text:
            self._json({"error": "missing text"}, 400)
            return
        char = body.get("character") or body.get("voice") or None
        try:
            audio = self.service.engine.speak(
                text, character=char, emotion=normalize_emotion(body.get("emotion")),
                speaking_rate=body.get("speaking_rate"),
                priority=body.get("priority", "normal"))
            self._audio(audio)
        except TTSUnavailable as e:
            logger.error(f"[TTS] engine unavailable: {e}")
            self._json({"error": f"TTS unavailable: {e}", "state": self.service.state}, 503)
        except TTSError as e:
            logger.error(f"[TTS] error: {e}")
            self._json({"error": str(e)}, 500)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[TTS] unexpected: {e}")
            self._json({"error": "unexpected TTS failure"}, 500)

    def _stream(self, body: dict):
        text = (body.get("text") or "").strip()
        if not text:
            self._json({"error": "missing text"}, 400)
            return
        char = body.get("character") or body.get("voice") or None
        try:
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            for _amp, wav in self.service.stream(
                    text, character=char, emotion=normalize_emotion(body.get("emotion")),
                    priority=body.get("priority", "normal")):
                part = wav
                self.wfile.write(b"%x\r\n%s\r\n" % (len(part), part))
            self.wfile.write(b"0\r\n\r\n")
        except Exception as e:  # noqa: BLE001
            logger.error(f"[TTS] stream error: {e}")
            if not self.wfile.closed:
                try:
                    self.wfile.write(b"0\r\n\r\n")
                except Exception:  # noqa: BLE001
                    pass


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


class _DoubleStartException(Exception):
    pass


def start_tts_server(cfg: VoiceConfig, engine: Optional[VoiceEngine] = None,
                     service: Optional[VoiceService] = None,
                     reuse_if_running: bool = True) -> ThreadingHTTPServer:
    """Start the gateway. Double-start protection: if the gateway is already
    healthy on this port, reuse it (spec §37). Returns a server object, or the
    existing healthy process marker.
    """
    if reuse_if_running and port_in_use(cfg.tts_host, cfg.tts_port):
        # Another gateway (ours) is already serving this port -> reuse it.
        logger.info(f"[TTS] gateway already on {cfg.tts_host}:{cfg.tts_port}; reusing")
        class _Marker:
            def serve_forever(self):
                pass

            def shutdown(self):
                pass
        return _Marker()

    if service is None:
        service = VoiceService(cfg, engine=engine)
    _Handler.service = service
    _Handler.cfg = cfg
    server = ThreadingHTTPServer((cfg.tts_host, cfg.tts_port), _Handler)
    logger.info(f"[TTS] gateway listening on http://{cfg.tts_host}:{cfg.tts_port}/tts "
                f"(provider={cfg.provider} engine={service.engine.engine_name})")
    return server