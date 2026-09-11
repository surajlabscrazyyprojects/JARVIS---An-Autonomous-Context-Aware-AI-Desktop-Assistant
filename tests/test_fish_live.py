"""Tests for the Fish live-WS protocol framing (§5, §20). All mocked — no key."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import msgpack
import pytest

from voice import fish_live as fl
from voice.fish_config import FishConfig, FishConfigError


def _cfg(**kw):
    d = dict(api_key="sk-test-1234567890", reference_id="ref123",
             model="s2.1-pro-free")
    d.update(kw)
    return FishConfig(**d)


def test_start_request_shape_matches_asyncapi():
    cfg = _cfg()
    req = fl.build_start_request(cfg, "ref123", speed=1.0)
    assert req["text"] == ""
    assert req["reference_id"] == "ref123"
    assert req["format"] == "pcm"
    assert req["sample_rate"] == 24000
    assert req["prosody"]["speed"] == 1.0
    assert req["latency"] in ("low", "normal", "balanced")
    assert req["normalize"] is True
    # msgpack round-trip (what the wire actually carries)
    assert msgpack.unpackb(msgpack.packb({"event": "start", "request": req}), raw=False)["event"] == "start"


def test_paid_model_blocked_pre_request():
    cfg = _cfg(model="s2.1-pro")
    # Fail-closed at validation AND at session construction - never sent.
    with pytest.raises((fl.PaidModelBlocked, FishConfigError)):
        fl.build_start_request(cfg, "ref123")
    with pytest.raises(fl.PaidModelBlocked):
        fl.FishLiveSession(cfg, "ref123")


def test_missing_key_fails_fast():
    with pytest.raises(fl.MissingApiKey):
        fl.FishLiveSession(FishConfig(api_key="", reference_id="r", model="s2.1-pro-free"), "r")


def test_missing_reference_fails_fast():
    with pytest.raises(fl.MissingReferenceId):
        fl.FishLiveSession(_cfg(), "")


def test_parse_audio_and_finish():
    kind, payload = fl.FishLiveSession._parse(msgpack.packb({"event": "audio", "audio": b"\x00\x01abc"}))
    assert kind == "audio" and payload == b"\x00\x01abc"
    kind, payload = fl.FishLiveSession._parse(msgpack.packb({"event": "finish", "reason": "stop"}))
    assert (kind, payload) == ("finish", "stop")


def test_parse_garbage_raises_protocol_error():
    with pytest.raises(fl.FishProtocolError):
        fl.FishLiveSession._parse(b"\xff\xff not msgpack \xff")
    with pytest.raises(fl.FishProtocolError):
        fl.FishLiveSession._parse(msgpack.packb({"event": "weird"}))


def test_parse_empty_audio_rejected():
    with pytest.raises(fl.FishProtocolError):
        fl.FishLiveSession._parse(msgpack.packb({"event": "audio", "audio": b""}))


class _FakeWS:
    """Scripted stand-in for the sync websocket: records sends, replays recvs."""
    def __init__(self, script):
        self.sent = []
        self.script = list(script)
        self.closed = False

    def send(self, data):
        self.sent.append(msgpack.unpackb(data, raw=False))

    def recv(self, timeout=None):
        if not self.script:
            # Scripted server is done -> terminal finish (models a server
            # that always closes the session; production adds timeouts).
            return _finish()
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True


def _audio_blob(n=320):
    return msgpack.packb({"event": "audio", "audio": b"\x01\x02" * (n // 2)})


def _finish(reason="stop"):
    return msgpack.packb({"event": "finish", "reason": reason})


def test_full_session_lifecycle(monkeypatch):
    sess = fl.FishLiveSession(_cfg(), "ref123")
    fake = _FakeWS([_audio_blob(), _audio_blob(), _finish()])
    import msgpack as _mp

    def _fake_connect():
        sess._ws = fake
        # Real _connect sends start first — emulate it for the mock.
        fake.send(_mp.packb({"event": "start", "request": {}}))

    monkeypatch.setattr(sess, "_connect", _fake_connect)
    out = list(sess.synthesize(iter(["Hello there."])))
    assert len(out) == 2 and all(len(b) > 0 for b in out)
    events = [m["event"] for m in fake.sent]
    assert events[0] == "start"
    assert "text" in events and "flush" in events and events[-1] == "stop"
    assert fake.closed


def test_cancel_before_audio():
    sess = fl.FishLiveSession(_cfg(), "ref123")
    import threading
    sess.cancel = threading.Event()
    sess.cancel.set()

    class NeverWS:
        def send(self, data):
            pass

        def close(self):
            pass

    sess._connect = lambda: setattr(sess, "_ws", NeverWS())
    with pytest.raises(fl.UserInterrupted):
        list(sess.synthesize(iter(["Hello"])))


def test_finish_error_raises():
    sess = fl.FishLiveSession(_cfg(), "ref123")
    fake = _FakeWS([_finish(reason="error")])
    sess._connect = lambda: setattr(sess, "_ws", fake)
    with pytest.raises(fl.FishProtocolError):
        list(sess.synthesize(iter(["Hi"])))


def test_no_retry_after_audio_started():
    """A failure AFTER first audio must surface, never silently re-request."""
    sess = fl.FishLiveSession(_cfg(), "ref123")
    fake = _FakeWS([_audio_blob(), fl.FishProtocolError("boom")])
    sess._connect = lambda: setattr(sess, "_ws", fake)
    with pytest.raises(fl.FishProtocolError):
        list(sess.synthesize(iter(["Hello there, this is a longer line."])))
    assert sess.audio_started is True
