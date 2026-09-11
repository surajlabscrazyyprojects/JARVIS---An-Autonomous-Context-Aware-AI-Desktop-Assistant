# J.A.R.V.I.S. — Holographic Environment

An Iron Man-inspired conversational AI with a holographic HUD, voice cloning, multi-character system, and desktop automation — now running as a **secure Electron desktop app** with embedded `WebContentsView` for external intelligence.

> **Security:** Credentials and runtime memory are local-only. Review `SECURITY.md` and `.env.example` before publishing or running the assistant.

## Features
- **Holographic HUD** (`hologram_environment.html` + Three.js + MediaPipe Hands)
- **Voice:** Backend-only Hume Octave or Fish/ElevenLabs/local engines; continuous STT with wake words
- **Characters:** IRON_MAN, SPIDER_MAN, THOR, THANOS — voice, model, personality switching
- **Spidey Tracker:** `https://spideytracker.net/intl/in/` embedded via **Electron `WebContentsView`** (not iframe) — respects `X-Frame-Options/CSP`, isolated (`nodeIntegration:false`, `contextIsolation:true`), single view, bounds-matched to ` #spidey-tracker-overlay` / ` #spidey-tracker-panel`
- **God's Eye:** optional local `gods-eye-view/` checkout (third-party Cesium/Leaflet globe; kept out of this first release until its dependency/license packaging is reviewed)
- **Automation:** `agent.py` + `jarvis.py` (WebSocket `8765`, HTTP `8767-8780`) — browser, computer, file, shell tools
- **Memory, Reminders, Routine, Diagnostics, Camera/Tracking**

## Quick Start (New User)

```bash
git clone <your-fork-url>
cd iron-man-with_no_rig

# Python backend (Windows, Python 3.12)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Node / Electron (requires Node 18+)
npm install

# Configure secrets
cp .env.example .env
# Edit .env and set:
#   GROQ_API_KEY=gsk_...
#   GEMINI_API_KEY=...        # optional
#   HUME_API_KEY=...           # recommended Hume Octave backend
#   HUME_SECRET_KEY=...        # if required by your Hume account
#   HUME_VOICE_ID=...          # optional; a default is provided
#   FISH_API_KEY=...           # optional alternative
#   ELEVENLABS_API_KEY=...    # optional

# Run (Electron, preferred)
npm start
# or double-click: jarvis.bat  /  JARVIS_START.bat

# Browser fallback (Spidey will show LINK BLOCKED — Electron required for embed)
# python jarvis.py
```

Open `http://127.0.0.1:8767/hologram_environment.html` if launched via `jarvis.py`.

## Configuration

All secrets **only** via environment / `.env`. Never hardcode.

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | yes (for chat) | Groq `gsk_...` https://console.groq.com/keys |
| `GEMINI_API_KEY` | no | Gemini `AIza...` alternative |
| `JARVIS_CONVERSATION_PROVIDER` | no | `groq` (default) or `gemini` |
| `JARVIS_CONVERSATION_MODEL` | no | e.g. `openai/gpt-oss-120b` |
| `HUME_API_KEY` | optional | Hume Octave server-side TTS key |
| `HUME_SECRET_KEY` | optional | Hume account secret; never expose client-side |
| `HUME_VOICE_ID` / `HUME_VOICE_PROVIDER` | no | Hume voice selection (`HUME_AI` for Hume voices) |
| `FISH_API_KEY` / `FISH_AUDIO_API_KEY` | optional | Fish Audio alternative TTS |
| `ELEVENLABS_API_KEY` | no | ElevenLabs optional |
| `BRAINROT_JARVIS_VOICE_ID` | no | ElevenLabs voice ID |
| `VOICE_*` | no | Local Chatterbox-Nano overrides (see `.env.example`) |

Missing required keys → startup logs `CONFIGURATION ERROR Missing: GROQ_API_KEY` (or `FISH_AUDIO_API_KEY`) and runs in degraded/offline mode, not silent fake credentials.

## Project Structure

```
iron-man-with_no_rig/
├── hologram_environment.html  # HUD (ES modules, no secrets)
├── electron_main.js           # Electron WebContentsView (single view, isolated)
├── preload.js                 # contextBridge only
├── jarvis.py                  # HTTP + WebSocket backend, env-only secrets
├── agent.py                   # Computer-use agent
├── voice/                     # Hume, local, Fish/ElevenLabs backends (env-only)
├── src/character/             # Multi-character system
├── gods-eye-view/             # Optional local third-party checkout (ignored)
├── memory/                    # Private runtime history (gitignored)
├── nvidia's api keys/         # Ignored (placeholder only)
├── .env.example               # Safe template (no values)
└── .gitignore                 # Secrets, logs, caches, browser profile ignored
```

## Security Notes

- **Never commit `.env`** — it is `gitignored`. Only `.env.example` (empty values) is public.
- **No frontend secrets** — `hologram_environment.html` / `preload.js` never contain `GROQ_API_KEY`, `FISH_API_KEY`, etc. All provider auth stays in `jarvis.py` / `voice/` backend.
- **No CSP bypass** — Electron does **not** disable `webSecurity`, does not inject scripts to remove `X-Frame-Options`, does not use unsafe flags. `WebContentsView` loads `spideytracker.net` as a real browser surface.
- **Isolation** — `nodeIntegration:false, contextIsolation:true, sandbox:true, webSecurity:true` for both main and Spidey view.
- **Personal paths** — Use `Path.home()` / project-relative `ROOT / "path"`; no hardcoded `C:\Users\...` in tracked source (helper scripts in parent `iron man/` are not part of publication).
- **History** — This repo has **no git history** (`git status` → not a git repo) — no historical secret exposure. If you had previously committed real keys, **rotate them** before pushing.

## Third-Party Attribution

- `gods-eye-view/` — optional local third-party checkout; retain its original `LICENSE` / attribution if distributed separately. Do not claim it as your own.
- `vendor/mediapipe/`, `vendor/three/` — vendored, keep notices.
- `HUD Sound Effects.mp3`, `JARVIS STARTUP SOUND.mp3`, `reminder sound.mp3`, `scene.gltf` etc. — required runtime assets, keep.

## Troubleshooting

- **Spidey shows `LINK BLOCKED` / `RETRY`** → you are in browser fallback (`python jarvis.py` + Chrome). Use Electron: `npm start` or `jarvis.bat` (requires `npm install`).
- **Two HUD windows** → kill stale `python.exe`/`electron.exe` (`taskkill /F /IM python.exe` / `taskkill /F /IM electron.exe`) then `npm start`.
- **Microphone/Camera blocked** → Electron auto-grants for `http://127.0.0.1:8767-8780`; Chrome fallback seeds `Preferences` for those origins.
- **WS `10048` bind error** → stale backend holds `8765`. Kill or wait for fallback `8766-8775` (HUD tries `8765-8770`; check `jarvis_crash.log`).

## License

`license.txt` records the required CC-BY-4.0 attribution for the included Iron Man model. A project-wide open-source license has not been selected; choose one before redistributing the complete repository. Do not remove third-party attribution.

## Security Disclosure

If you find a secret in history, **rotate it immediately** and open an issue without posting the value.
