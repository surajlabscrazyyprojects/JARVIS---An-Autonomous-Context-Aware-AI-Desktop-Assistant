# Security Policy

## Reporting a Vulnerability
Please do not open a public issue with a real secret. Use a private maintainer/security contact configured for the published repository, and rotate the credential immediately. If no private contact is configured yet, report only that a vulnerability exists and do not include sensitive details.

## Secrets Handling
- All provider credentials are **only** via environment variables / `.env` (never committed).
- `.env` and runtime memory are gitignored; only `.env.example` (placeholder values) is public.
- Frontend (`hologram_environment.html`, `preload.js`, `src/`) never contains provider credentials. Hume, Groq, Fish, and other auth remain backend-side.
- Electron `WebContentsView` is isolated (`nodeIntegration:false, contextIsolation:true, sandbox:true, webSecurity:true`), no CSP bypass, no `X-Frame-Options` removal, no unsafe flags.

## Required Keys
- `GROQ_API_KEY` — Groq console (for chat)
- `HUME_API_KEY` — Hume Octave (for Hume TTS, if enabled)
- `FISH_API_KEY` or `FISH_AUDIO_API_KEY` — Fish Audio alternative TTS

Optional: `GEMINI_API_KEY` (`AIza...`), `ELEVENLABS_API_KEY`, `BRAINROT_JARVIS_VOICE_ID`.

Missing keys → startup logs `CONFIGURATION ERROR Missing: ...` and runs degraded/offline, not silent fake.

## Git History
This repository is initialized **without history** containing secrets. If you previously committed real keys, you **must rotate/revoke** them (`Groq dashboard → Regenerate`, `Fish Audio → Regenerate`, `Google Cloud → Regenerate`, `Nvidia → Regenerate`) and clean history (`git filter-repo` or `BFG`) before publishing. Do **not** just delete the file in a new commit.

## Personal Data
- `memory/`, `logs/`, `.jarvis_browser_profile/`, `.venv/`, `node_modules/`, and generated runtime/cache files are gitignored.
- No `C:\Users\...` absolute paths in tracked source; use `Path(__file__).parent` / `ROOT`.
- `nvidia's api keys/` is gitignored and sanitized to `YOUR_NVIDIA_API_KEY_HERE`.

## Third-Party
- `gods-eye-view-main/` retains its original `LICENSE` — do not remove attribution.
- `vendor/` retains notices.

## Safe Publication Checklist
- [ ] `git status` shows only intended files (no `.env`, no logs, no memory history)
- [ ] `grep -R "gsk_\|sk-fish\|AIza\|nvapi-" --exclude-dir=node_modules --exclude-dir=.venv` shows no real values (only `YOUR_...` placeholders and env references)
- [ ] `npm install && npm run build` (if applicable) passes
- [ ] `python -m pytest` passes
- [ ] `npm start` (Electron) loads HUD fullscreen, Spidey `WebContentsView` isolated, no duplicate window
