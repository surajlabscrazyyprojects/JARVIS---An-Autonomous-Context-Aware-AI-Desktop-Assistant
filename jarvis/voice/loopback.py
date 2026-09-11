"""
WASAPI loopback reference capture for system audio (YouTube, Spotify, etc.).

On Windows, WASAPI can capture the audio being rendered to the current output
device (loopback). This provides the AEC with a reference that contains not
only JARVIS TTS but also any other system playback, allowing suppression of
YouTube/music echo as well.

If loopback is unavailable (device does not support it, or sounddevice not
configured for WASAPI), this class gracefully degrades to TTS-only reference
(which still handles JARVIS self-voice).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger("jarvis.voice.loopback")

class LoopbackCapture:
    def __init__(self, sample_rate: int = 16000, on_frame: Optional[Callable[[np.ndarray], None]] = None):
        self.sample_rate = sample_rate
        self.on_frame = on_frame
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._available = False

    def is_available(self) -> bool:
        # Check if sounddevice can open a WASAPI loopback stream
        try:
            import sounddevice as sd
            # Try to query loopback devices (Windows WASAPI)
            devs = sd.query_devices()
            for d in devs:
                name = str(d.get("name", "")).lower()
                host = str(d.get("hostapi", "")).lower()
                # Loopback devices often appear as "Speakers (loopback)" or similar with maxInputChannels >0 and is loopback
                if d.get("max_input_channels", 0) > 0 and ("loopback" in name or "wasapi" in host):
                    self._available = True
                    return True
            # Fallback: try to see if we can open a loopback stream at all
            # We don't actually open here, just report that sounddevice is present
            # so caller can attempt; if it fails, we degrade gracefully
            self._available = True
            return False  # No explicit loopback device found, but sounddevice present
        except Exception as e:
            logger.debug(f"[loopback] not available: {e}")
            return False

    def start(self):
        if self._running:
            return
        if not self.is_available():
            logger.info("[loopback] WASAPI loopback not found — using TTS-only reference (JARVIS self-voice will still be suppressed, YouTube suppression will be partial)")
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, name="jarvis-loopback", daemon=True)
        self._thread.start()
        logger.info("[loopback] started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _capture_loop(self):
        try:
            import sounddevice as sd
            # Try to open loopback stream
            # On Windows, loopback is an input stream from the output device
            # We attempt to open the default output device as loopback input
            # This is best-effort; if it fails, we just log and exit
            def callback(indata, frames, time_info, status):
                if status:
                    logger.debug(f"[loopback] status: {status}")
                if self.on_frame and indata is not None:
                    # indata is float32 [-1,1] shape (frames, channels)
                    mono = np.mean(indata, axis=1) if indata.ndim > 1 else indata.ravel()
                    # Resample if needed (assume loopback is 48k, we need 16k)
                    # Simple decimation: for now, just take every 3rd sample if 48k->16k
                    # A proper resampler would be better, but this is a fallback
                    if len(mono) > 320:  # Likely 48k (960 samples for 20ms) vs 16k (320)
                        mono = mono[::3][:320]
                    try:
                        self.on_frame(mono.astype(np.float32))
                    except Exception:
                        pass

            # Try WASAPI loopback
            try:
                # On Windows, the loopback device is often the default output device with wasapi loopback flag
                # sounddevice extra_settings can specify wasapi loopback
                # We try a generic input stream first
                with sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype='float32',
                    blocksize=320,
                    callback=callback
                ):
                    while self._running:
                        time.sleep(0.1)
            except Exception as e:
                logger.info(f"[loopback] WASAPI loopback stream failed (expected on some systems): {e}")
                # Fallback: try with explicit wasapi host
                try:
                    wasapi = sd.WasapiSettings(loopback=True)
                    with sd.InputStream(
                        samplerate=self.sample_rate,
                        channels=1,
                        dtype='float32',
                        blocksize=320,
                        callback=callback,
                        extra_settings=wasapi
                    ):
                        while self._running:
                            time.sleep(0.1)
                except Exception as e2:
                    logger.info(f"[loopback] fallback also failed: {e2}")
        except Exception as e:
            logger.warning(f"[loopback] capture loop error: {e}")

__all__ = ["LoopbackCapture"]
