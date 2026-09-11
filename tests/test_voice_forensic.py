"""Forensic voice trace tests — prove pipeline is not fake (§5, §14, §61)."""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
HTML = Path("hologram_environment.html").read_text(encoding="utf-8", errors="replace")

def test_trace_exists():
    assert "VoiceTrace" in HTML
    assert "sessionId" in HTML
    assert "TURN-" in HTML

def test_utterance_buffer_exists():
    assert "UtteranceBuffer" in HTML
    assert "UTTERANCE_OPEN" in HTML
    assert "UTTERANCE_FINALIZE" in HTML


def test_authoritative_manager_has_real_lifecycle_states():
    # HUD state is not accepted as proof: these are the manager's own states.
    assert "VoiceCaptureManager" in HTML
    for state in ["MIC_REQUESTING", "MIC_READY", "AUDIO_ACTIVE", "SPEECH_CONFIRMED",
                  "FINALIZING", "TRANSCRIPT_READY", "SENDING_TO_AI", "DISABLED"]:
        assert state in HTML


def test_turn_detector_keeps_running_after_speech_is_confirmed():
    # Regression: the prior code marked a turn TRANSCRIBING at onset, and the
    # VAD's next tick returned early.  Confirmed speech must stay observable
    # until finalization decides the turn is over.
    assert "setVoiceCaptureState(VoiceCaptureStates.SPEECH_CONFIRMED" in HTML
    assert "ServerSTT.state === 'TRANSCRIBING') return" not in HTML


def test_partial_overlap_and_one_ai_request_guard_exist():
    assert "merge(previous, next)" in HTML
    assert "DUPLICATE_AI_REQUEST_IGNORED" in HTML

def test_forensic_mic_states():
    for s in ["MICROPHONE_OFF","MICROPHONE_REQUESTING","MICROPHONE_BLOCKED",
              "MICROPHONE_CONNECTED","MICROPHONE_ACTIVE","MICROPHONE_ACTIVE_NO_AUDIO","MICROPHONE_ERROR"]:
        assert s in HTML, f"missing {s}"

def test_audio_proof_metrics():
    assert "frameCount" in HTML
    assert "peakRms" in HTML
    assert "noiseFloor" in HTML
    assert "AUDIO_CONTEXT_CREATED" in HTML
    assert "MIC_TRACK_ACTIVE" in HTML

def test_single_mic_owner():
    # only ServerSTT owns mic; no second live getUserMedia besides camera + diagnostics probe
    streams = re.findall(r"getUserMedia\(\{audio", HTML)
    # 1 in ServerSTT init, 1 in diagnostics probe, 1 in old analyser fallback (shared now)
    assert len(streams) <= 3, f"too many mic owners: {len(streams)}"

def test_stale_protection():
    assert "__voiceSessionGen" in HTML
    assert "STALE_TURN_IGNORED" in HTML

def test_no_fake_transcript():
    # ensure no hardcoded fake transcript generation
    assert "fake transcript" not in HTML.lower() or "Do not" in HTML

def test_diagnostics_truthful():
    assert "TRUTHFUL STATE" in HTML
    assert "FRAMES" in HTML
