"""Fish Audio real-time TTS over WebSocket (verified against official AsyncAPI).

Endpoint: wss://api.fish.audio/v1/tts/live
Auth:     Authorization: Bearer <key>  +  model: <name> headers.
Frames (MessagePack):
  -> {event: "start", request: {text: "", reference_id, format, ...}}
  -> {event: "text", text: <chunk>} ... [{event: "flush"}]
  -> {event: "stop"}
  <- {event: "audio", audio: <bytes>} ... <- {event: "finish", reason}

Only ``s2.1-pro-free`` is sent by default; paid models require an explicit
opt-in and are otherwise blocked BEFORE any request (fail-closed — the server
falls back to paid s2.1-pro for omitted/unrecognized models, so we never send
such a request).

Runs on the ``websockets`` sync client in the caller's worker thread with
connect + first-audio timeouts, cooperative cancel, and no retries once audio
has started (a retry would double-bill and double-speak).
"""
from __future__ import annotations

import threading
import time
from typing import Iterator, Optional

from .fish_config import FREE_MODEL, FishConfig, FishConfigError


# ---- typed error taxonomy (§5) -------------------------------------------
class FishError(Exception):
    pass


class MissingApiKey(FishError):
    pass


class MissingReferenceId(FishError):
    pass


class InvalidConfiguration(FishError):
    pass


class AuthenticationFailed(FishError):
    pass


class FreeModelUnavailable(FishError):
    pass


class PaidModelBlocked(FishError):
    pass


class RateLimited(FishError):
    pass


class FishServiceUnavailable(FishError):
    pass


class FishTimeout(FishError):
    pass


class FishProtocolError(FishError):
    pass


class UserInterrupted(FishError):
    pass


LIVE_URL = "wss://api.fish.audio/v1/tts/live"


def _need_msgpack():
    try:
        import msgpack
        return msgpack
    except Exception as exc:  # noqa: BLE001
        raise FishProtocolError(f"msgpack is required for Fish live streaming: {exc}")


def build_start_request(cfg: FishConfig, reference_id: str, speed: float = 1.0,
                        volume_db: float = 0.0) -> dict:
    """Build the validated start-event request payload (no key inside)."""
    cfg.validate()
    if cfg.model != FREE_MODEL and not cfg.allow_paid_models:
        raise PaidModelBlocked(f"paid model {cfg.model!r} blocked (fail-closed)")
    return {
        "text": "",
        "reference_id": reference_id,
        "format": "pcm",
        "sample_rate": 24000,
        "chunk_length": int(cfg.chunk_length),
        "min_chunk_length": int(cfg.min_chunk_length),
        "normalize": bool(cfg.normalize),
        "condition_on_previous_chunks": bool(cfg.condition_on_previous_chunks),
        "temperature": float(cfg.temperature),
        "top_p": float(cfg.top_p),
        "repetition_penalty": float(cfg.repetition_penalty),
        "latency": cfg.latency,
        "prosody": {
            "speed": max(0.5, min(2.0, float(speed))),
            "volume": max(-20.0, min(20.0, float(volume_db))),
            "normalize_loudness": True,
        },
    }


class FishLiveSession:
    """One logical TTS stream (one assistant reply). Not thread-safe for
    concurrent text feeds — feed from a single producer thread."""

    def __init__(self, cfg: FishConfig, reference_id: str, speed: float = 1.0,
                 volume_db: float = 0.0, cancel: Optional[threading.Event] = None):
        if not (cfg.api_key or "").strip():
            raise MissingApiKey("FISH_API_KEY missing")
        if not (reference_id or "").strip():
            raise MissingReferenceId("voice reference_id missing")
        # Paid-block BEFORE full validation so the failure mode is explicit.
        _model = (cfg.model or "").strip()
        if _model and _model != FREE_MODEL and not cfg.allow_paid_models:
            raise PaidModelBlocked(
                f"paid model {_model!r} blocked (fail-closed) — use '{FREE_MODEL}'")
        self.cfg = cfg.validate()
        self.reference_id = reference_id
        self.speed = speed
        self.volume_db = volume_db
        self.cancel = cancel or threading.Event()
        self.t_connect_ms: Optional[int] = None
        self.t_first_audio_ms: Optional[int] = None
        self.audio_started = False
        self._ws = None

    def _connect(self):
        from websockets.sync.client import connect
        msgpack = _need_msgpack()
        t0 = time.time()
        try:
            self._ws = connect(
                self.cfg.ws_url or LIVE_URL,
                additional_headers={
                    "Authorization": f"Bearer {self.cfg.api_key}",
                    "model": self.cfg.model,
                },
                open_timeout=self.cfg.connect_timeout_ms / 1000.0,
                max_size=8 * 1024 * 1024,
            )
        except TimeoutError as exc:
            raise FishTimeout(f"live connect timeout: {exc}")
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "401" in msg or "unauthorized" in msg.lower():
                raise AuthenticationFailed(f"live auth failed: {msg[:120]}")
            raise FishServiceUnavailable(f"live connect failed: {msg[:160]}")
        self.t_connect_ms = int((time.time() - t0) * 1000)
        start = {"event": "start",
                 "request": build_start_request(self.cfg, self.reference_id,
                                                self.speed, self.volume_db)}
        try:
            self._ws.send(msgpack.packb(start))
        except Exception as exc:  # noqa: BLE001
            self._close_quiet()
            raise FishProtocolError(f"live start failed: {exc}")

    def _close_quiet(self):
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:  # noqa: BLE001
            pass
        self._ws = None

    def synthesize(self, text_chunks: Iterator[str]) -> Iterator[bytes]:
        """Feed text chunks, yield raw PCM audio fragments as they arrive."""
        import msgpack
        _need_msgpack()
        self._connect()
        assert self._ws is not None
        t0 = time.time()
        first_audio_at: Optional[float] = None
        started_audio = False
        try:
            for piece in text_chunks:
                if self.cancel.is_set():
                    raise UserInterrupted("cancelled before/during synthesis")
                if piece:
                    try:
                        self._ws.send(msgpack.packb({"event": "text", "text": piece}))
                    except Exception as exc:  # noqa: BLE001
                        raise FishProtocolError(f"live text send failed: {exc}")
                # Drain any audio already available without blocking the feed.
                for blob in self._drain_available(first_audio_at, t0):
                    if first_audio_at is None:
                        first_audio_at = time.time()
                        self.t_first_audio_ms = int((first_audio_at - t0) * 1000)
                    started_audio = True
                    yield blob
            # Flush + stop, then drain the remainder.
            try:
                self._ws.send(msgpack.packb({"event": "flush"}))
            except Exception:  # noqa: BLE001
                pass
            try:
                self._ws.send(msgpack.packb({"event": "stop"}))
            except Exception:  # noqa: BLE001
                pass
            while True:
                if self.cancel.is_set():
                    raise UserInterrupted("cancelled during drain")
                try:
                    raw = self._ws.recv(timeout=2.0)
                except TimeoutError:
                    continue
                except Exception as exc:  # noqa: BLE001
                    raise FishProtocolError(f"live drain failed: {exc}")
                kind, payload = self._parse(raw)
                if kind == "audio":
                    if first_audio_at is None:
                        first_audio_at = time.time()
                        self.t_first_audio_ms = int((first_audio_at - t0) * 1000)
                    started_audio = True
                    yield payload
                elif kind == "finish":
                    if payload != "stop":
                        raise FishProtocolError(f"live finish reason={payload!r}")
                    return
                if time.time() - t0 > self.cfg.tts_timeout_ms / 1000.0:
                    raise FishTimeout("live session exceeded tts timeout")
        finally:
            self.audio_started = started_audio
            self._close_quiet()

    def _drain_available(self, first_audio_at, t0):
        """Non-blocking drain used between text feeds."""
        assert self._ws is not None
        import msgpack  # noqa: F401
        while True:
            try:
                raw = self._ws.recv(timeout=0.01)
            except TimeoutError:
                return
            except Exception as exc:  # noqa: BLE001
                raise FishProtocolError(f"live recv failed: {exc}")
            kind, payload = self._parse(raw)
            if kind == "audio":
                yield payload
            elif kind == "finish":
                if payload != "stop":
                    raise FishProtocolError(f"live finish reason={payload!r}")
                return
            if time.time() - t0 > self.cfg.tts_timeout_ms / 1000.0:
                raise FishTimeout("live session exceeded tts timeout")

    @staticmethod
    def _parse(raw) -> tuple:
        import msgpack
        try:
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            msg = msgpack.unpackb(raw, raw=False)
        except Exception as exc:  # noqa: BLE001
            raise FishProtocolError(f"live frame decode failed: {exc}")
        ev = msg.get("event")
        if ev == "audio":
            data = msg.get("audio")
            if not isinstance(data, (bytes, bytearray)) or not data:
                raise FishProtocolError("live audio frame empty")
            return "audio", bytes(data)
        if ev == "finish":
            return "finish", msg.get("reason")
        raise FishProtocolError(f"live unexpected event={ev!r}")
