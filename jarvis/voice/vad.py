"""
Energy-based Voice Activity Detection.

Why this exists:
- The previous listener relied on the browser Web Speech API (webkitSpeechRecognition)
  which stops after a few utterances and depends on Google's network service.
- We own the microphone directly via PyAudio and need our own lightweight VAD so we can
  stay "always listening" without re-opening the mic for every sentence.
- Calibration is done ONCE at startup (short ambient window) and adapts slowly during
  runtime. We never block the conversation for long ambient calibration per utterance.
"""
from __future__ import annotations

import numpy as np


class EnergyVAD:
    def __init__(self, sample_rate: int = 16000, frame_ms: int = 20) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = int(sample_rate * frame_ms / 1000)
        self.noise_floor = 1e-3
        self.speech_threshold = 0.02
        self._calibrated = False
        # --- Playback-aware echo suppression ---
        self._playback_active = False
        self._playback_rms = 0.0
        # --- webrtcvad (optional, more robust to stationary noise/crowd) ---
        self._webrtc_vad = None
        try:
            import webrtcvad  # type: ignore
            self._webrtc_vad = webrtcvad.Vad(2)  # aggressiveness 2 (0-3)
        except Exception:
            pass

    # ----- calibration (fast, non-blocking) -----
    def calibrate(self, frames: np.ndarray) -> None:
        """Calibrate the noise floor from a short ambient sample (startup only)."""
        rms = self._rms(frames)
        # set the floor a little above the observed ambient energy
        self.noise_floor = max(1e-4, rms * 1.5 + 1e-4)
        self.speech_threshold = max(self.noise_floor * 3.0, 0.02)
        self._calibrated = True

    def set_playback_state(self, active: bool, rms: float = 0.0) -> None:
        """Tell VAD whether JARVIS is currently speaking (for echo cancellation)."""
        self._playback_active = bool(active)
        self._playback_rms = float(rms)

    # ----- core -----
    def _rms(self, frame: np.ndarray) -> float:
        if frame is None or frame.size == 0:
            return 0.0
        f = np.asarray(frame, dtype=np.float32)
        if f.dtype == np.int16:
            f = f.astype(np.float32) / 32768.0
        f = f.ravel()
        return float(np.sqrt(np.mean(np.square(f)) + 1e-12))

    def _zero_crossing_rate(self, frame: np.ndarray) -> float:
        if frame is None or frame.size < 2:
            return 0.0
        f = np.asarray(frame, dtype=np.float32).ravel()
        # Normalize
        if f.dtype == np.int16:
            f = f.astype(np.float32) / 32768.0
        # Zero crossing rate helps distinguish speech (higher ZCR variance) from stationary noise
        zcr = float(((f[:-1] * f[1:]) < 0).sum()) / max(1, len(f) - 1)
        return zcr

    def is_speech(self, frame: np.ndarray, playback_active: bool | None = None, playback_rms: float | None = None) -> bool:
        rms = self._rms(frame)
        # Update playback state if provided explicitly (overrides set_playback_state)
        if playback_active is not None:
            self._playback_active = bool(playback_active)
        if playback_rms is not None:
            self._playback_rms = float(playback_rms)

        # Slowly adapt the noise floor so the detector does not go stale if the
        # environment gets quieter/louder, but never below a sane minimum.
        # Do NOT adapt while playback is active (would learn the echo as noise).
        if not self._playback_active:
            self.noise_floor = max(1e-4, self.noise_floor * 0.999 + rms * 0.001)
        threshold = max(self.noise_floor * 3.0, 0.012)

        # --- ECHO CANCELLATION: when JARVIS is speaking, require MUCH louder signal ---
        # The mic will pick up speaker output acoustically. We require the user to be
        # significantly louder than the playback reference to be considered a barge-in.
        if self._playback_active:
            # Need at least 2.8x the playback RMS + adaptive floor to count as user speech
            # Also need 3.2x threshold — this makes computer audio alone insufficient
            echo_threshold = max(threshold * 3.2, self._playback_rms * 2.8 + 0.015)
            threshold = max(threshold, echo_threshold)

        self.speech_threshold = threshold
        if rms <= threshold:
            return False

        # --- Voicing check: speech has higher zero-crossing variance than stationary noise ---
        # Crowd noise / hum tends to have low or very high static ZCR; speech is in-between
        zcr = self._zero_crossing_rate(frame)
        # Speech typically 0.05 - 0.40 ZCR at 16kHz 20ms frames; pure tone/noise is outside
        if not (0.03 < zcr < 0.55):
            # Still allow very loud signals (user shouting close to mic) even if ZCR odd
            if rms < threshold * 1.8:
                return False

        # --- webrtcvad as secondary gate (if available) for crowd-noise rejection ---
        if self._webrtc_vad is not None and not self._playback_active:
            # webrtcvad expects 10ms/20ms/30ms of 16k mono int16
            try:
                # Need exactly 320 samples (20ms @16k) or 160 (10ms) or 480 (30ms)
                f = np.asarray(frame, dtype=np.float32).ravel()
                if f.dtype != np.int16:
                    # Convert float32 [-1,1] to int16
                    pcm = (np.clip(f, -1.0, 1.0) * 32767).astype(np.int16)
                else:
                    pcm = f
                # webrtcvad needs 10/20/30ms — we have 20ms (320 samples)
                if len(pcm) == 320:
                    is_speech_webrtc = self._webrtc_vad.is_speech(pcm.tobytes(), 16000)
                    # If webrtc says NO and we're not super loud, trust it (filters stationary noise)
                    if not is_speech_webrtc and rms < threshold * 2.5:
                        return False
            except Exception:
                pass

        return True
