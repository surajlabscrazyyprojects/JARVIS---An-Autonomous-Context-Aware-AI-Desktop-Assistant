"""
VoiceService - the persistent, first-class local TTS service.

Provides the spec API (health/warmup/speak/stream/stop/pause/resume/shutdown),
loads the model ONCE, verifies synthesis before ever reporting VOICE_READY,
and drives interruption/priority/barge-in through the single
AudioPlaybackManager + SpeechQueue. Runs its own worker (conversation thread
stays unblocked). Failure recovery re-initialises ONLY the TTS engine.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

from .audio_playback import AudioPlaybackManager, BufferSink, PyAudioSink
from .character_registry import get_display_name, get_reference_id, normalize_character
from .config import VoiceConfig
from .engine import VoiceEngine, VOICE_READY, VOICE_DEGRADED, VOICE_LOADING
from .log import logger
from .speech_queue import SpeechQueue
from .tts_backend import TTSError


@dataclass
class LatencyMetrics:
    count: int = 0
    last_total: float = 0.0
    last_first_audio: float = 0.0
    rolling_total: float = 0.0
    rolling_first: float = 0.0
    worst_total: float = 0.0

    def record(self, total: float, first_audio: float):
        self.count += 1
        self.last_total = total
        self.last_first_audio = first_audio
        n = self.count
        self.rolling_total = (self.rolling_total * (n - 1) + total) / n
        self.rolling_first = (self.rolling_first * (n - 1) + first_audio) / n
        self.worst_total = max(self.worst_total, total)


def _default_sink(cfg: VoiceConfig):
    """Speakers only when playback_target requests it (else HUD renders)."""
    target = (cfg.playback_target or "hud").lower()
    try:
        if target in ("system", "both"):
            return PyAudioSink()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[TTS] real sink unavailable ({e}); using buffer sink")
    return BufferSink()


class VoiceService:
    def __init__(self, cfg: Optional[VoiceConfig] = None,
                 engine: Optional[VoiceEngine] = None,
                 backend=None, sink=None):
        self.cfg = cfg or VoiceConfig.load()
        self.engine = engine or VoiceEngine(self.cfg, backend=backend)
        if sink is None:
            sink = _default_sink(self.cfg)
        self.playback = AudioPlaybackManager(sink)
        self.queue = SpeechQueue()
        self.metrics = LatencyMetrics()
        self.emotion = self.engine.emotion
        self.state = self.engine.state

        self._running = True
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        self._lock = threading.Lock()

    # -- required API ---------------------------------------------------
    def health(self) -> dict:
        with self._lock:
            service_ok, _ = self.engine.core.health_check()
        playing = self.playback.is_playing()
        return {
            **self.engine.health(),
            "state": self.state,
            "service_ok": service_ok,
            "playing": bool(playing),
            "amplitude": round(self.playback.amplitude(), 3),
            "queue_pending": self.queue.pending(),
            "metrics": {
                "count": self.metrics.count,
                "last_total_s": round(self.metrics.last_total, 3),
                "last_first_audio_s": round(self.metrics.last_first_audio, 3),
                "avg_total_s": round(self.metrics.rolling_total, 3),
                "avg_first_audio_s": round(self.metrics.rolling_first, 3),
                "worst_total_s": round(self.metrics.worst_total, 3),
            },
            "emotion": self.emotion.to_dict(),
        }

    def warmup(self) -> tuple[bool, str]:
        self.state = VOICE_LOADING
        ok, detail = self.engine.warmup()
        self.state = VOICE_READY if ok else VOICE_DEGRADED
        return ok, detail

    def speak(self, text: str, character: Optional[str] = None, emotion: Optional[str] = None,
              priority: str = "normal", on_done: Optional[Callable] = None) -> str:
        # Snapshot character/reference at enqueue time to prevent stale voice (spec §15)
        char = normalize_character(character or self.engine.current_character)
        ref = get_reference_id(char)
        display = get_display_name(char)
        return self.queue.enqueue(text, emotion=emotion, priority=priority,
                                  meta={"enqueued": time.time(),
                                        "on_done": on_done,
                                        "character": char,
                                        "reference_id": ref,
                                        "display_name": display})

    def stream(self, text: str, character: Optional[str] = None, emotion: Optional[str] = None,
               priority: str = "normal") -> Iterator[tuple[float, bytes]]:
        """Blocking generator: yields (amplitude, wav_bytes) per chunk as the
        queue worker plays them. Used by the streaming route."""
        char = normalize_character(character or self.engine.current_character)
        for _perf, wav in self.engine.speak_stream(text, character=char, emotion=emotion,
                                                   priority=priority):
            yield self.playback.amplitude(), wav

    def get_current_voice(self) -> dict:
        return self.engine.get_current_voice()

    def set_character(self, character: str) -> bool:
        ok = self.engine.set_character(character)
        # Keep service state in sync
        self.state = self.engine.state
        return ok

    def clear_queue(self):
        self.queue.cancel_all()
        self.playback.stop()

    def stop(self):
        try:
            # Cancel any live Fish session before clearing the queue (§13).
            for it in list(self.queue._heap):
                try:
                    ev = it.get("meta", {}).get("_live_cancel")
                    if ev is not None:
                        ev.set()
                except Exception:
                    pass
        except Exception:
            pass
        self.queue.cancel_all()
        self.playback.stop()

    def pause(self):
        self.playback.pause()
        try:
            self.engine.core.pause()
        except Exception:  # noqa: BLE001
            pass

    def resume(self):
        self.playback.resume()
        try:
            self.engine.core.resume()
        except Exception:  # noqa: BLE001
            pass

    def speak_sync(self, text: str, character: Optional[str] = None, emotion: Optional[str] = None,
                   priority: str = "normal", timeout: float = 30.0) -> dict:
        evt = threading.Event()
        res = {}
        item_id = self.speak(text, character=character, emotion=emotion, priority=priority,
                             on_done=lambda aborted: (res.update(
                                 {"aborted": aborted, "item_id": item_id}),
                                 evt.set()))
        res["item_id"] = item_id
        evt.wait(timeout)
        return res

    def recover(self) -> tuple[bool, str]:
        ok, detail = self.engine.recover()
        self.state = VOICE_READY if ok else VOICE_DEGRADED
        return ok, detail

    # -- worker ---------------------------------------------------------
    def _worker_loop(self):
        while self._running:
            item = self.queue.pop()
            if item is None:
                time.sleep(0.02)
                continue
            self._process(item)

    def _process(self, item: dict):
        t_req = item["meta"].get("enqueued", time.time())
        iid = item["id"]
        prio = item["priority"]
        done_cb = item["meta"].get("on_done")
        aborted = False
        first = 0.0
        recorded = threading.Event()

        def _call_done(aborted_flag: bool):
            if recorded.is_set():
                return
            recorded.set()
            if done_cb:
                try:
                    done_cb(aborted_flag)
                except Exception:  # noqa: BLE001
                    pass

        def _record_metrics():
            total = time.time() - t_req
            fa = first if first != 0.0 else total
            with self._lock:
                self.metrics.record(total, fa)

        try:
            if self.cfg.streaming:
                # Pipelined: generate chunk N while chunk N-1 plays.
                # Each synthesis item owns a cancel token so barge-in stops the
                # live socket immediately (no duplicate synthesis after interrupt).
                item_cancel = threading.Event()
                item["meta"]["_live_cancel"] = item_cancel

                def _chunk_aborted(ab: bool):
                    if ab:
                        try:
                            item_cancel.set()
                        except Exception:
                            pass
                        _call_done(True)

                char = item["meta"].get("character") or self.engine.current_character
                for _perf, wav in self.engine.speak_stream(
                        item["text"], character=char, emotion=item.get("emotion"),
                        cancel=item_cancel):
                    if self.queue.is_cancelled(iid):
                        try:
                            item_cancel.set()
                        except Exception:
                            pass
                        aborted = True
                        break
                    if first == 0.0:
                        first = time.time() - t_req
                    # Each chunk's on_done reports only aborts; success is
                    # reported after the last chunk has fully drained.
                    self.playback.play(wav, iid, prio,
                                       on_done=lambda ab, _cb=_chunk_aborted: _cb(bool(ab)) if ab else None)
                _record_metrics()
                if aborted or self.queue.is_cancelled(iid):
                    _call_done(True)
                    return
                def _poll_stream():
                    while self._running and self.playback.is_playing():
                        # Barge-in will stop the sink -> is_playing becomes False.
                        time.sleep(0.02)
                    was_cancelled = self.queue.is_cancelled(iid)
                    self.queue.mark_done(iid)
                    # If we are here because a higher-priority item barged in,
                    # its manager call already stopped the sink and the chunk's
                    # on_done fired with aborted=True -> _call_done already True.
                    # Otherwise this is a natural finish.
                    if not recorded.is_set():
                        _call_done(bool(was_cancelled))
                threading.Thread(target=_poll_stream, daemon=True).start()
                return
            else:
                char = item["meta"].get("character") or self.engine.current_character
                wav = self.engine.speak(item["text"], character=char, emotion=item.get("emotion"),
                                        priority=prio)
                if self.queue.is_cancelled(iid):
                    _record_metrics()
                    _call_done(True)
                    return
                perf = self.engine.planner.director.classify(
                    item["text"], override=item.get("emotion"),
                    mode=self.cfg.emotion_mode,
                    base_intensity=self.cfg.emotion_intensity)
                self.emotion.update_from_performance(perf, self.cfg.voice)
                first = time.time() - t_req
                _record_metrics()

                def _on_play_done(fin_aborted: bool):
                    _call_done(bool(fin_aborted))

                self.playback.play(wav, iid, prio, on_done=_on_play_done)
                return
        except TTSError as e:
            logger.error(f"[TTS] item {iid} failed: {e}")
            _record_metrics()
            _call_done(True)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[TTS] item {iid} unexpected failure: {e}")
            _record_metrics()
            _call_done(True)

    # -- shutdown -------------------------------------------------------
    def shutdown(self):
        self._running = False
        self.stop()
        try:
            self.playback.shutdown()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.engine.shutdown()
        except Exception:  # noqa: BLE001
            pass