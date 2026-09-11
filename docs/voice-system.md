# J.A.R.V.I.S. Local Expressive Voice System (Orpheus provider / Kokoro engine)

A local, offline-first expressive TTS subsystem. The HUD POSTs to `http://127.0.0.1:8766/tts` (and `/stream`); this subsystem answers with real local audio. No Fish Audio, no cloud key, no external service. If the engine is unavailable the gateway returns a truthful `VOICE_DEGRADED` state.

## Architecture (spec §4)

```
Groq reply text
   -> SpeechPlanner (preprocess + segmentation + emotion)   voice/speech_planner.py
   -> EmotionDirector (performance: speed/pitch/energy)    voice/emotion.py
   -> TTS engine (kokoro, provider identity orpheus)       voice/kokoro_backend.py
   -> Streaming Audio Queue (chunk N plays while N+1 generates)
   -> AudioPlaybackManager (single sink, no overlap)        voice/audio_playback.py
   -> Speaker / HUD AudioContext                            voice/server.py
```

- Provider identity is `orpheus` (spec §44); the installed synthesis engine is `kokoro` (`hexgrad/Kokoro-82M`, voice `am_michael`, male young-adult American). The engine is loaded ONCE in a long-running process.
- `VoiceEngine` orchestrates the pipeline; `VoiceService` owns the worker + queue + playback + health states.

## Files

| File | Responsibility |
|------|----------------|
| `voice/config.py` | `VoiceConfig` (provider/engine/model/voice, env + JSON overrides) |
| `voice/log.py` | `[TTS]` logging + metrics |
| `voice/emotion.py` | 18 states, `EmotionDirector`, `EmotionState` (shared voice+character) |
| `voice/voice_profile.py` | `VoiceProfile`, `VoiceProfileManager` |
| `voice/preprocess.py` | speech-friendly cleaning + sentence segmentation |
| `voice/speech_planner.py` | `SpeechPlanner` (chunking, per-chunk emotion) |
| `voice/tts_backend.py` | `TTSBackend` interface, `TTSUnavailable/TTSError` |
| `voice/kokoro_backend.py` | Kokoro synthesis engine (KPipeline, streaming, pitch/pace) |
| `voice/orpheus_backend.py` | Orpheus provider front (truthful DEGRADED when not installed) |
| `voice/wav.py` | WAV encode/decode, concat, rms |
| `voice/speech_queue.py` | priority queue (CRITICAL/HIGH/NORMAL/LOW) |
| `voice/audio_playback.py` | `AudioPlaybackManager`, `PyAudioSink`, `BufferSink`, amplitude |
| `voice/engine.py` | `VoiceEngine` (VOICE_* states, warmup, speak/stream) |
| `voice/service.py` | `VoiceService` (health/warmup/speak/stream/stop/pause/resume/recover) |
| `voice/server.py` | HTTP gateway `127.0.0.1:8766` (`/tts`, `/stream`, `/health`, `/voices`, ...) |
| `start_voice.py` | standalone gateway launcher (localhost-only, warmup-verified) |

Historical: Fish Audio (`fish_speech_backend.py`, `lifecycle.py`, `sapi_backend.py`, `chatterbox_backend.py`, `laughter.py`, `audio_queue.py`) was removed from the active runtime. See git history.

## Installation

Model is `hexgrad/Kokoro-82M` (82M params, ~330MB, cached at `~/.cache/huggingface/hub/models--hexgrad--Kokoro-82M`). No separate installer is needed; first `warmup()` triggers the cached load (warmup verifies real synthesis). The Orpheus 3B model is not required on this CPU-only target; set `JARVIS_TTS_ENGINE=orpheus` and install `orpheus-tts` when a GPU target is available.

## Running

```powershell
python start_voice.py          # load model, warmup, serve 127.0.0.1:8766
python start_voice.py --check  # print health/config and exit
python start_voice.py --no-warmup  # serve without warmup (dev)
```

Start JARVIS normally (unchanged):

```powershell
python jarvis.py
```

If the engine is down, `/tts` returns 503 and `GET /health` shows `VOICE_DEGRADED`.

## Configuration

`config/voice.json` + `config/voice_state.json` + env vars (env wins).

| Env var | Default | Meaning |
|---------|---------|---------|
| `JARVIS_TTS_PROVIDER` | `orpheus` | provider identity |
| `JARVIS_TTS_ENGINE` | `kokoro` | synthesis engine (`kokoro` or `orpheus`) |
| `JARVIS_TTS_MODEL` | `hexgrad/Kokoro-82M` | HF repo id |
| `JARVIS_VOICE` | `am_michael` | voice id (kokoro: `am_*` male, `af_*` female) |
| `JARVIS_TTS_LANG` | `a` | kokoro lang code (`a`=American English) |
| `JARVIS_TTS_HOST` | `127.0.0.1` | gateway host (forced localhost) |
| `JARVIS_TTS_PORT` | `8766` | gateway port (HUD contract) |
| `JARVIS_EMOTION_MODE` | `auto` | `auto` or `manual` |
| `JARVIS_EMOTION_DEFAULT` | `neutral` | default emotion |
| `JARVIS_EMOTION_INTENSITY` | `0.75` | 0.0–1.0 |
| `JARVIS_TTS_STREAMING` | `true` | stream chunk N+1 while N plays |
| `JARVIS_TTS_PLAYBACK` | `hud` | `hud` \| `system` \| `both` |

## Troubleshooting

- `warmup failed` in `VOICE_DEGRADED`: model not cached or kokoro import missing.
- `503 from /tts`: engine degraded or empty text after preprocessing.
- Port collision on 8766: set `JARVIS_TTS_PORT`.
- Logs are prefixed `[TTS]`.

See `docs/emotion-system.md` for the voice/emotion distinction.
