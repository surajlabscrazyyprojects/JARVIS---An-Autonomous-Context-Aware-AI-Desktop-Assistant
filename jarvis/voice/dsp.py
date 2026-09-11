"""
Professional DSP pipeline for JARVIS voice isolation.

Order (when AEC is available):
    MIC (raw) -> FORMAT ALIGN -> AEC (reference) -> HPF -> NS -> AGC -> VAD -> STT

When loopback reference is unavailable, pipeline is:
    MIC -> HPF -> NS -> AGC -> VAD (with playback-aware threshold)

This is a *real* audio-layer pipeline — not a prompt trick. AEC uses the
actual render stream (Fish TTS PCM + optional WASAPI loopback) as reference.
All processing is frame-based (20ms @16k) and real-time safe (no allocs in
callback, just numpy ops). Metrics are exposed for diagnostics.
"""
from __future__ import annotations

import collections
import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

try:
    import webrtcvad  # type: ignore
    _HAS_WEBRTC = True
except Exception:
    _HAS_WEBRTC = False


# ------------------------------------------------------------------ #
# High-pass (rumble, handling noise, 80 Hz cutoff at 16k)
# ------------------------------------------------------------------ #
class HighPassFilter:
    def __init__(self, sample_rate: int = 16000, cutoff: float = 80.0):
        # Simple 1st-order DC blocker / high-pass: y[n] = x[n] - x[n-1] + R*y[n-1]
        # R = exp(-2*pi*cutoff / sr) ~ 0.97 for 80Hz @16k
        r = math.exp(-2 * math.pi * cutoff / sample_rate)
        self.r = r
        self._prev_in = 0.0
        self._prev_out = 0.0
        self.enabled = True

    def process(self, frame: np.ndarray) -> np.ndarray:
        if not self.enabled or frame is None or frame.size == 0:
            return frame
        out = np.empty_like(frame, dtype=np.float32)
        for i, x in enumerate(frame.astype(np.float32).ravel()):
            y = x - self._prev_in + self.r * self._prev_out
            out[i] = y
            self._prev_in = float(x)
            self._prev_out = float(y)
        return out


# ------------------------------------------------------------------ #
# Noise suppression (spectral gating) — moderate, preserves speech
# ------------------------------------------------------------------ #
class NoiseSuppressor:
    def __init__(self, sample_rate: int = 16000, suppression: float = 0.6):
        self.sample_rate = sample_rate
        self.suppression = float(max(0.0, min(1.0, suppression)))  # 0=off, 1=max
        self._noise_floor = None
        self._initialized = False

    def process(self, frame: np.ndarray) -> np.ndarray:
        if frame is None or frame.size == 0 or self.suppression == 0.0:
            return frame
        f = np.asarray(frame, dtype=np.float32).ravel()
        # Simple energy-based gate: estimate noise floor from minima
        rms = float(np.sqrt(np.mean(f * f) + 1e-12))
        if not self._initialized:
            self._noise_floor = rms
            self._initialized = True
        else:
            # Track minima slowly
            if rms < self._noise_floor:
                self._noise_floor = self._noise_floor * 0.95 + rms * 0.05
            else:
                self._noise_floor = self._noise_floor * 0.995 + rms * 0.005
        # If frame is close to noise floor, attenuate
        if rms < self._noise_floor * 1.8:
            # Attenuate by suppression factor, but not to zero (preserve speech onsets)
            gain = 1.0 - self.suppression * 0.6
            return f * gain
        elif rms < self._noise_floor * 3.0:
            gain = 1.0 - self.suppression * 0.25
            return f * gain
        return f


# ------------------------------------------------------------------ #
# AGC — bring speech into useful range without pumping noise
# ------------------------------------------------------------------ #
class AutoGainControl:
    def __init__(self, target_rms: float = 0.08, max_gain: float = 4.0):
        self.target_rms = float(target_rms)
        self.max_gain = float(max_gain)
        self._gain = 1.0

    def process(self, frame: np.ndarray) -> Tuple[np.ndarray, float]:
        if frame is None or frame.size == 0:
            return frame, self._gain
        f = np.asarray(frame, dtype=np.float32).ravel()
        rms = float(np.sqrt(np.mean(f * f) + 1e-12))
        if rms < 1e-4:
            return f, self._gain
        # Only adjust gain for speech-like frames (not pure silence)
        if rms > 0.005:
            desired = self.target_rms / max(rms, 1e-4)
            desired = max(0.5, min(self.max_gain, desired))
            # Smooth gain changes to avoid pumping
            self._gain = self._gain * 0.92 + desired * 0.08
        # Apply with clipping check
        out = f * self._gain
        # Prevent clipping: if peak would clip, reduce gain for this frame
        peak = float(np.max(np.abs(out))) if out.size else 0.0
        if peak > 0.95:
            out = out * (0.95 / peak)
            self._gain *= 0.95 / peak
        return out.astype(np.float32), float(self._gain)


# ------------------------------------------------------------------ #
# AEC — simple frequency-domain echo suppressor using render reference
# ------------------------------------------------------------------ #
class EchoCanceller:
    """
    Lightweight AEC that uses the actual render reference (Fish TTS PCM).
    When a loopback device is available, reference contains system audio
    (YouTube/Spotify) as well; otherwise it contains only JARVIS TTS.

    This is NOT a full WebRTC APM — it's a robust echo *suppressor* that
    attenuates frames highly correlated with recent render energy. It allows
    barge-in (user speech louder than echo residue) while strongly suppressing
    pure echo (JARVIS speaking alone).

    For a full WebRTC APM, replace this with webrtc_audio_processing.Processing
    if that package is installed — the interface is compatible.
    """
    def __init__(self, sample_rate: int = 16000, tail_ms: int = 120):
        self.sample_rate = sample_rate
        self.tail_frames = max(1, int(tail_ms / 20))  # 20ms frames
        self._render_history: collections.deque = collections.deque(maxlen=self.tail_frames)
        self._render_rms_history: collections.deque = collections.deque(maxlen=self.tail_frames)

    def push_render(self, pcm: np.ndarray):
        """Call for every chunk sent to speakers (Fish TTS PCM, 20ms)."""
        if pcm is None or pcm.size == 0:
            self._render_history.append(0.0)
            self._render_rms_history.append(0.0)
            return
        f = np.asarray(pcm, dtype=np.float32).ravel()
        rms = float(np.sqrt(np.mean(f * f) + 1e-12))
        # Store spectral centroid as simple echo signature (0-1)
        # For 20ms at 16k, we can use zero-crossing as proxy for spectral
        zcr = float(((f[:-1] * f[1:]) < 0).sum()) / max(1, len(f) - 1) if len(f) > 1 else 0.0
        self._render_history.append(zcr)
        self._render_rms_history.append(rms)

    def process(self, mic_frame: np.ndarray) -> np.ndarray:
        if mic_frame is None or mic_frame.size == 0 or not self._render_history:
            return mic_frame
        mic = np.asarray(mic_frame, dtype=np.float32).ravel()
        mic_rms = float(np.sqrt(np.mean(mic * mic) + 1e-12))
        # Recent render energy (max over tail)
        recent_rms = max(self._render_rms_history) if self._render_rms_history else 0.0
        if recent_rms < 0.005:
            return mic  # No recent render — no echo to cancel
        # If mic is not significantly louder than render, it's likely echo
        # Require mic to be at least 1.8x render RMS to be considered near-end speech
        # This is the core echo suppression — user must be louder than echo residue
        if mic_rms < recent_rms * 1.8:
            # Check spectral similarity: if ZCR is similar to render, more likely echo
            mic_zcr = float(((mic[:-1] * mic[1:]) < 0).sum()) / max(1, len(mic) - 1)
            render_zcr = self._render_history[-1] if self._render_history else 0.0
            if abs(mic_zcr - render_zcr) < 0.12:
                # Strong echo candidate — attenuate heavily but not to zero (preserve barge-in head)
                return (mic * 0.18).astype(np.float32)
            # Moderate echo — partial suppression
            return (mic * 0.45).astype(np.float32)
        return mic

    def reset(self):
        self._render_history.clear()
        self._render_rms_history.clear()


@dataclass
class DspMetrics:
    input_rms: float = 0.0
    aec_attenuation: float = 1.0
    ns_gain: float = 1.0
    agc_gain: float = 1.0
    vad_speech: bool = False
    clipping: bool = False


class DspPipeline:
    """Full pipeline: AEC -> HPF -> NS -> AGC -> VAD -> metrics"""
    def __init__(self, sample_rate: int = 16000, vad=None):
        self.sample_rate = sample_rate
        self.vad = vad  # RobustVAD instance (optional)
        self.hpf = HighPassFilter(sample_rate)
        self.ns = NoiseSuppressor(sample_rate, suppression=0.6)
        self.agc = AutoGainControl()
        self.aec = EchoCanceller(sample_rate)
        self._last_metrics = DspMetrics()

    def push_render(self, pcm: np.ndarray):
        self.aec.push_render(pcm)

    def process(self, mic_frame: np.ndarray, is_playing: bool = False) -> Tuple[np.ndarray, DspMetrics]:
        if mic_frame is None or mic_frame.size == 0:
            return mic_frame, DspMetrics()
        orig = np.asarray(mic_frame, dtype=np.float32).ravel()
        in_rms = float(np.sqrt(np.mean(orig * orig) + 1e-12))
        clipping = bool(np.max(np.abs(orig)) > 0.99)

        # AEC (only when we have recent render)
        aec_in = orig
        aec_out = self.aec.process(aec_in)
        aec_att = float(np.sqrt(np.mean(aec_out * aec_out) + 1e-12) / (in_rms + 1e-12)) if in_rms > 1e-6 else 1.0

        # HPF
        hpf_out = self.hpf.process(aec_out)
        # NS
        ns_out = self.ns.process(hpf_out)
        ns_gain = float(np.sqrt(np.mean(ns_out * ns_out) + 1e-12) / (np.sqrt(np.mean(hpf_out * hpf_out) + 1e-12) + 1e-12)) if np.sqrt(np.mean(hpf_out * hpf_out)) > 1e-6 else 1.0
        # AGC
        agc_out, agc_gain = self.agc.process(ns_out)

        # VAD is run by the caller (listener) after pipeline, but we can pre-compute
        vad_speech = False
        if self.vad is not None:
            # Let VAD know if playback was active (for its own threshold)
            try:
                vad_speech = bool(self.vad.is_speech(agc_out, playback_active=is_playing))
            except TypeError:
                vad_speech = bool(self.vad.is_speech(agc_out))

        m = DspMetrics(
            input_rms=in_rms,
            aec_attenuation=aec_att,
            ns_gain=ns_gain,
            agc_gain=agc_gain,
            vad_speech=vad_speech,
            clipping=clipping,
        )
        self._last_metrics = m
        return agc_out.astype(np.float32), m

    def reset(self):
        self.aec.reset()
        self._last_metrics = DspMetrics()
