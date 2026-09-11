"""
AudioPlaybackManager + sinks.

One authoritative playback path -> guarantees NO overlapping TTS (spec: single
AudioPlaybackManager, no audio overlap). Supports:
  * real playback through the system speakers (PyAudioSink)
  * priority interruption (a newer/higher-priority item cancels the current one)
  * stop() / pause() / resume()
  * cleanup of finished streams

A BufferSink is provided for deterministic automated tests (it records exactly
what was delivered to the output stage) without requiring a speaker.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from .wav import read_wav, wav_to_pcm, rms
from .log import logger


def _wav_to_pcm(wav_bytes: bytes) -> tuple[int, int, bytes]:
    fr, ch, pcm = wav_to_pcm(wav_bytes)
    return fr, ch, pcm


def _amp(wav_bytes: bytes) -> float:
    return rms(wav_bytes)


class PyAudioSink:
    """Real speaker playback via PyAudio. Supports stop/pause/resume."""

    def __init__(self, output_device_index: int | None = None):
        import pyaudio
        self._pa = pyaudio.PyAudio()
        self._out_idx = output_device_index
        self._stream = None
        self._thread = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._playing = False
        self._lock = threading.Lock()

    def play(self, wav_bytes: bytes, on_done=None):
        if self._playing:
            self.stop()
        fr, ch, data = _wav_to_pcm(wav_bytes)
        self._stop.clear()
        self._pause.clear()
        self._playing = True
        self._cur_wav = wav_bytes

        def run():
            stream = None
            try:
                stream = self._pa.open(format=pyaudio.paInt16, channels=ch,
                                      rate=fr, output=True,
                                      output_device_index=self._out_idx)
                self._stream = stream
                chunk = 4096
                i = 0
                while i < len(data):
                    if self._stop.is_set():
                        break
                    if self._pause.is_set():
                        time.sleep(0.02)
                        continue
                    end = min(i + chunk, len(data))
                    stream.write(data[i:end])
                    i = end
                stream.stop_stream()
                stream.close()
            except Exception as e:  # noqa: BLE001
                logger.error(f"[PLAYBACK] device error: {e}")
            finally:
                self._playing = False
                self._stream = None
                if on_done:
                    on_done(self._stop.is_set())

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._stream:
            try:
                self._stream.stop_stream()
            except Exception:
                pass

    def pause(self):
        self._pause.set()
        if self._stream:
            try:
                self._stream.stop_stream()
            except Exception:
                pass

    def resume(self):
        self._pause.clear()
        if self._stream:
            try:
                self._stream.start_stream()
            except Exception:
                pass

    def is_playing(self) -> bool:
        return self._playing

    def amplitude(self) -> float:
        cur = getattr(self, "_cur_wav", None)
        return _amp(cur) if self._playing and cur else 0.0

    def shutdown(self):
        try:
            self.stop()
        except Exception:
            pass
        time.sleep(0.05)
        try:
            self._pa.terminate()
        except Exception:
            pass


class BufferSink:
    """Test sink: records delivered audio; simulates real-time playback timing
    so interruption/overlap semantics can be exercised deterministically.

    Each play gets its OWN cancellation token, and a new play cancels the
    previous one (mirroring the real AudioPlaybackManager 'no overlap'
    guarantee). Stopping exits the simulation promptly so on_done fires fast.
    """

    def __init__(self):
        self.played: list[bytes] = []
        self._playing = False
        self._current_ev = None
        self.sim_dur = None  # if set, fixed simulated playback seconds (tests)
        self._lock = threading.Lock()

    def play(self, wav_bytes: bytes, on_done=None):
        with self._lock:
            if self._current_ev is not None:
                self._current_ev.set()  # cancel any in-flight clip
            ev = threading.Event()
            self._current_ev = ev
        self._playing = True
        self._cur_wav = wav_bytes
        if self.sim_dur is not None:
            dur = self.sim_dur
        else:
            fr, ch, _ = _wav_to_pcm(wav_bytes)
            dur = max(0.05, len(wav_bytes) / (fr * ch * 2 + 1))

        def run():
            step = 0.02
            elapsed = 0.0
            while elapsed < dur and not ev.is_set():
                time.sleep(step)
                elapsed += step
            self._playing = False
            with self._lock:
                if self._current_ev is ev:
                    self._current_ev = None
            if not ev.is_set():
                self.played.append(wav_bytes)
            if on_done:
                on_done(ev.is_set())

        threading.Thread(target=run, daemon=True).start()

    def stop(self):
        with self._lock:
            if self._current_ev is not None:
                self._current_ev.set()

    def pause(self):
        # No audible pause in the test sink; safe no-op.
        pass

    def resume(self):
        pass

    def is_playing(self) -> bool:
        return self._playing

    def amplitude(self) -> float:
        cur = getattr(self, "_cur_wav", None)
        return _amp(cur) if self._playing and cur else 0.0

    def shutdown(self):
        self.stop()


class AudioPlaybackManager:
    """Single owner of audio output.

    Guarantees:
      * NO audio overlap (one sink, one active clip at a time).
      * Normal-priority items are QUEUED and played sequentially (nothing is
        dropped) - the SpeechQueue worker can pop the next item while the
        current one is still rendering/playing.
      * A HIGHER-priority item INTERRUPTS the current one (barge-in), and
        `stop()` cancels everything.
    """

    def __init__(self, sink):
        self.sink = sink
        self._lock = threading.Lock()
        self._current_id = None
        self._current_priority = 0
        self._pending = []  # FIFO of (wav_bytes, item_id, priority, on_done)

    def _start(self, wav_bytes, item_id, priority, on_done):
        self._current_id = item_id
        self._current_priority = priority

        def _done(aborted):
            nxt = None
            with self._lock:
                if self._current_id == item_id:
                    self._current_id = None
                if self._pending:
                    nxt = self._pending.pop(0)
            if on_done:
                on_done(aborted)
            if nxt is not None:
                w, iid, p, cb = nxt
                self._start(w, iid, p, cb)

        self.sink.play(wav_bytes, on_done=_done)

    def play(self, wav_bytes: bytes, item_id: str, priority: int = 0,
             on_done=None):
        with self._lock:
            if self._current_id is not None:
                if priority > self._current_priority:
                    # Barge-in: drop queued items and interrupt the current one.
                    self._pending.clear()
                    try:
                        self.sink.stop()
                    except Exception:
                        pass
                else:
                    # Same/lower priority: queue so nothing is dropped.
                    self._pending.append((wav_bytes, item_id, priority, on_done))
                    return
            self._start(wav_bytes, item_id, priority, on_done)

    def stop(self):
        with self._lock:
            self._pending.clear()
        try:
            self.sink.stop()
        except Exception:
            pass

    def pause(self):
        try:
            self.sink.pause()
        except Exception:
            pass

    def resume(self):
        try:
            self.sink.resume()
        except Exception:
            pass

    def is_playing(self) -> bool:
        return self.sink.is_playing()

    def amplitude(self) -> float:
        try:
            return self.sink.amplitude()
        except Exception:  # noqa: BLE001
            return 0.0

    def shutdown(self):
        self.stop()
        try:
            self.sink.shutdown()
        except Exception:
            pass
