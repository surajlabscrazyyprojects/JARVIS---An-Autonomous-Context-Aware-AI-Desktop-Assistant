# Voice Capture Manager

`VoiceCaptureManager` (the HUD-compatible `ServerSTT` object) is the single
authoritative owner of microphone capture. The HUD, meter, and diagnostics are
subscribers only; AI receives a final transcript only.

```
microphone -> browser AEC/noise suppression/AGC -> Web Audio capture
           -> measured RMS + adaptive VAD -> turn detector -> utterance WAV
           -> Groq STT (turbo, then v3) or local faster-whisper fallback
           -> TranscriptAssembler -> existing JARVIS command router -> TTS
```

## Ownership and lifecycle

The manager records track identity/settings, AudioContext state, frame count,
RMS, peak, noise floor, and audio activity before declaring audio usable. It
owns one `MediaStream`, one AudioContext, one audio graph, one VAD timer and
one pending final STT request. Device end and missing-frame events emit a
diagnostic and trigger controlled reacquisition.

The manager states are: `OFF`, `INITIALIZING`, `MIC_REQUESTING`, `MIC_READY`,
`AUDIO_ACTIVE`, `LISTENING`, `SPEECH_CANDIDATE`, `SPEECH_CONFIRMED`,
`TRANSCRIBING`, `WAITING_FOR_TURN_END`, `FINALIZING`, `TRANSCRIPT_READY`,
`SENDING_TO_AI`, `RECOVERING`, `ERROR`, and `DISABLED`.

Speech confirmation no longer means transcription has started: VAD continues
observing the open utterance until the adaptive turn detector finalizes it.
That prevents the former failure where the next VAD tick returned early and a
natural turn could remain open indefinitely.

## STT configuration

`JARVIS_STT_PROVIDER=auto` (default) uses Groq when `GROQ_API_KEY` is present:
`whisper-large-v3-turbo`, with `whisper-large-v3` as a compatible retry. If
Groq is unavailable, local `faster-whisper` (`JARVIS_LOCAL_STT_MODEL=base` by
default) is the offline fallback. Set `JARVIS_STT_PROVIDER=groq` to fail
truthfully instead of using the local fallback.

Partials are real STT responses from bounded rolling audio. The transcript
assembler removes overlapping words. Final results carry session, turn, and
request IDs; duplicate final replies and duplicate AI sends are rejected.

## Verification status

Automated verification covers syntax, state presence, the VAD lifecycle
regression, transcript overlap guard, single AI-send guard, listener stress,
and existing streaming/acceptance behavior. Real microphone, whisper,
far-field, noise, echo, interruption, provider validation, and latency tests
must be performed in a launched Electron session with physical audio hardware;
they are deliberately not recorded as passed by unit tests.
