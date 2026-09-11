# Voice Identity ≠ Emotion ≠ Character Personality

These three dimensions are deliberately independent in the J.A.R.V.I.S. voice
system. Confusing them is the most common way a TTS integration becomes a toy.

## 1. Voice Identity  (timbre / speaker)

Controlled by a **voice profile** (`voices/<id>/`). It determines *who is
speaking*: timbre, vocal identity, speaker characteristics.

- Examples: `jarvis`, `cartoon`, `energetic`.
- Selected via `/voice/set` or `engine.set_voice(...)`.
- Changing the voice **must not** change how the line is performed.

```python
engine.set_voice("cartoon")   # only swaps the speaker; emotion untouched
```

## 2. Emotion  (HOW the line is performed)

Controlled by the **EmotionDirector** (`voice/emotion.py`). It decides the
performance: excitement, happiness, curiosity, surprise, playfulness, seriousness,
concern, frustration, dramatic delivery, whispering, emphasis, pauses, energy.

- In `AUTO` mode it is inferred **deterministically** from the text (punctuation,
  lexical cues, intent) — no cloud LLM, no extra cost.
- In `manual` mode it is set explicitly via `/emotion/set`.
- Emitted as **sparse natural-language tags** for Fish Speech S2 Pro, e.g.
  `[excited] Wait, seriously?` or `[whisper] Okay... let's keep this quiet.`
- Tags influence performance; they are never spoken aloud.

```python
engine.set_emotion(emotion="curious", mode="manual")
# performance changes; voice identity and personality unchanged
```

### Critical property

```
VOICE = cartoon      does NOT reset   EMOTION = excited
VOICE = jarvis       works WITH       EMOTION = curious
EMOTION = serious    does NOT change  VOICE  = jarvis
```

The `SpeechPerformance` object is fully independent from `VoiceProfile`.

## 3. Character Personality  (who J.A.R.V.I.S. IS)

Controlled by `CharacterProfile` (`voice/emotion.py`). It is the consistent
personality baseline: energetic, playful, witty, curious, expressive, slightly
cheeky, youthful/cartoon-like, intelligent.

- Emotion modulates the *performance* of a line, but never rewrites the
  personality.
- Believable character comes from **contrast**, not constant hyperactivity:
  CALM → EXCITED, SERIOUS → PLAYFUL, CURIOUS → SURPRISED, NEUTRAL → DELIGHTED.
- The default profile biases energy/playfulness so the character feels alive
  while still allowing a calm line to sound calm.

```python
CharacterProfile(
    name="JARVIS",
    personality=["energetic","playful","witty","curious","expressive",
                 "spontaneous","engaging","slightly cheeky","youthful","intelligent"],
    humor_level=0.7, playfulness=0.75, energy_baseline=0.6,
    expressiveness=0.8, speech_style="conversational, crisp, a little cheeky",
)
```

## Supported emotions

`neutral, happy, excited, curious, surprised, playful, amused, confused,
serious, concerned, frustrated, dramatic, calm, whisper, celebratory`

Each has an intensity, pacing, energy, emphasis, pause behavior, pitch tendency
and a sparse NL tag — but these are *guidance*, not robotic DSP chains. The
director avoids over-tagging (e.g. low-intensity happy/curious get no tag).

## Why this matters

- A user can switch the **voice** (cartoon vs jarvis) without losing the
  assistant's **personality**.
- A user can force an **emotion** (excited) for a prank without changing the
  **voice**.
- The assistant still sounds like ONE character across millions of replies
  because the personality baseline is fixed while emotion provides contrast.
