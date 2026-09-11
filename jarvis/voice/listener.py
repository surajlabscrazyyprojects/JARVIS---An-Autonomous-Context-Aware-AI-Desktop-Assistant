"""
Self-healing J.A.R.V.I.S. voice listener.

ROOT CAUSE OF THE ORIGINAL BUG
------------------------------
The previous listener was the browser "Web Speech API" (webkitSpeechRecognition) inside
the HUD. That API is fundamentally unreliable for an "always on" assistant:
  * After a few utterances `onend` fires and recognition does NOT auto-restart.
  * `onerror` ('no-speech', 'network', 'aborted', 'audio-capture', 'not-allowed') kills it.
  * Calling start() again too quickly throws InvalidStateError, so the restart dies silently.
  * It depends on Google's network service -> network blips stop listening permanently.
There was no state machine, no per-component recovery, no watchdog, and no barge-in.

THIS MODULE FIXES THE ARCHITECTURE
-----------------------------------
A single dedicated Python service owns the microphone (PyAudio) and does offline STT
(faster-whisper) so network failures cannot stop listening. It runs an explicit state
machine with a watchdog that force-resets any state that hangs, per-component recovery
functions (mic / stt / tts / audio device / conversation state), and a separate
interruptible TTS playback thread so speaking never blocks listening and the user can
barge in.

Components are injected (MicSource / STTBackend / TTSBackend / on_utterance) so the exact
same loop can be stress-tested headlessly with simulated audio (see tests/...).
"""
from __future__ import annotations

import concurrent.futures
import logging
import queue
import threading
import time
import traceback
from enum import Enum
from typing import Any, Callable, Optional

import numpy as np

from .audio_session import AudioSessionManager, SessionState
from .dsp import DspPipeline
from .playback import AudioPlaybackManager
from .vad import EnergyVAD

logger = logging.getLogger("jarvis.voice.listener")

# --------------------------------------------------------------------------
# State machine
# --------------------------------------------------------------------------
class ListenerState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    ACTING = "ACTING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    RECOVERING = "RECOVERING"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


# States that are allowed to hang and therefore get a watchdog timeout.
HANGABLE = {
    ListenerState.TRANSCRIBING,
    ListenerState.THINKING,
    ListenerState.ACTING,
    ListenerState.RECOVERING,
    ListenerState.SPEAKING,
    ListenerState.ERROR,
}

STOP_COMMANDS = {"stop jarvis", "stop jarvis.", "quit", "exit", "jarvis stop", "shut down jarvis"}

# --------------------------------------------------------------------------
# Exceptions (so recovery can be component-specific)
# --------------------------------------------------------------------------
class VoiceError(Exception):
    pass

class MicError(VoiceError):
    pass

class STTError(VoiceError):
    pass

class TTSError(VoiceError):
    pass

class ThinkError(VoiceError):
    pass


# --------------------------------------------------------------------------
# Timeout helper: run a blocking call with a deadline. On timeout the call
# keeps running on a pooled thread (rare; logged) but we proceed so the loop
# never stalls.
# --------------------------------------------------------------------------
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="voice-work")


def run_with_timeout(fn, timeout: float, what: str):
    fut = _EXECUTOR.submit(fn)
    try:
        result = fut.result(timeout=timeout)
        return result, True
    except concurrent.futures.TimeoutError:
        logger.warning("[watchdog] %s timed out after %.1fs (proceeding; worker may linger)", what, timeout)
        return None, False
    except Exception as exc:  # noqa: BLE001
        logger.exception("[voice] %s raised: %s", what, exc)
        return None, False


# --------------------------------------------------------------------------
# MicSource / STTBackend / TTSBackend are duck-typed interfaces:
#   MicSource:  open(), close(), read(n, timeout) -> np.ndarray[float32]|None, healthy(bool)
#   STTBackend: transcribe(frames) -> str   ("" means unknown speech, not an error)
#   TTSBackend: synthesize(text) -> np.ndarray[float32]|None  (None => no audio)
# --------------------------------------------------------------------------

USER_STATUS = {
    ListenerState.LISTENING: "Listening",
    ListenerState.TRANSCRIBING: "Hearing you",
    ListenerState.THINKING: "Thinking",
    ListenerState.ACTING: "Working",
    ListenerState.SPEAKING: "Speaking",
    ListenerState.INTERRUPTED: "Interrupted",
    ListenerState.RECOVERING: "Recovering voice",
    ListenerState.ERROR: "Error",
    ListenerState.STOPPED: "Stopped",
    ListenerState.IDLE: "Ready",
}


class VoiceListener:
    def __init__(
        self,
        mic,
        stt,
        tts,
        on_utterance: Callable[[str], Optional[str]],
        playback: Optional[AudioPlaybackManager] = None,
        status_cb: Optional[Callable[[ListenerState, str], None]] = None,
        sample_rate: int = 16000,
        *,
        listen_timeout: float = 12.0,
        silence_timeout: float = 0.7,
        max_phrase: float = 18.0,
        transcribe_timeout: float = 30.0,
        think_timeout: float = 60.0,
        act_timeout: float = 60.0,
        speak_timeout: float = 120.0,
        recover_timeout: float = 20.0,
        recover_backoff: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.mic = mic
        self.stt = stt
        self.tts = tts
        self.on_utterance = on_utterance
        self.playback = playback or AudioPlaybackManager(sample_rate=sample_rate)
        self.status_cb = status_cb
        self.sample_rate = sample_rate
        self.vad = EnergyVAD(sample_rate=sample_rate)
        # Professional DSP pipeline + single-owner audio session (AEC -> HPF -> NS -> AGC -> VAD)
        self.dsp = DspPipeline(sample_rate=sample_rate, vad=self.vad)
        self.session = AudioSessionManager(mic=self.mic, playback=self.playback, vad=self.vad, sample_rate=sample_rate)

        self.chunk_samples = int(sample_rate * 0.02)  # 20 ms
        self.chunk_time = 0.02

        self.listen_timeout = listen_timeout
        self.silence_timeout = silence_timeout
        self.max_phrase = max_phrase
        self.transcribe_timeout = transcribe_timeout
        self.think_timeout = think_timeout
        self.act_timeout = act_timeout
        self.speak_timeout = speak_timeout
        self.recover_timeout = recover_timeout
        self.recover_backoff = recover_backoff
        self.max_retries = max_retries

        self._state = ListenerState.IDLE
        self._last_transition = time.time()
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._cancel = threading.Lock()  # held briefly to abort a hung phase
        self._listener_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self.conversations = 0
        self.recoveries = 0
        self._mic_held = threading.Event()  # mic is open and owned by listener thread

        # user-facing status hook
        self._status("Ready")

    # ------------------------------------------------------------------ #
    # state machine
    # ------------------------------------------------------------------ #
    @property
    def state(self) -> ListenerState:
        return self._state

    def _set_state(self, new: ListenerState) -> None:
        with self._state_lock:
            if self._state == new:
                return
            old = self._state
            self._state = new
            self._last_transition = time.time()
        if new in (ListenerState.RECOVERING, ListenerState.ERROR):
            self.recoveries += 1
        logger.info("[state] %s -> %s", old.value, new.value)
        self._status(USER_STATUS.get(new, new.value))

    def _status(self, text: str) -> None:
        if self.status_cb:
            try:
                self.status_cb(self._state, text)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def health_check(self) -> dict:
        """Verify mic / stt / tts actually work before claiming 'Listening'."""
        report = {"mic": False, "stt": False, "tts": False, "ok": False}
        try:
            self._ensure_mic()
            report["mic"] = True
        except Exception as exc:  # noqa: BLE001
            logger.error("[health] mic failed: %s", exc)
            return report
        # STT smoke test on a short silence (must not raise; "" is acceptable)
        try:
            self.stt.transcribe(np.zeros(self.chunk_samples, dtype=np.float32))
            report["stt"] = True
        except Exception as exc:  # noqa: BLE001
            logger.error("[health] stt failed: %s", exc)
        try:
            audio = self.tts.synthesize("health check")
            if audio is not None:
                report["tts"] = True
        except Exception as exc:  # noqa: BLE001
            logger.error("[health] tts failed: %s", exc)
        report["ok"] = report["mic"] and report["stt"]
        return report

    def start(self) -> None:
        self.playback.start()
        self._stop.clear()
        if self._listener_thread is None or not self._listener_thread.is_alive():
            self._listener_thread = threading.Thread(
                target=self._run, name="jarvis-listener", daemon=True
            )
            self._listener_thread.start()
        if self._watchdog_thread is None or not self._watchdog_thread.is_alive():
            self._watchdog_thread = threading.Thread(
                target=self._watchdog, name="jarvis-watchdog", daemon=True
            )
            self._watchdog_thread.start()

    def stop(self) -> None:
        logger.info("[voice] stop requested")
        self._stop.set()
        self.playback.interrupt()
        self.playback.stop()
        try:
            self.mic.close()
        except Exception:  # noqa: BLE001
            pass
        self._set_state(ListenerState.STOPPED)

    def join(self, timeout: float = 5.0) -> None:
        t = self._listener_thread
        if t is not None:
            t.join(timeout=timeout)
        w = self._watchdog_thread
        if w is not None:
            w.join(timeout=timeout)

    # ------------------------------------------------------------------ #
    # microphone management (stable lifecycle)
    # ------------------------------------------------------------------ #
    def _ensure_mic(self) -> None:
        if getattr(self.mic, "healthy", False) and getattr(self.mic, "_opened", False):
            return
        self.mic.open()
        # fast, non-blocking ambient calibration (startup only)
        try:
            ambient = self.mic.read(self.chunk_samples * 25, timeout=0.6)
            if ambient is not None:
                self.vad.calibrate(ambient)
        except Exception:  # noqa: BLE001
            pass
        self._mic_held.set()

    # ------------------------------------------------------------------ #
    # main loop
    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        logger.info("[voice] listener thread started")
        while not self._stop.is_set():
            try:
                # 1) make sure we have a working microphone
                try:
                    self._ensure_mic()
                except Exception as exc:  # noqa: BLE001
                    self._set_state(ListenerState.RECOVERING)
                    if not self.recover_microphone():
                        time.sleep(1.0)
                        continue  # keep trying forever; NEVER die

                # 2) LISTEN
                self._set_state(ListenerState.LISTENING)
                frames = self._capture_phrase()
                if self._stop.is_set():
                    break
                if frames is None:
                    # pure timeout / silence -> normal, just keep listening
                    continue

                # 3) TRANSCRIBE
                self._set_state(ListenerState.TRANSCRIBING)
                text = self._transcribe(frames)
                if not text or not text.strip():
                    logger.info("[voice] unknown speech (empty) -> back to listening")
                    continue
                text_s = text.strip()

                # 4) explicit stop command
                if text_s.lower() in STOP_COMMANDS or text_s.lower().startswith("stop jarvis"):
                    logger.info("[voice] stop command recognized: %r", text_s)
                    self.stop()
                    return

                # 5) THINK + ACT
                self._set_state(ListenerState.THINKING)
                reply = self._think(text_s)

                # 6) SPEAK (or just return to listening)
                if reply:
                    self._speak(reply)
                self._set_state(ListenerState.LISTENING)
                self.conversations += 1

            except MicError as exc:
                self._log_err("microphone", exc)
                self._set_state(ListenerState.RECOVERING)
                recovered = self.recover_microphone()
                # Back off so a dead device can NOT peg the CPU with an error storm.
                time.sleep(self.recover_backoff)
                if not recovered:
                    continue
            except STTError as exc:
                self._log_err("stt", exc)
                self._set_state(ListenerState.RECOVERING)
                self.recover_stt()
            except TTSError as exc:
                self._log_err("tts", exc)
                self._set_state(ListenerState.RECOVERING)
                self.recover_tts()
            except ThinkError as exc:
                self._log_err("think", exc)
                self.reset_conversation_state()
            except Exception as exc:  # noqa: BLE001
                self._log_err("unexpected", exc, tb=True)
                self._set_state(ListenerState.ERROR)
                self.reset_conversation_state()
                self.recover_audio_device()
            else:
                # If a watchdog cancellation happened mid-phase, clear it and
                # make sure we are back to LISTENING (never stuck).
                if self._cancel.locked():
                    self._cancel.release()
        logger.info("[voice] listener thread exiting (state=%s)", self._state.value)

    # ------------------------------------------------------------------ #
    # capture (VAD endpointing) -- single reader, no blocking forever
    # ------------------------------------------------------------------ #
    def _capture_phrase(self):
        frames = []
        speaking = False
        silence_chunks = 0
        speech_chunks = 0
        no_speech_chunks = 0
        max_silence = int(self.silence_timeout / self.chunk_time)
        max_no_speech = int(self.listen_timeout / self.chunk_time)
        max_phrase_chunks = int(self.max_phrase / self.chunk_time)

        while not self._stop.is_set():
            if self._cancel.locked():
                return None
            try:
                chunk = self.mic.read(self.chunk_samples, timeout=self.chunk_time + 0.1)
            except Exception as exc:  # noqa: BLE001
                raise MicError(f"read failed: {exc}") from exc
            if chunk is None:
                raise MicError("mic returned None")
            no_speech_chunks += 1

            # --- PROFESSIONAL DSP: AEC -> HPF -> NS -> AGC -> VAD ---
            # Single pipeline that suppresses JARVIS TTS echo + system audio + noise
            # before VAD ever sees the frame. This is the acoustic fix, not a prompt trick.
            clean_chunk, dsp_m = self.session.process_capture(chunk)
            # Use clean audio for VAD decision (echo-reduced)
            if self.vad.is_speech(clean_chunk, playback_active=self.playback.is_playing() if hasattr(self.playback, "is_playing") else False):
                speaking = True
                silence_chunks = 0
                speech_chunks += 1
                frames.append(clean_chunk)
                no_speech_chunks = 0
            else:
                if speaking:
                    silence_chunks += 1
                    frames.append(chunk)
                    if silence_chunks >= max_silence:
                        break
                elif no_speech_chunks >= max_no_speech:
                    # timeout with no speech -> normal, not an error
                    return None

            if speech_chunks >= max_phrase_chunks:
                break

        return frames if frames else None

    # ------------------------------------------------------------------ #
    # transcribe / think / speak
    # ------------------------------------------------------------------ #
    def _transcribe(self, frames) -> str:
        audio = np.concatenate([np.asarray(f, dtype=np.float32).ravel() for f in frames])
        result, ok = run_with_timeout(
            lambda: self.stt.transcribe(audio), self.transcribe_timeout, "stt"
        )
        if not ok:
            raise STTError("transcription timed out")
        if result is None:
            raise STTError("stt returned None")
        return result

    def _think(self, text: str) -> Optional[str]:
        def job():
            return self.on_utterance(text)
        result, ok = run_with_timeout(job, self.think_timeout, "think")
        if not ok:
            raise ThinkError("thinking timed out")
        return result

    def _speak(self, text: str) -> None:
        self._set_state(ListenerState.SPEAKING)
        self.session.set_state(SessionState.SPEAKING)
        audio = self._synthesize_with_recovery(text)
        if audio is not None:
            # Publish render reference to AEC so mic echo of THIS audio is suppressed
            try:
                import numpy as np
                pcm = np.asarray(audio, dtype=np.float32).ravel()
                # Push in 20ms chunks to AEC for proper tail handling
                for i in range(0, len(pcm), 320):
                    self.session.on_render(pcm[i:i+320])
            except Exception:
                pass
            self.playback.enqueue(audio, text)

        # Barge-in monitor: keep reading the mic while speaking. If the user
        # starts talking, stop TTS immediately and free the audio output.
        deadline = time.time() + self.speak_timeout
        while (self.playback.is_playing() or not self.playback.queue_empty()) and not self._stop.is_set():
            if time.time() > deadline:
                logger.warning("[voice] speak deadline reached -> interrupt")
                self.playback.interrupt()
                break
            if self._cancel.locked():
                self.playback.interrupt()
                break
            try:
                chunk = self.mic.read(self.chunk_samples, timeout=self.chunk_time + 0.1)
            except Exception:  # noqa: BLE001
                chunk = None
            # Barge-in: run through full DSP (AEC suppresses our own voice)
            if chunk is not None:
                clean_barge, _ = self.session.process_capture(chunk)
                if self.vad.is_speech(clean_barge, playback_active=True):
                    self._set_state(ListenerState.INTERRUPTED)
                    self.playback.interrupt()
                    # small yield so the playback thread releases the output device
                    time.sleep(0.05)
                    break
            time.sleep(0.005)
        self.playback.wait_idle(timeout=self.speak_timeout)
        self.session.set_state(SessionState.LISTENING)
        self._set_state(ListenerState.LISTENING)

    def _synthesize_with_recovery(self, text: str):
        for attempt in range(self.max_retries):
            try:
                audio = self.tts.synthesize(text)
                return audio
            except Exception as exc:  # noqa: BLE001
                logger.warning("[voice] tts attempt %d failed: %s", attempt + 1, exc)
                self.recover_tts()
        raise TTSError("tts permanently failed after retries")

    # ------------------------------------------------------------------ #
    # recovery functions (NEVER restart the whole process for routine faults)
    # ------------------------------------------------------------------ #
    def recover_microphone(self) -> bool:
        self._set_state(ListenerState.RECOVERING)
        self._status("Recovering microphone")
        for attempt in range(self.max_retries):
            try:
                try:
                    self.mic.close()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.3 * (attempt + 1))
                self.mic.open()
                # Verify we can ACTUALLY read audio before declaring success, so a
                # still-dead device is reported as failed and the loop backs off
                # (instead of spinning at 100% CPU claiming "recovered").
                ok = False
                ambient = None
                for _ in range(3):
                    try:
                        ambient = self.mic.read(self.chunk_samples * 10, timeout=0.5)
                    except Exception:  # noqa: BLE001
                        ambient = None
                    if ambient is not None:
                        ok = True
                        break
                if ok:
                    self.vad.calibrate(ambient)
                    self._mic_held.set()
                    logger.info("[recover] microphone OK after %d tries", attempt + 1)
                    self._set_state(ListenerState.LISTENING)
                    return True
                logger.warning("[recover] mic still returns no audio (attempt %d)", attempt + 1)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[recover] mic retry %d failed: %s", attempt + 1, exc)
        logger.error("[recover] microphone unavailable after retries")
        return False

    def recover_stt(self) -> None:
        self._set_state(ListenerState.RECOVERING)
        self._status("Recovering voice")
        try:
            if hasattr(self.stt, "reload"):
                self.stt.reload()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[recover] stt reload failed: %s", exc)
        logger.info("[recover] stt recovery attempted")

    def recover_tts(self) -> None:
        self._set_state(ListenerState.RECOVERING)
        try:
            if hasattr(self.tts, "reload"):
                self.tts.reload()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[recover] tts reload failed: %s", exc)
        logger.info("[recover] tts recovery attempted")

    def recover_audio_device(self) -> None:
        self._set_state(ListenerState.RECOVERING)
        self._status("Recovering audio")
        try:
            self.playback.interrupt()
        except Exception:  # noqa: BLE001
            pass
        if not self.recover_microphone():
            time.sleep(0.5)

    def reset_conversation_state(self) -> None:
        """Clear any per-turn buffers / flags so one bad turn can't corrupt the next."""
        if self._cancel.locked():
            try:
                self._cancel.release()
            except Exception:  # noqa: BLE001
                pass
        logger.info("[recover] conversation state reset")

    # ------------------------------------------------------------------ #
    # watchdog: force-reset any state that hangs past its timeout
    # ------------------------------------------------------------------ #
    def _watchdog(self) -> None:
        while not self._stop.is_set():
            time.sleep(0.5)
            state = self._state
            timeout = {
                ListenerState.TRANSCRIBING: self.transcribe_timeout,
                ListenerState.THINKING: self.think_timeout,
                ListenerState.ACTING: self.act_timeout,
                ListenerState.RECOVERING: self.recover_timeout,
                ListenerState.SPEAKING: self.speak_timeout,
                ListenerState.ERROR: 10.0,
            }.get(state)
            if timeout is None:
                continue
            with self._state_lock:
                stuck = (time.time() - self._last_transition) > timeout
            if not stuck:
                continue
            logger.warning("[watchdog] state %s stuck > %.1fs -> resetting", state.value, timeout)
            self.recoveries += 1
            # cancel the hung phase
            if not self._cancel.locked():
                try:
                    self._cancel.acquire()
                except Exception:  # noqa: BLE001
                    pass
            if state == ListenerState.TRANSCRIBING:
                self.recover_stt()
            elif state == ListenerState.SPEAKING:
                self.playback.interrupt()
                self.recover_audio_device()
            elif state == ListenerState.RECOVERING:
                self.reset_conversation_state()
            else:
                self.reset_conversation_state()
            # release cancel and return to listening
            if self._cancel.locked():
                try:
                    self._cancel.release()
                except Exception:  # noqa: BLE001
                    pass
            self._set_state(ListenerState.LISTENING)

    # ------------------------------------------------------------------ #
    # logging helper
    # ------------------------------------------------------------------ #
    def _log_err(self, component: str, exc: Exception, tb: bool = False) -> None:
        dur = time.time() - self._last_transition
        logger.error(
            "[error] component=%s state=%s exception=%s duration=%.2fs",
            component, self._state.value, repr(exc), dur,
        )
        if tb:
            logger.error(traceback.format_exc())
