# Voice pipeline audit

## Authoritative runtime path

The active browser path is now one pipeline:

`VoiceSessionManager (setVoiceSession) -> ServerSTT microphone stream -> AudioContext/ScriptProcessor -> adaptive VAD/turn detector -> 16 kHz mono WAV -> WebSocket stt_audio -> faster-whisper -> stt_result -> submitToJarvis -> WebSocket command -> backend agent/model -> conversation response -> TTS/playback`.

The browser owns one `MediaStream`. Diagnostics and the HUD analyser reuse its analyser; they do not call `getUserMedia` themselves. Each finalized request carries `session_id`, `turn_id`, and `req_id`.

## Inventory

| Component | Location | Classification | Notes |
| --- | --- | --- | --- |
| ServerSTT | `hologram_environment.html` | ACTIVE / authoritative | Owns the microphone, audio graph, frame capture, VAD, partials, finalization, and recovery. |
| `UtteranceBuffer` | `hologram_environment.html` | ACTIVE | One buffer per turn; final text is sent once after finalization. |
| `VoiceTrace` | `hologram_environment.html` | ACTIVE | Records session, turn, audio, STT, serialization, and send stages. |
| faster-whisper | `jarvis.py` | ACTIVE | Final model is `JARVIS_STT_MODEL` (default `base`); partial model is `JARVIS_STT_PARTIAL_MODEL` (default `tiny`). |
| `stt_audio` WebSocket contract | `hologram_environment.html` / `jarvis.py` | ACTIVE | Includes duplicate-request cache, trace IDs, size limits, timeout, and one retry. |
| Web Speech recognizer | `hologram_environment.html` | QUARANTINED / DEAD | The function returns before constructing `SpeechRecognition`; it is retained only as migration reference and cannot become a second owner. |
| Mic analyser fallback | `hologram_environment.html` | INACTIVE fallback | The authoritative ServerSTT stream is shared first; a second capture is not opened when ServerSTT is available. |
| Fish/local TTS | `voice/` | SECONDARY | Runs after text response; TTS failures do not own or restart the microphone. |

## Readiness and forensic evidence

The microphone is not reported ready when permission merely resolves. Startup now waits for:

- a live, enabled audio track;
- a running AudioContext;
- at least three observed ScriptProcessor audio frames.

If frames do not arrive, the state is `ACTIVE_NO_AUDIO` and diagnostics report `MIC ACTIVE / NO AUDIO`. Once energy changes above the calibrated floor, the trace emits `AUDIO_ACTIVITY_DETECTED`. Device settings, track state, sample rate, channel count, AEC, noise suppression, and AGC are exposed through `window.__voiceDebug`.

## Provider and transport

- Capture: browser `getUserMedia`, one mono audio track.
- Processing: Web Audio `AnalyserNode` plus `ScriptProcessorNode` sink required for frame callbacks.
- Turn detection: adaptive noise-floor calibration, sustained onset, minimum voiced duration, trailing-off patience, 60-second cap.
- STT transport: JSON WebSocket message containing a base64 16 kHz mono WAV.
- STT endpoint: local JARVIS WebSocket `stt_audio`; server transcribes with faster-whisper.
- AI handoff: final transcript is normalized only for whitespace, then serialized unchanged as the command text.

## Current evidence boundary

Automated targeted tests pass for TaskOS, context, integration, voice forensic hooks, and the TTS compatibility path. A real microphone/audio-activity/long-session result is not marked PASS here because the Windows UI automation helper was unavailable and no physical speech signal was observed in this run. The first live acceptance test remains: start JARVIS, inspect `window.__voiceDebug`, speak “Hello.”, and verify the trace sequence through `AI_RESPONSE_SENT`.
