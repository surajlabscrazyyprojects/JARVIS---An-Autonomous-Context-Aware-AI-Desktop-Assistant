"""HTTP gateway tests (FakeBackend contract, no real model load)."""
import io
import json
import sys
import threading
import wave
from pathlib import Path
from http.client import HTTPConnection

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voice import VoiceConfig, VoiceService, BufferSink, start_tts_server  # noqa: E402


def _tone_wav(dur=0.2, sr=24000) -> bytes:
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    a = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((a * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


class FakeBackend:
    name = "fake"
    def available(self): return True
    def health_check(self): return True, "ok"
    def warmup(self): return True, "ready (fake)"
    def synthesize(self, text, voice=None, speed=1.0, pitch_cents=0):
        return _tone_wav(0.15)
    def stream(self, text, voice=None, speed=1.0, pitch_cents=0):
        yield 0.05, self.synthesize(text, voice=voice, speed=speed, pitch_cents=pitch_cents)
    def list_voices(self): return ["am_michael", "am_puck"]
    def stop(self): pass
    def pause(self): pass
    def resume(self): pass
    def shutdown(self): pass


def _make_config(tmp_path, tts_port=None):
    c = VoiceConfig()
    c.provider = "orpheus"
    c.engine = "kokoro"
    c.streaming = False
    c.tts_host = "127.0.0.1"
    c.tts_port = tts_port or 0  # ephemeral when 0 -> real assigned port
    c.voices_dir = tmp_path / "voices"
    c.state_dir = tmp_path / "config"
    c.cache_dir = tmp_path / "cache"
    # create a dummy voice profile so list_voices via engine is exercised
    vd = tmp_path / "voices" / "jarvis"
    vd.mkdir(parents=True)
    (vd / "metadata.json").write_text('{"id":"jarvis","name":"JARVIS","reference_audio":"reference.wav","reference_text":"hi"}')
    (vd / "reference.wav").write_bytes(_tone_wav(0.1))
    return c


def _start(c, port=None):
    if port is not None:
        c.tts_port = port
    svc = VoiceService(c, sink=BufferSink(), backend=FakeBackend())
    svc.warmup()
    srv = start_tts_server(c, service=svc)
    # When port 0, retrieve assigned port
    if hasattr(srv, "server_address"):
        c.tts_port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return svc, srv


def _post(conn, path, body=None):
    data = json.dumps(body).encode() if body is not None else b""
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn.request("POST", path, body=data, headers=headers)
    return conn.getresponse()


def test_gateway_full_flow(tmp_path):
    c = _make_config(tmp_path, tts_port=8871)
    svc, srv = _start(c)
    try:
        conn = HTTPConnection("127.0.0.1", c.tts_port, timeout=10)
        conn.request("GET", "/health")
        h = json.loads(conn.getresponse().read())
        assert h["state"] in ("VOICE_READY", "VOICE_LOADING", "VOICE_OFFLINE")
        assert h["provider"] == "orpheus"
        assert h["engine"] == "fake"

        conn.request("GET", "/voices")
        v = json.loads(conn.getresponse().read())
        assert "am_michael" in v.get("voices", []) or "jarvis" in str(v)

        r = _post(conn, "/tts", {"text": "Wait, seriously? We actually fixed it!"})
        assert r.status == 200, r.read()[:200]
        audio = r.read()
        assert audio[:4] == b"RIFF"
        with wave.open(io.BytesIO(audio), "rb") as w:
            assert w.getframerate() == 24000

        r = _post(conn, "/voice/set", {"voice": "am_michael"})
        assert r.status == 200

        r = _post(conn, "/emotion/set", {"emotion": "excited", "mode": "manual", "intensity": 0.9})
        assert r.status == 200

        r = _post(conn, "/speak", {"text": "Async line.", "priority": "normal"})
        assert r.status == 202
        assert "item_id" in json.loads(r.read())

        r = _post(conn, "/warmup")
        assert r.status == 200
        assert json.loads(r.read())["ok"] is True

        conn.request("GET", "/emotion/state")
        st = json.loads(conn.getresponse().read())
        assert "current" in st and "voice_id" in st
    finally:
        srv.shutdown()


def test_gateway_missing_text(tmp_path):
    c = _make_config(tmp_path, tts_port=8872)
    svc, srv = _start(c)
    try:
        conn = HTTPConnection("127.0.0.1", c.tts_port, timeout=10)
        r = _post(conn, "/tts", {})
        assert r.status == 400
        r = _post(conn, "/speak", {"text": "   "})
        assert r.status == 400
    finally:
        srv.shutdown()


def test_gateway_stream_endpoint(tmp_path):
    c = _make_config(tmp_path, tts_port=8873)
    svc, srv = _start(c)
    try:
        conn = HTTPConnection("127.0.0.1", c.tts_port, timeout=10)
        r = _post(conn, "/stream", {"text": "Hello world. This streams."})
        assert r.status == 200
        body = r.read()
        assert len(body) > 0
    finally:
        srv.shutdown()


def test_gateway_unavailable_reports_degraded(tmp_path):
    class DeadBackend(FakeBackend):
        def health_check(self): return False, "dead"
        def warmup(self): return False, "dead"
        def synthesize(self, *a, **kw):
            from voice.tts_backend import TTSUnavailable
            raise TTSUnavailable("dead")

    c = _make_config(tmp_path, tts_port=8874)
    svc = VoiceService(c, sink=BufferSink(), backend=DeadBackend())
    ok, _ = svc.warmup()
    assert ok is False
    assert svc.state == "VOICE_DEGRADED"
    srv = start_tts_server(c, service=svc)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        import urllib.request, urllib.error
        req = __import__("urllib.request").request.Request(
            "http://127.0.0.1:%d/tts" % c.tts_port,
            data=json.dumps({"text": "hi"}).encode(), headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10)
            assert False, "expected 503"
        except urllib.error.HTTPError as e:
            assert e.code in (500, 503)
    finally:
        srv.shutdown()
