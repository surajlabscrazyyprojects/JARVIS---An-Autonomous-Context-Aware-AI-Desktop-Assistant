"""
Headless stress test for the self-healing J.A.R.V.I.S. voice listener.

It drives the REAL listener loop with SIMULATED audio (no microphone/speaker needed) and
injects every failure class the spec calls out:

  * silence / listen timeouts
  * short + long commands
  * unintelligible speech (empty transcript)
  * microphone read failure
  * microphone device disconnect + reconnect
  * STT failure
  * TTS failure
  * barge-in (user speaks while JARVIS is speaking)
  * explicit STOP command

It asserts the loop NEVER dies, returns to LISTENING after every case, never spawns
duplicate workers, never lets the playback queue grow, and terminates cleanly on STOP.
"""
from __future__ import annotations

import threading
import time

from jarvis.voice.listener import VoiceListener, ListenerState
from jarvis.voice.playback import AudioPlaybackManager
from jarvis.voice.sim import SimMicSource, ScriptedSTT, BeepTTS


def _count_threads(name: str) -> int:
    return sum(1 for t in threading.enumerate() if t.name == name)


def test_voice_listener_stress_50_conversations():
    # Disable the auto scheduler; we drive speech manually.
    mic = SimMicSource(script=["seed"], sample_rate=16000, schedule_interval=99999)
    stt = ScriptedSTT(mic)
    tts = BeepTTS(duration=0.25)
    playback = AudioPlaybackManager(sample_rate=16000, play_fn=None)

    transitions = []
    max_queue = 0

    def status_cb(state, text):
        transitions.append(state)
        q = playback.queue_size()
        nonlocal max_queue
        if q > max_queue:
            max_queue = q

    listener = VoiceListener(
        mic=mic, stt=stt, tts=tts, playback=playback,
        on_utterance=lambda text: f"Reply to: {text}",
        status_cb=status_cb,
        listen_timeout=1.0, silence_timeout=0.35, max_phrase=6.0,
        transcribe_timeout=5.0, think_timeout=5.0, speak_timeout=8.0,
        recover_timeout=4.0,
    )

    # ---- build a 50-turn plan with faults interleaved ----
    plan = []
    for k in range(50):
        if k == 7:
            plan.append(("FAULT_MIC",))
        elif k == 13:
            plan.append(("FAULT_STT",))
        elif k == 20:
            plan.append(("FAULT_TTS",))
        elif k == 26:
            plan.append(("UNINTELL",))
        elif k == 33:
            plan.append(("BARGE",))
        elif k == 44:
            plan.append(("DISCONNECT",))
        else:
            plan.append(("say", f"command number {k} " + ("x" * (3 if k % 2 else 60))))
    plan.append(("STOP",))

    fed_index = 0
    last_feed = 0.0
    barge_pending = False
    reconnect_at = 0.0
    stop_time = time.time() + 150.0

    def apply_action(action):
        nonlocal barge_pending, reconnect_at
        kind = action[0]
        if kind == "say":
            mic.current_phrase = action[1]
            mic.trigger_speech(action[1])
        elif kind == "FAULT_MIC":
            mic.fail_next_read = True
            mic.current_phrase = "mic fault test"
            mic.trigger_speech("mic fault test")
        elif kind == "FAULT_STT":
            stt.fail_next = True
            mic.current_phrase = "stt fault test"
            mic.trigger_speech("stt fault test")
        elif kind == "FAULT_TTS":
            tts.fail_next = True
            mic.current_phrase = "tts fault test"
            mic.trigger_speech("tts fault test")
        elif kind == "UNINTELL":
            mic.current_phrase = ""
            mic.trigger_speech("")
        elif kind == "BARGE":
            barge_pending = True
            mic.current_phrase = "normal sentence please"
            mic.trigger_speech("normal sentence please")
        elif kind == "DISCONNECT":
            mic.drop_device = True
            mic._dropped_at = time.time()  # sim mic auto-reconnects after 2s
            mic.current_phrase = "device will drop"
            mic.trigger_speech("device will drop")
        elif kind == "STOP":
            mic.current_phrase = "stop jarvis"
            mic.trigger_speech("stop jarvis")

    def controller():
        nonlocal fed_index, last_feed, barge_pending, reconnect_at
        while time.time() < stop_time and listener.state != ListenerState.STOPPED:
            # barge-in trigger
            if barge_pending and listener.state == ListenerState.SPEAKING:
                mic.trigger_speech("jarvis interrupt now")
                barge_pending = False
            # feed next action only when the device is actually usable, so a
            # STOP command is never "consumed" while the mic is disconnected.
            if (fed_index < len(plan) and listener.state == ListenerState.LISTENING
                    and not mic._speaking and not mic.drop_device
                    and (time.time() - last_feed) > 0.4):
                apply_action(plan[fed_index])
                fed_index += 1
                last_feed = time.time()
            time.sleep(0.02)

    listener.start()
    ctrl = threading.Thread(target=controller, name="test-controller", daemon=True)
    ctrl.start()

    # Wait until STOP consumed or timeout.
    while time.time() < stop_time and listener.state != ListenerState.STOPPED:
        time.sleep(0.1)

    # ---- assertions ----
    # 1) It actually terminated only via the explicit STOP command.
    assert listener.state == ListenerState.STOPPED, f"state={listener.state}"
    # 2) Every planned turn was consumed (loop never silently stopped feeding).
    assert fed_index == len(plan), f"fed {fed_index}/{len(plan)}"
    # 3) It kept returning to LISTENING throughout (no stuck state).
    assert transitions.count(ListenerState.LISTENING) >= 50, (
        f"only {transitions.count(ListenerState.LISTENING)} LISTENING transitions"
    )
    # 4) Faults triggered recovery (proving the recovery paths executed).
    assert listener.recoveries > 0, "no recoveries recorded"
    # 5) No duplicate worker threads (==1 while running, or 0 after a clean STOP).
    assert _count_threads("jarvis-listener") <= 1
    assert _count_threads("jarvis-watchdog") <= 1
    # 6) Playback queue never grew unbounded.
    assert max_queue <= 2, f"max playback queue size was {max_queue}"

    listener.stop()
    listener.join(timeout=3.0)
    print(f"\nSTRESS OK: conversations={listener.conversations} "
          f"recoveries={listener.recoveries} max_queue={max_queue}")
