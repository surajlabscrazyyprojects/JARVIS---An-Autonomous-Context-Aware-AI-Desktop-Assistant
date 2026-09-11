#!/usr/bin/env python3
"""Voice diagnostics for my laptop (Ryzen 5 / 16GB, no GPU required).
Run:  python scripts/voice_diag.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voice.config import VoiceConfig

def main():
    cfg = VoiceConfig.load()
    print(f"provider={cfg.provider} engine={cfg.engine} model={cfg.model}")
    print(f"fish_model={cfg.fish_model} latency={cfg.fish_latency} "
          f"format={cfg.fish_format} sr={cfg.fish_port if False else 24000}")
    print(f"gateway={cfg.tts_host}:{cfg.tts_port} streaming={cfg.streaming}")
    # Redacted key
    print(f"fish_key={cfg.fish_api_key_preview()} ref={cfg.voice[:8]}... "
          f"configured={cfg.has_fish_key()} private_cache={os.environ.get('FISH_ALLOW_PRIVATE_RESPONSE_CACHE','false')}")
    try:
        import psutil
        print(f"ram={psutil.virtual_memory().percent}% cpu={psutil.cpu_percent(interval=0.2)}%")
    except Exception:
        print("ram/cpu: psutil unavailable")
    # Health
    from voice.engine import VoiceEngine
    try:
        eng = VoiceEngine(cfg)
        h = eng.health()
        print(f"health: status={h['status']} available={h['available']} detail={h['detail'][:80]}")
        print(f"queue: n/a  state={h['status']} fallback={'no' if h['available'] else 'yes'}")
    except Exception as e:
        print(f"health probe failed: {e.__class__.__name__}: {e}")

if __name__ == "__main__":
    main()
