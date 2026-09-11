from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent.parent

_SERVER: Optional[ThreadingHTTPServer] = None
_SERVER_PORT: Optional[int] = None
_SERVER_LOCK = threading.Lock()


class _HudHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".ts": "application/javascript",
        ".glb": "model/gltf-binary",
        ".gltf": "model/gltf+json",
        ".bin": "application/octet-stream",
        ".wasm": "application/wasm",
        ".json": "application/json",
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, *args):
        pass


def _profile_process_running() -> bool:
    try:
        import psutil
        for proc in psutil.process_iter(["name", "cmdline"]):
            cmd = proc.info.get("cmdline") or []
            if any(".jarvis_browser_profile" in str(arg) for arg in cmd):
                return True
    except Exception:
        pass
    return False


def is_hud_running(proc: Optional[Any] = None) -> bool:
    if proc is not None:
        if hasattr(proc, "poll") and proc.poll() is None:
            return True
        if hasattr(proc, "returncode") and proc.returncode is None:
            return True
    hl = sys.modules.get("jarvis.hud_launcher")
    if hl is not None and hasattr(hl, "_profile_process_running"):
        return hl._profile_process_running()
    return _profile_process_running()


def verify_hud_started(proc: Optional[Any] = None, grace_s: float = 5.0) -> bool:
    return is_hud_running(proc)


def start_hud_server() -> Optional[int]:
    global _SERVER, _SERVER_PORT
    with _SERVER_LOCK:
        if _SERVER is not None and _SERVER_PORT is not None:
            return _SERVER_PORT
        for port in range(8767, 8785):
            try:
                srv = ThreadingHTTPServer(("127.0.0.1", port), _HudHandler)
                t = threading.Thread(target=srv.serve_forever, daemon=True)
                t.start()
                _SERVER = srv
                _SERVER_PORT = port
                return port
            except OSError:
                continue
    return None


def stop_hud_server() -> None:
    global _SERVER, _SERVER_PORT
    with _SERVER_LOCK:
        if _SERVER is not None:
            try:
                _SERVER.shutdown()
                _SERVER.server_close()
            except Exception:
                pass
            _SERVER = None
            _SERVER_PORT = None
