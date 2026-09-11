"""Clean-process real Kokoro E2E (subprocess by test_voice_service)."""
import io
import os
import sys
import time
import wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice import VoiceConfig, VoiceService, BufferSink, EMOTIONS  # noqa: E402


def main():
    sink = BufferSink()
    sink.sim_dur = 0.08
    cfg = VoiceConfig.load()
    cfg.voice = "am_michael"
    cfg.streaming = True
    svc = VoiceService(cfg, sink=sink)  # real kokoro engine
    ok, detail = svc.warmup()
    assert ok, detail
    assert svc.health()["state"] == "VOICE_READY"

    for n in range(20):
        svc.speak("Line %d: all systems nominal." % n)
    for emo in EMOTIONS:
        svc.speak("Testing %s delivery." % emo, emotion=emo)
    t0 = time.time()
    while len(sink.played) < 20 + len(EMOTIONS) and time.time() - t0 < 120:
        time.sleep(0.05)
    assert len(sink.played) >= 20 + len(EMOTIONS), "played %d" % len(sink.played)
    assert svc.metrics.count >= 20 + len(EMOTIONS)

    # streaming: one long reply with chunks
    wav = svc.engine.speak("Hello, this is JARVIS. I have opened the browser. Wait... seriously?")
    with io.BytesIO(wav) as b:
        with wave.open(b, "rb") as w:
            assert w.getframerate() == 24000

    # barge-in (sim_dur long enough for real kokoro generation to interrupt)
    sink2 = BufferSink(); sink2.sim_dur = 2.0
    svc2 = VoiceService(cfg, sink=sink2)
    svc2.warmup()
    results = {}
    svc2.speak("A long low message that will be interrupted.", on_done=lambda ab: results.setdefault("A", ab))
    t0 = time.time()
    while time.time()-t0 < 10 and not sink2.is_playing():
        time.sleep(0.02)
    svc2.speak("High priority barge-in.", priority="high", on_done=lambda ab: results.setdefault("B", ab))
    t0 = time.time()
    while time.time()-t0 < 30 and "B" not in results:
        time.sleep(0.02)
    assert results.get("A") is True
    assert results.get("B") is False
    svc2.shutdown()
    svc.shutdown()
    print("REAL_KOKORO_OK")


if __name__ == "__main__":
    main()
