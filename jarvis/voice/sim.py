"""
Simulated voice backends for HEADLESS stress-testing and `--sim` runner mode.

These implement the exact same MicSource / STTBackend / TTSBackend interfaces as the real
backends, but generate synthetic audio and scripted text so the full listen -> respond ->
listen loop (and every recovery path) can be exercised without a microphone or speakers.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np

from .listener import MicError, STTError, TTSError


class SimMicSource:
    def __init__(self, script, sample_rate: int = 16000, chunk_ms: int = 20,
                 schedule_interval: float = 1.3) -> None:
        self.sample_rate = sample_rate
        self.chunk_samples = int(sample_rate * chunk_ms / 1000)
        self.script = list(script)
        self.idx = 0
        self.schedule_interval = schedule_interval
        self._opened = False
        self.healthy = True
        self.current_phrase = "hello jarvis"
        self._speaking = False
        self._speech_chunks_left = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # fault injection
        self.fail_next_read = False
        self.drop_device = False

    def open(self) -> None:
        self._opened = True
        self.healthy = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._sched, name="sim-mic", daemon=True)
        self._thread.start()

    def _sched(self) -> None:
        while self._opened and not self._stop.is_set():
            time.sleep(self.schedule_interval)
            if not self.healthy or self.drop_device:
                continue
            self.current_phrase = self.script[self.idx % len(self.script)]
            self.idx += 1
            self._speaking = True
            self._speech_chunks_left = int(0.8 * 1000 / (self.chunk_samples / self.sample_rate * 1000))

    def trigger_speech(self, phrase: str = "jarvis interrupt now") -> None:
        """Force an immediate speech burst (used to test barge-in deterministically)."""
        self.current_phrase = phrase
        self._speaking = True
        self._speech_chunks_left = int(0.8 * 1000 / (self.chunk_samples / self.sample_rate * 1000))

    def read(self, n: int, timeout: float = 0.3):
        if self.fail_next_read:
            self.fail_next_read = False
            raise MicError("sim mic read failure")
        if self.drop_device:
            # simulate the OS re-attaching the device after a short gap
            if time.time() - getattr(self, "_dropped_at", 0.0) > 2.0:
                self.drop_device = False
            else:
                return None
        if not self.healthy:
            return None
        if self._speaking and self._speech_chunks_left > 0:
            self._speech_chunks_left -= 1
            if self._speech_chunks_left == 0:
                self._speaking = False
            return np.full(n, 0.35, dtype=np.float32)
        return np.zeros(n, dtype=np.float32)

    def close(self) -> None:
        self._opened = False
        self._stop.set()
        self.healthy = False

    def reload(self) -> None:
        self.drop_device = False
        self.healthy = True
        self._opened = True


class ScriptedSTT:
    def __init__(self, mic: SimMicSource) -> None:
        self.mic = mic
        self.fail_next = False

    def reload(self) -> None:
        self.fail_next = False

    def transcribe(self, audio) -> str:
        if self.fail_next:
            self.fail_next = False
            raise STTError("sim stt failure")
        # Simulate a little processing latency.
        time.sleep(0.05)
        return self.mic.current_phrase


class BeepTTS:
    def __init__(self, sample_rate: int = 16000, duration: float = 0.6) -> None:
        self.sample_rate = sample_rate
        self.duration = duration
        self.fail_next = False

    def reload(self) -> None:
        self.fail_next = False

    def synthesize(self, text: str):
        if self.fail_next:
            self.fail_next = False
            raise TTSError("sim tts failure")
        t = np.linspace(0, self.duration, int(self.sample_rate * self.duration), endpoint=False)
        return (0.2 * np.sin(2 * np.pi * 330 * t)).astype(np.float32)
