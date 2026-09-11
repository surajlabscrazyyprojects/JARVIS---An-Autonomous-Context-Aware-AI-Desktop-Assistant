"""
AudioPlaybackManager + SpeechQueue.

Design goals (from the spec):
- TTS MUST NEVER permanently block listening. Playback runs on its OWN worker thread.
- When speech finishes: release playback resources and the listener becomes available immediately.
- Barge-in: the listener can call interrupt() at any time to stop/fade TTS and free the
  audio output, so the microphone can be activated.
- No duplicate TTS workers (start() is idempotent), no orphaned threads.

`play_fn(audio: np.ndarray[float32], sample_rate: int, interrupted: threading.Event)` is
pluggable so we can use real PyAudio output, the Fish Speech server, or a silent backend
(for tests / machines without an output device).
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable, Optional

import numpy as np


class SpeechQueue(queue.Queue):
    """Queue of (audio, text) utterances waiting to be spoken."""

    def size(self) -> int:
        return self.qsize()


class AudioPlaybackManager:
    def __init__(
        self,
        sample_rate: int = 16000,
        play_fn: Optional[Callable[[np.ndarray, int, threading.Event], None]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self._play_fn = play_fn
        self._queue: "SpeechQueue" = SpeechQueue()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._playing = threading.Event()
        self._interrupted = threading.Event()
        self._lock = threading.Lock()
        self.items_played = 0
        self.items_interrupted = 0

    # ----- lifecycle -----
    def start(self) -> None:
        """Idempotent: never spawns a second worker."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._worker, name="tts-playback", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.interrupt()
        t = self._thread
        if t is not None:
            t.join(timeout=2.0)

    # ----- public API -----
    def enqueue(self, audio: Any, text: str = "", sample_rate: Optional[int] = None) -> None:
        if audio is None:
            return
        # Allow audio objects that carry their own native sample rate.
        if sample_rate is None and hasattr(audio, "sample_rate"):
            sample_rate = int(audio.sample_rate)
        self._queue.put((audio, text, sample_rate or self.sample_rate))

    def interrupt(self) -> None:
        """Stop current playback and drop everything queued."""
        with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
        self._interrupted.set()

    def is_playing(self) -> bool:
        return self._playing.is_set()

    def queue_empty(self) -> bool:
        return self._queue.empty()

    def queue_size(self) -> int:
        return self._queue.qsize()

    def wait_idle(self, timeout: Optional[float] = None) -> bool:
        """Block until nothing is playing and the queue is drained."""
        start = time.time()
        while not self._stop.is_set():
            if not self._playing.is_set() and self._queue.empty():
                return True
            if timeout is not None and (time.time() - start) > timeout:
                return False
            time.sleep(0.02)
        return False

    # ----- worker -----
    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                audio, text, sr = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            self._playing.set()
            self._interrupted.clear()
            try:
                if self._play_fn is not None:
                    self._play_fn(np.asarray(audio, dtype=np.float32), sr, self._interrupted)
                else:
                    # Silent backend: simulate duration so barge-in timing is realistic.
                    dur = max(0.1, float(np.asarray(audio).ravel().size) / max(1, self.sample_rate))
                    steps = max(1, int(dur * 10))
                    for _ in range(steps):
                        if self._interrupted.is_set() or self._stop.is_set():
                            break
                        time.sleep(0.1)
            finally:
                self._playing.clear()
                if self._interrupted.is_set():
                    self.items_interrupted += 1
                    self._interrupted.clear()
                self.items_played += 1
