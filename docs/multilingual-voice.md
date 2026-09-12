# Multilingual voice behavior

The microphone/VAD and turn assembler remain unchanged. Final STT now uses
automatic language detection (`language=None` for faster-whisper and no forced
language for Groq), while the fast live model still supplies interim words.

Each final turn carries language, script, direction, confidence, and a
code-switch signal. The backend keeps current-turn language separate from the
temporary conversation language and does not persist a preference merely
because one turn used Hindi or another language.

| Language | Recognition policy | Native-script display | TTS status |
|---|---|---:|---|
| English | automatic Whisper/Groq detection | tested by existing English path | configured Hume voice |
| Hindi | automatic detection; Devanagari preserved | supported by Unicode path | requires live Hume pronunciation test |
| Hinglish | mixed-script/code-switch metadata | preserved without translation | requires live mixed-language test |
| Bhojpuri | no false dedicated-model claim; provider result is retained | preserved when returned by STT | requires live Hume/provider test |

No language is marked “perfect” or “fully supported” without real microphone,
transcript, response, and TTS validation. Bhojpuri is never silently relabeled
as Hindi by the local policy layer.
