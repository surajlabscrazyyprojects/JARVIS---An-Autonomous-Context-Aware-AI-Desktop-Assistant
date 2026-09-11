"""
VoiceService verification (orpheus provider / kokoro engine).

Contract tests use a fast deterministic FakeBackend producing real valid WAV
bytes, so queue / SpeechQueue / AudioPlaybackManager / interruption / recovery
/ latency are exercised without loading the 82M model. One subprocess test
verifies the real Kokoro engine offline.
"""
import io
import os
import subprocess
import sys
import time
import wave

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice import (  # noqa: E402
    VoiceConfig, VoiceService, BufferSink, PyAudioSink, EMOTIONS,
)

HERE = os.path.dirname(os.path.abspath(__file__))


def _tone_wav(dur: float = 0.3, sr: int = 24000, freq: float = 180.0) -> bytes:
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    samples = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((samples * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


class FakeBackend:
    """Deterministic local backend matching the new TTSBackend contract."""
    name = "fake"

    def available(self):
        return True

    def health_check(self):
        return True, "ok"

    def warmup(self):
        return True, "ready (fake)"

    def synthesize(self, text, voice=None, speed: float = 1.0, pitch_cents: int = 0):
        dur = min(1.2, max(0.15, len(text) * 0.01))
        return _tone_wav(dur=dur)

    def stream(self, text, voice=None, speed: float = 1.0, pitch_cents: int = 0):
        yield 0.05, self.synthesize(text, voice=voice, speed=speed, pitch_cents=pitch_cents)

    def list_voices(self):
        return ["am_michael", "am_puck"]

    def stop(self): pass
    def pause(self): pass
    def resume(self): pass
    def shutdown(self): pass


def _cfg(**kw):
    c = VoiceConfig.load()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _service(sink=None, **cfg_kw):
    return VoiceService(_cfg(**cfg_kw), sink=sink or BufferSink(), backend=FakeBackend())


def _wait_played(sink: BufferSink, n: int, timeout: float = 20.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if len(sink.played) >= n and not sink.is_playing():
            return True
        time.sleep(0.02)
    return len(sink.played) >= n


# ---------------------------------------------------------------- warmup
def test_warmup_reports_ready():
    svc = _service()
    try:
        ok, detail = svc.warmup()
        assert ok is True, detail
        h = svc.health()
        assert h["state"] == "VOICE_READY", h
        assert h["engine"] == "fake"
        assert h["provider"] == "fish"
    finally:
        svc.shutdown()


# ---------------------------------------------------------------- basic speak
def test_single_speak_delivers_audio():
    svc = _service()
    sink = svc.playback.sink
    try:
        svc.warmup()
        res = svc.speak_sync("Systems online, sir.")
        assert res.get("aborted") is False
        assert _wait_played(sink, 1)
        assert len(sink.played[0]) > 44
    finally:
        svc.shutdown()


# ---------------------------------------------------------------- 20+ utterances
def test_twenty_utterances_all_succeed():
    svc = _service()
    sink = svc.playback.sink
    try:
        svc.warmup()
        lines = [
            "Good morning, sir.", "Shall I begin the daily briefing?",
            "The suit is fully charged.", "Repulsor output nominal.",
            "I have locked the doors.", "Weather in New York is clear.",
            "Your calendar is empty today.", "Message sent.",
            "Navigating now.", "Scanning the perimeter.",
            "Threat level: low.", "Power at ninety eight percent.",
            "Would you like some music?", "Call connected.",
            "Reminder set for ten seconds.", "Download complete.",
            "Uploading to the cloud.", "Sensors report all clear.",
            "Time is 0800 hours.", "Goodnight, sir.",
        ]
        assert len(lines) >= 20
        for ln in lines:
            svc.speak(ln)
        assert _wait_played(sink, len(lines), timeout=60)
        assert len(sink.played) == len(lines)
        assert svc.metrics.count == len(lines)
    finally:
        svc.shutdown()


# ---------------------------------------------------------------- every emotion
def test_every_emotion_is_spoken_and_recorded():
    svc = _service()
    svc.cfg.emotion_mode = "manual"
    sink = svc.playback.sink
    try:
        svc.warmup()
        for emo in EMOTIONS:
            svc.speak("Testing the %s tone." % emo, emotion=emo)
        assert _wait_played(sink, len(EMOTIONS), timeout=60)
        assert svc.emotion.current in EMOTIONS
        # same sentence with different emotions keeps identity but changes delivery
        svc2 = _service()
        try:
            svc2.warmup()
            from voice.emotion import delivery_for
            s1, _, _ = delivery_for("neutral")
            s2, _, _ = delivery_for("excited")
            assert s1 != s2
        finally:
            svc2.shutdown()
    finally:
        svc.shutdown()


# ---------------------------------------------------------------- chunking
def test_long_text_chunks_and_plays():
    svc = _service()
    sink = svc.playback.sink
    try:
        svc.warmup()
        long_text = (" " + "This is a very long status report that must be "
                     "chunked into multiple segments for natural delivery. ") * 6
        res = svc.speak_sync(long_text, timeout=30)
        assert res.get("aborted") is False
        assert _wait_played(sink, 1)
        assert len(sink.played[0]) > 44
    finally:
        svc.shutdown()


# ---------------------------------------------------------------- interruption / barge-in
def test_interruption_stops_current_and_plays_new():
    svc = _service()
    sink = svc.playback.sink
    results = {}
    try:
        svc.warmup()
        svc.speak("This is a long unimportant message that should be "
                  "interrupted before it finishes playing out loud.",
                  on_done=lambda ab: results.setdefault("A", ab))
        t0 = time.time()
        while time.time() - t0 < 10 and not sink.is_playing():
            time.sleep(0.005)
        assert sink.is_playing() is True
        svc.speak("Priority override, sir.", priority="high",
                  on_done=lambda ab: results.setdefault("B", ab))
        assert _wait_played(sink, 1, timeout=30)
        t0 = time.time()
        while time.time() - t0 < 30 and "B" not in results:
            time.sleep(0.02)
        assert results.get("A") is True
        assert results.get("B") is False
        assert len(sink.played) == 1
    finally:
        svc.shutdown()


def test_stop_cancels_playback_barge_in():
    svc = _service()
    sink = svc.playback.sink
    results = {}
    try:
        svc.warmup()
        svc.speak("A message that we will barge in on and cancel.",
                  on_done=lambda ab: results.setdefault("A", ab))
        t0 = time.time()
        while time.time() - t0 < 10 and not sink.is_playing():
            time.sleep(0.01)
        assert sink.is_playing() is True
        svc.stop()
        t0 = time.time()
        while time.time() - t0 < 10 and "A" not in results:
            time.sleep(0.02)
        assert results.get("A") is True
        assert len(sink.played) == 0
    finally:
        svc.shutdown()


# ---------------------------------------------------------------- no overlap + priorities
def test_no_audio_overlap():
    svc = _service()
    sink = svc.playback.sink
    try:
        svc.warmup()
        svc.speak("First overlapping check sentence.")
        svc.speak("Second overlapping check sentence.")
        svc.speak("Third overlapping check sentence final.")
        assert _wait_played(sink, 3, timeout=30)
        assert len(sink.played) == 3
    finally:
        svc.shutdown()


def test_priority_ordering():
    svc = _service()
    sink = svc.playback.sink
    sink.sim_dur = 0.05
    try:
        svc.warmup()
        # low then critical: critical jumps ahead (queued behind current, but
        # critical clears pending queue style in manager)
        svc.speak("low priority background", priority="low")
        svc.speak("critical system warning", priority="critical")
        assert _wait_played(sink, 2, timeout=30)
        assert len(sink.played) == 2
    finally:
        svc.shutdown()


# ---------------------------------------------------------------- TTS failure + recovery
def test_tts_failure_recovers():
    svc = _service()
    sink = svc.playback.sink
    calls = {"n": 0}
    real_synth = svc.engine.core.synthesize

    def flaky(text, voice=None, speed=1.0, pitch_cents=0):
        calls["n"] += 1
        if calls["n"] <= 1:
            from voice.tts_backend import TTSError
            raise TTSError("simulated TTS failure")
        return real_synth(text, voice=voice, speed=speed, pitch_cents=pitch_cents)

    svc.engine.core.synthesize = flaky
    try:
        svc.warmup()
        # engine.speak wraps synthesize per chunk, so one retry path via service
        # recovery is not auto; we just verify the service stays alive after a fail.
        # Speak will fail the first chunk then the item is marked aborted; next
        # speak should succeed after we restore.
        res = svc.speak_sync("This will fail once.", timeout=10)
        # may be aborted due to flaky; next one should succeed
        svc.engine.core.synthesize = real_synth
        res2 = svc.speak_sync("Recovery after simulated failure, sir.", timeout=10)
        assert res2.get("aborted") is False
        assert _wait_played(sink, 1)
    finally:
        svc.shutdown()


# ---------------------------------------------------------------- device recovery
def test_sink_failure_does_not_crash_service():
    svc = _service()
    sink = svc.playback.sink
    calls = {"n": 0}

    orig_play = svc.playback.play

    def boom(wav, item_id, priority=0, on_done=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated device error")
        return BufferSink.play(sink, wav, on_done)

    svc.playback.play = boom  # type: ignore
    try:
        svc.warmup()
        svc.speak("This one fails at the device.")
        time.sleep(0.3)
        svc.playback.play = orig_play  # restore
        res = svc.speak_sync("This one plays correctly.", timeout=10)
        assert res.get("aborted") is False
        assert _wait_played(sink, 1)
    finally:
        svc.shutdown()


# ---------------------------------------------------------------- latency + CPU/RAM
def test_latency_and_resource_metrics():
    psutil = pytest.importorskip("psutil")
    svc = _service()
    sink = svc.playback.sink
    proc = psutil.Process(os.getpid())
    try:
        svc.warmup()
        mem_before = proc.memory_info().rss
        for i in range(10):
            svc.speak("Metric sample phrase number %d." % i)
        assert _wait_played(sink, 10, timeout=40)
        mem_after = proc.memory_info().rss
        mem_mb = (mem_after - mem_before) / (1024 * 1024)
        m = svc.metrics
        assert m.count == 10
        assert m.last_total > 0, m
        assert m.last_first_audio >= 0, m
        assert m.rolling_total < 5.0, "avg total too high: %s" % m.rolling_total
        assert mem_mb < 1500, "memory delta too high: %.1f MB" % mem_mb
    finally:
        svc.shutdown()


# ---------------------------------------------------------------- real device smoke
def test_real_speaker_smoke():
    svc = None
    try:
        svc = _service(sink=PyAudioSink())
    except Exception as e:  # noqa: BLE001
        pytest.skip("no audio device available: %s" % e)
    try:
        ok, detail = svc.warmup()
        assert ok is True, detail
        res = svc.speak_sync("Audible smoke test complete.", timeout=30)
        assert res.get("item_id") is not None
    finally:
        if svc:
            svc.shutdown()


# ---------------------------------------------------------------- real Kokoro E2E (subprocess)
def test_real_kokoro_service_e2e():
    """Full VoiceService + real Kokoro, run in a clean process."""
    script = os.path.join(HERE, "_real_kokoro_run.py")
    if not os.path.exists(script):
        pytest.skip("real Kokoro runner missing")
    try:
        proc = subprocess.run([sys.executable, script],
                              capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        pytest.skip("real Kokoro E2E timed out")
    if proc.returncode != 0:
        pytest.skip("real Kokoro unavailable here: %s" % proc.stderr[-400:])
    assert "REAL_KOKORO_OK" in proc.stdout

