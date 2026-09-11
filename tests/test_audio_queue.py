"""Tests: WAV helpers, AudioPlaybackManager (no-overlap, queue, barge-in)."""
import io
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voice import VoiceConfig  # noqa: E402
from voice.audio_playback import AudioPlaybackManager, BufferSink  # noqa: E402
from voice.wav import concat_wav, read_wav, encode_wav  # noqa: E402


def _tone_wav(seconds=0.2, freq=220, sr=24000) -> bytes:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    a = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return encode_wav(a, sr)


def test_concat_wav():
    a = _tone_wav(seconds=0.2)
    b = _tone_wav(seconds=0.2, freq=330)
    c = concat_wav([a, b])
    assert c[:4] == b"RIFF"
    ch, sw, fr, arr = read_wav(c)
    assert arr.shape[0] > read_wav(a)[3].shape[0]


def test_encode_read_roundtrip():
    w = _tone_wav(seconds=0.3)
    ch, sw, fr, arr = read_wav(w)
    assert fr == 24000
    assert arr.size > 0


def test_no_overlap_queued():
    sink = BufferSink()
    sink.sim_dur = 0.05
    mgr = AudioPlaybackManager(sink)
    import time
    mgr.play(_tone_wav(0.05), "a", priority=1)
    mgr.play(_tone_wav(0.05), "b", priority=1)
    mgr.play(_tone_wav(0.05), "c", priority=1)
    t0 = time.time()
    while time.time() - t0 < 5 and len(sink.played) < 3:
        time.sleep(0.02)
    assert len(sink.played) == 3


def test_barge_in_interrupt():
    sink = BufferSink()
    sink.sim_dur = 0.5
    mgr = AudioPlaybackManager(sink)
    import time
    results = {}
    mgr.play(_tone_wav(0.5), "low", priority=1, on_done=lambda ab: results.setdefault("low", ab))
    time.sleep(0.05)
    assert sink.is_playing()
    mgr.play(_tone_wav(0.05), "high", priority=3, on_done=lambda ab: results.setdefault("high", ab))
    t0 = time.time()
    while time.time() - t0 < 5 and "high" not in results:
        time.sleep(0.02)
    assert results.get("low") is True
    assert results.get("high") is False
