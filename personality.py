"""J.A.R.V.I.S. personality core — ONE authoritative module.

Owns, for every spoken reply:
  * tone estimation (communication style, not simulated feelings),
  * the personality system-prompt block given to the LLM,
  * speech formatting (markdown/JSON stripped, length matched to the
    request, facts preserved verbatim),
  * opener variety + "sir" discipline.

Design rules (from the voice-rebuild spec):
  - Natural > verbose. Never theatrical monologues.
  - "sir" at most once per reply, and not in every reply.
  - Never the same opener twice in a row.
  - Never claim to be human; never invent memories, feelings or actions.
  - Never alter factual content to sound emotional.
"""
from __future__ import annotations

import re
from collections import deque
from typing import Optional

# --------------------------------------------------------------------------
# Tone estimation (keyword cues from the user's request + task outcome)
# --------------------------------------------------------------------------

CALM = "calm"
NEUTRAL = "neutral"
FOCUSED = "focused"
CONFIDENT = "confident"
CURIOUS = "curious"
CONCERNED = "concerned"
EMPATHETIC = "empathetic"
APOLOGETIC = "apologetic"
SERIOUS = "serious"
PLAYFUL = "playful"
ENERGETIC = "energetic"

_FRUSTRATED = ("annoying", "stupid", "hate", "took forever", "too slow", "again?!",
               "not working", "doesn't work", "broken", "ugh", "seriously",
               "wrong", "not what i meant", "you failed", "failed", "damn")
_EXCITED = ("awesome", "amazing", "incredible", "fantastic", "love it", "perfect",
            "brilliant", "excellent", "wow", "nice!", "great job", "funny",
            "hilarious", "lol", "haha")
_SERIOUS = ("serious", "important", "urgent", "critical", "emergency", "deadline",
            "interview", "exam", "hospital", "doctor", "money", "payment",
            "password", "security", "delete", "format", "backup")
_SORRY_TRIGGERS = ("sorry", "apolog", "my fault", "my mistake", "i messed")
_PLAYFUL = ("joke", "funny", "boring", "entertain", "story", "interesting",
            "riddle", "game")


def estimate_tone(user_text: str, outcome: str = "ok") -> str:
    """Pick a communication tone. `outcome` is ok|fail|clarify."""
    t = (user_text or "").lower()
    if outcome == "fail":
        if any(k in t for k in _FRUSTRATED):
            return EMPATHETIC
        return APOLOGETIC
    if outcome == "clarify":
        return CURIOUS
    if any(k in t for k in _FRUSTRATED):
        return CONCERNED
    if any(k in t for k in _SORRY_TRIGGERS):
        return EMPATHETIC
    if any(k in t for k in _SERIOUS):
        return SERIOUS
    if any(k in t for k in _EXCITED):
        return ENERGETIC
    if any(k in t for k in _PLAYFUL):
        return PLAYFUL
    if "?" in t and len(t.split()) <= 8:
        return CURIOUS
    if re.search(r"\b(open|launch|start|close|type|search|create|set|remind)\b", t):
        return FOCUSED
    return NEUTRAL


_TONE_DIRECTION = {
    CALM: "Steady, unhurried delivery. Short sentences.",
    NEUTRAL: "Even, natural delivery.",
    FOCUSED: "Crisp and direct. Confirm the action, then report the result. No small talk.",
    CONFIDENT: "Assured delivery, subtle satisfaction. One concise sentence.",
    CURIOUS: "Engaged, slightly inquisitive delivery. Ask exactly one short question when clarification is needed.",
    CONCERNED: "Calmer, more measured delivery. Acknowledge the friction briefly, then focus on the fix.",
    EMPATHETIC: "Gentle, understanding delivery. Acknowledge why it is annoying in one clause, then solve it.",
    APOLOGETIC: "Direct acknowledgement of the failure, then the concrete next step. No grovelling.",
    SERIOUS: "Slower, respectful, precise delivery. No jokes.",
    PLAYFUL: "Light, dry delivery. One subtle witty remark at most, then the substance.",
    ENERGETIC: "Warmer, livelier delivery matching their energy, still concise.",
}

# --------------------------------------------------------------------------
# Personality system-prompt block (appended to the agent's tool prompt)
# --------------------------------------------------------------------------

PERSONALITY_BLOCK = (
    "Personality (J.A.R.V.I.S. — original assistant persona, not a human): "
    "intelligent, confident, observant, calm, quick-thinking, dry-witted but never "
    "sarcastic at the user's expense. Supportive and emotionally aware in tone only — "
    "you do not have feelings, memories, or a body; never claim otherwise and never "
    "invent experiences. "
    "Voice rules: conversational spoken English, varied sentence rhythm, occasional "
    "natural transitions ('Alright', 'Right', 'Actually', 'Give me a second') but sparingly. "
    "Address the user as 'sir' AT MOST once per reply, and skip it entirely in most replies. "
    "Never open two consecutive replies with the same phrase. "
    "Match length to the request: action confirmations are one short sentence; "
    "answers are at most two or three sentences unless detail was requested. "
    "Plain text only — no markdown, no bullet lists, no code fences, no emojis. "
    "If an action succeeded, say what is now true. If it failed, say what failed "
    "and the useful next step. Never report success without tool evidence."
)


def personality_directive(tone: str, avoid_opener: str = "") -> str:
    direction = _TONE_DIRECTION.get(tone, _TONE_DIRECTION[NEUTRAL])
    extra = f" Do not open your reply with {avoid_opener!r}." if avoid_opener else ""
    return f"Current tone: {tone}. {direction}{extra}"


# --------------------------------------------------------------------------
# Speech formatter: raw LLM output -> (speak, detail)
# --------------------------------------------------------------------------

_OPENERS = (
    "certainly", "of course", "understood", "done", "sure", "absolutely",
    "right", "alright", "okay", "got it", "yep",
)

_last_openers: deque = deque(maxlen=3)


def _strip_markdown(text: str) -> str:
    s = text or ""
    s = re.sub(r"```.*?```", " ", s, flags=re.S)          # code fences
    s = re.sub(r"`([^`]*)`", r"\1", s)                     # inline code
    s = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", s)        # images
    s = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", r"\1", s)       # links keep label
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.M)           # headings
    s = re.sub(r"[*_~]{1,3}(\S.*?\S)[*_~]{1,3}", r"\1", s)  # bold/italic/strike
    s = re.sub(r"^\s*[-*+]\s+", "", s, flags=re.M)         # bullets
    s = re.sub(r"^\s*\d+[.)]\s+", "", s, flags=re.M)       # numbered lists
    s = re.sub(r"^\s*>\s?", "", s, flags=re.M)             # quotes
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip(" \n")


def _cap_sir(text: str, allow: bool) -> str:
    if allow:
        parts = re.split(r"(?i)\bsir\b", text, maxsplit=1)
        if len(parts) == 2:
            # keep the single allowed "sir", drop any further ones
            rest = re.sub(r"(?i)\bsir\b[,.!]?", "", parts[1]).strip(" ,")
            text = (parts[0] + "sir" + (" " + rest if rest else "")).strip()
            text = re.sub(r"\s{2,}", " ", text)
        return text
    return re.sub(r"(?i)\bsir\b[,.!]?", "", text).strip(" ,")


def _first_opener_key(text: str) -> str:
    m = re.match(r"(?i)^([\w']+)", (text or "").strip())
    return (m.group(1).lower() if m else "")


def format_for_speech(raw: str, kind: str = "answer", tone: str = NEUTRAL,
                      detail_requested: bool = False) -> tuple:
    """Return (speak, detail). `speak` is what TTS reads; `detail` is the
    fuller text for HUD display (None when identical). Facts are preserved."""
    clean = _strip_markdown(raw or "").strip()
    if not clean:
        return "I didn't catch that clearly. Could you say it once more?", None

    # Last-mile guard: tool/LLM responses must not leak the legacy canned
    # acknowledgements the persona explicitly avoids. Preserve the useful
    # clause that follows when one exists.
    clean = re.sub(r"(?i)^done\s*,?\s*sir[.!]?\s*", "", clean).strip()
    clean = re.sub(r"(?i)^yes\s*,?\s*sir[.!]?\s*", "Understood. ", clean).strip()
    clean = re.sub(r"(?i)^okay\s*,?\s*sir[.!]?\s*", "Understood. ", clean).strip()
    clean = re.sub(r"(?i)^task completed\s*,?\s*sir[.!]?\s*", "The task is complete. ", clean).strip()
    clean = re.sub(r"(?i)^that'?s a great idea[.!]?\s*", "I’ll look into that. ", clean).strip()
    # Readiness is a UI/system state, not a conversational answer. Remove a
    # standalone readiness opener while preserving useful facts such as
    # “the installer is ready”.
    clean = re.sub(r"(?i)^i['’]?m\s+ready(?:\s*,?\s*sir)?[.!]?\s*", "", clean).strip()
    clean = re.sub(r"(?i)^i\s+am\s+ready(?:\s*,?\s*sir)?[.!]?\s*", "", clean).strip()
    if not clean:
        clean = "I didn’t get a useful response from the model."

    # Collapse to sentences for length control.
    flat = re.sub(r"\s*\n\s*", " ", clean)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", flat) if s.strip()]

    if kind == "confirm":
        speak = sentences[0] if sentences else clean
        words = speak.split()
        if len(words) > 25:
            speak = " ".join(words[:25]).rstrip(",;:") + "."
    elif detail_requested:
        speak = " ".join(sentences[:6])
    else:
        if len(clean.split()) > 60:
            speak = " ".join(sentences[:3])
            if len(speak.split()) > 70:
                speak = " ".join(speak.split()[:70]).rstrip(",;:") + "."
        else:
            speak = clean

    # Opener variety: never the same opener twice in a row.
    key = _first_opener_key(speak)
    if key in _OPENERS and _last_openers and key == _last_openers[-1]:
        alt = "Right" if key != "right" else "Alright"
        speak = re.sub(r"(?i)^[\w']+", alt, speak, count=1)
        key = alt.lower()
    if key in _OPENERS:
        _last_openers.append(key)

    # "sir" discipline: at most one, and only in a minority of tones.
    allow_sir = tone in (CONFIDENT, NEUTRAL, FOCUSED) and len(_last_openers) % 2 == 0
    speak = _cap_sir(speak, allow_sir)
    speak = re.sub(r"\s{2,}", " ", speak).strip()
    if speak and speak[-1] not in ".!?":
        speak += "."

    detail = None
    if clean != speak and len(clean.split()) > len(speak.split()) + 4:
        detail = clean
    return speak, detail


def reset_opener_memory() -> None:
    _last_openers.clear()


def build_context_block(history: list, last_result: str = "",
                        task: str = "") -> str:
    """Compact, relevant-only context for the planner prompt."""
    lines = []
    if task:
        lines.append(f"Active task: {task}")
    if last_result:
        lines.append(f"Last verified result: {last_result[:220]}")
    if history:
        tail = history[-4:]
        turns = []
        for h in tail:
            role = h.get("role", "?")
            content = str(h.get("content", ""))[:160]
            turns.append(f"{role}: {content}")
        lines.append("Recent turns: " + " | ".join(turns))
    return "\n".join(lines)
