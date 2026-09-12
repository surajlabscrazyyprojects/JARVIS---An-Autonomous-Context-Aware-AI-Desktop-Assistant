from types import SimpleNamespace

import numpy as np

from jarvis.voice.backends import WhisperSTT


def test_whisper_uses_automatic_language_detection_and_fast_decode():
    calls = {}

    class FakeWhisper:
        def transcribe(self, audio, **kwargs):
            calls.update(kwargs)
            return [SimpleNamespace(text="नमस्ते" )], SimpleNamespace(language="hi")

    stt = WhisperSTT()
    stt._model = FakeWhisper()
    assert stt.transcribe(np.ones(1600, dtype=np.float32)) == "नमस्ते"
    assert calls["language"] is None
    assert calls["beam_size"] == 1
    assert calls["best_of"] == 1
    assert calls["vad_filter"] is True
