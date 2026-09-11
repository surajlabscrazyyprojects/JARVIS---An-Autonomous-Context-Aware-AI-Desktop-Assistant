from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from jarvis.voice.config import VoiceEngineConfig
from jarvis.voice.engine import VoiceEngineManager


class VoiceTTSServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], RequestHandlerClass: Any, manager: VoiceEngineManager) -> None:
        self.manager = manager
        super().__init__(server_address, RequestHandlerClass)


class _TTSHandler(BaseHTTPRequestHandler):
    def _send_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        if self.path in ("/tts", "/health"):
            self.send_response(204)
            self._send_cors()
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self) -> None:
        self.do_POST()

    def do_POST(self) -> None:
        server: VoiceTTSServer = self.server  # type: ignore[assignment]
        path = self.path.split("?", 1)[0]

        if path == "/health":
            resp = {
                "status": "ok",
                "ready": server.manager.is_ready(),
                "engine": server.manager.engine.name,
            }
            body = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors()
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/tts":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length)
            try:
                data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except Exception:
                self.send_response(400)
                self._send_cors()
                self.end_headers()
                self.wfile.write(b"Invalid JSON")
                return

            text = (data.get("text") or "").strip()
            if not text:
                self.send_response(400)
                self._send_cors()
                self.end_headers()
                self.wfile.write(b"Empty text")
                return

            try:
                wav_bytes = server.manager.synthesize(text)
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav_bytes)))
                self._send_cors()
                self.end_headers()
                self.wfile.write(wav_bytes)
            except Exception as exc:
                self.send_response(500)
                self._send_cors()
                self.end_headers()
                self.wfile.write(str(exc).encode("utf-8"))
            return

        self.send_response(404)
        self._send_cors()
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        pass


def create_tts_server(manager: VoiceEngineManager, config: Optional[VoiceEngineConfig] = None) -> VoiceTTSServer:
    cfg = config or VoiceEngineConfig()
    return VoiceTTSServer(("127.0.0.1", cfg.http_port), _TTSHandler, manager)
