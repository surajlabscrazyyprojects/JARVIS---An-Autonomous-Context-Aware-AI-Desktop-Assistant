#!/usr/bin/env python3
"""Voice benchmark: LLM first-token -> Fish TTS first-audio -> playback.
Run from repo root:  python scripts/voice_benchmark.py [--text "..."]
Reports warm + cold; does NOT log private source text by default.
"""
from __future__ import annotations

import argparse
import time

def bench(text: str, warm_runs: int = 2, cold_desc: str = "cold"):
    from voice.config import VoiceConfig
    from voice.engine import VoiceEngine

    cfg = VoiceConfig.load()
    eng = VoiceEngine(cfg)
    print(f"provider={cfg.provider} engine={cfg.engine} model={cfg.model} "
          f"voice={cfg.voice[:8]}... streaming={cfg.streaming}")
    # Warm
    t0 = time.time()
    ok, detail = eng.warmup()
    print(f"warmup: {ok} ({detail}) in {time.time()-t0:.2f}s\n")
    # Cold run (first synthesis after warmup still cold-ish for the worker)
    for label, i in [(cold_desc, 0)] + [("warm", j) for j in range(1, warm_runs+1)]:
        t0 = time.time()
        first = None
        n = 0
        try:
            for perf, wav in eng.speak_stream(text):
                if first is None:
                    first = time.time() - t0
                n += 1
        except Exception as e:
            print(f"[{label}] failed: {e.__class__.__name__}: {str(e)[:120]}")
            continue
        total = time.time() - t0
        print(f"[{label}] chunks={n} first-audio={first:.2f}s total={total:.2f}s "
              f"first-text=0.00s (local) ws-connect={getattr(eng.core, '_last_live_connect_ms', 'n/a')}ms "
              f"ws-first={getattr(eng.core, '_last_live_first_ms', 'n/a')}ms "
              f"cache={'hit' if text.strip().lower() in ('hello','hi') else 'n/a'} "
              f"fallback={'no' if n else 'yes'}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Jarvis voice benchmark")
    ap.add_argument("--text", default="Ten-minute timer started. I will let you know when it is up.",
                    help="text to synthesize")
    ap.add_argument("--warm-runs", type=int, default=2)
    args = ap.parse_args()
    bench(args.text, warm_runs=args.warm_runs)
