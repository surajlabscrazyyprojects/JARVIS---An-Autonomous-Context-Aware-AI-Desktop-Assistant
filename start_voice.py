"""
Standalone launcher for J.A.R.V.I.S. Fish Audio voice gateway.

Provider: Fish Audio S2.1 Pro Free (https://api.fish.audio/v1/tts)
Single gateway on 127.0.0.1:8766 — starts instantly, warmup in background.

Usage:
    python start_voice.py            # start gateway, warmup in background
    python start_voice.py --check    # print health/config and exit
"""
from __future__ import annotations

import argparse
import signal
import sys
import threading
import time

from voice import VoiceConfig, VoiceService, start_tts_server
from voice.log import logger


def main():
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. local voice gateway (orpheus/kokoro)")
    parser.add_argument("--check", action="store_true", help="print health + config and exit")
    parser.add_argument("--host", default=None, help="override tts_host (must remain 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="override tts_port")
    parser.add_argument("--no-warmup", action="store_true", help="skip warmup synthesis")
    args = parser.parse_args()

    cfg = VoiceConfig.load()
    if args.host:
        cfg.tts_host = args.host
    if args.port:
        cfg.tts_port = args.port

    # Enforce localhost-only (spec Â§6, Â§46).
    if cfg.tts_host not in ("127.0.0.1", "localhost"):
        logger.warning(f"[TTS] tts_host {cfg.tts_host!r} forced to 127.0.0.1 (localhost-only)")
        cfg.tts_host = "127.0.0.1"

    service = VoiceService(cfg)

    if args.check:
        import json
        print(json.dumps(service.health(), indent=2))
        print("CONFIG:")
        print(json.dumps(cfg.public(), indent=2))
        service.shutdown()
        return

    # Start gateway immediately — warmup runs in background so HUD can connect fast
    server = start_tts_server(cfg, service=service)
    h0 = service.health()
    logger.info(f"[TTS] gateway listening on http://{cfg.tts_host}:{cfg.tts_port}/tts (provider={cfg.provider} engine={h0.get('engine')} voice={cfg.voice[:8]}... state={h0.get('state')})")

    if not args.no_warmup:
        def _bg_warmup():
            logger.info("[TTS] warmup_started (background)")
            t0 = time.time()
            ok, detail = service.warmup()
            logger.info(f"[TTS] warmup_verified ok={ok} detail={detail} in {time.time()-t0:.2f}s state={service.state}")
            if not ok:
                logger.warning(f"[TTS] warmup did not reach READY: {detail}")
        threading.Thread(target=_bg_warmup, daemon=True).start()
    else:
        logger.info("[TTS] warmup skipped (--no-warmup)")
    logger.info(f"[TTS] voice_service_started provider={cfg.provider} engine={h0.get('engine')} "
                f"voice={cfg.voice} state={h0.get('state')} (warmup background)")

    def _shutdown(*_):
        logger.info("[TTS] shutting down voice gateway")
        try:
            server.shutdown()
        except Exception:
            pass
        service.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()

