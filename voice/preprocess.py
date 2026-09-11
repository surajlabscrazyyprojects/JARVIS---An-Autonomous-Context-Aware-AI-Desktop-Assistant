"""
Speech preparation: preprocess raw assistant text and split it into safe,
natural phrases for TTS. No markdown / code / URLs are read aloud.
"""
from __future__ import annotations

import re

# Things we must never speak aloud.
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_BOLD_ITALIC_RE = re.compile(r"(\*\*|__|\*|_|~~|#+\s*)")
_JSON_RE = re.compile(r"\{[^{}]*\}".replace(" ", ""))  # rough single-level JSON
_EMOJI_RE = re.compile(
    "[" 
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F02F"
    "\U0000FE00-\U0000FE0F"
    "\U00002000-\U0000206F"
    "]+", flags=re.UNICODE)
_STACK_TRACE_RE = re.compile(r"(Traceback \(most recent call last\)|File \".*?\", line \d+)", re.I)
_SHORTCODE_RE = re.compile(r":[a-z0-9_+\\-]+:", re.I)
# Speech-hostile internal markers: tool ids, debug/status labels, uuids, params.
_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_INTERNAL_ID_RE = re.compile(r"\b(task[_\s-]?id|item[_\s-]?id|job[_\s-]?id)\s*[:=]\s*[\w\-]+", re.I)
_BRACKET_LABEL_RE = re.compile(r"\[(debug|info|warn|error|tool|task|status|notice|hud)\]", re.I)
_STATUS_NAME_RE = re.compile(r"\b(VERIFICATION|VALIDATION|EXECUTION|COMPLETION|FAILURE|SUCCESS|PENDING|READY)_[A-Z0-9_]+\b")
_PARAM_RE = re.compile(r"\b(status|tool|action|intent|mode|session)\s*[:=]\s*[\w\-]+", re.I)

# Protect these from sentence splitting.
_ABBREV = re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|e\.g|i\.e|apt|vol|fig|vs)\.")
_DECIMAL = re.compile(r"\d+\.\d+")
_FILE_TOKEN = re.compile(r"\b[\w\-./\\]+\.[A-Za-z0-9]{1,6}\b")


def preprocess_text(text: str) -> str:
    """Normalize text for natural speech. Returns cleaned text (tags NOT added here)."""
    if not text:
        return ""
    t = text

    # Strip code fences and inline code first (highest priority).
    t = _CODE_FENCE_RE.sub(" ", t)
    t = _INLINE_CODE_RE.sub(lambda m: _spell_code(m.group(1)), t)

    # Stack traces / internal metadata.
    t = _STACK_TRACE_RE.sub(" ", t)

    # URLs -> short spoken placeholder (never read char-by-char).
    t = _URL_RE.sub("a web link", t)

    # JSON blobs -> drop.
    t = _JSON_RE.sub(" ", t)

    # Markdown syntax characters.
    t = _MD_BOLD_ITALIC_RE.sub("", t)

    # Emojis -> remove (keeps speech clean; emotion is expressed via tags).
    t = _EMOJI_RE.sub("", t)

    # Emoji shortcodes like :fire: :smile:
    t = _SHORTCODE_RE.sub("", t)

    # Internal/debug markers -> drop (never read aloud as labels).
    t = _UUID_RE.sub(" ", t)
    t = _INTERNAL_ID_RE.sub(" ", t)
    t = _BRACKET_LABEL_RE.sub(" ", t)
    t = _STATUS_NAME_RE.sub(" ", t)
    t = _PARAM_RE.sub(" ", t)

    # Collapse excessive symbols but keep sentence punctuation.
    t = re.sub(r"(\*\*|__|~~)+", " ", t)
    t = re.sub(r"[#*`>|]+", " ", t)
    t = re.sub(r"\s{2,}", " ", t)

    # Normalize a few abbreviations for nicer reading.
    t = re.sub(r"\bOK\b", "okay", t)
    t = re.sub(r"\bU\b", "you", t)
    t = re.sub(r"\bw/\b", "with ", t)
    t = re.sub(r"\bcouldn't\b", "could not", t)

    return t.strip()


def _spell_code(code: str) -> str:
    # Read code as a short label, not verbatim symbols.
    code = code.strip()
    if not code:
        return " "
    if len(code) <= 24:
        return " " + code + " "
    return " a code snippet "


def segment_sentences(text: str, max_len: int = 220) -> list[str]:
    """Split into natural phrases WITHOUT breaking numbers, file names, URLs,
    decimals or abbreviations. Each segment keeps enough context to sound natural.
    """
    if not text:
        return []
    # Protect tokens that must not be split internally.
    protected = []

    def _protect(token: str) -> str:
        protected.append(token)
        return f"\u0001{len(protected) - 1}\u0001"

    t = _DECIMAL.sub(lambda m: _protect(m.group(0)), text)
    t = _ABBREV.sub(lambda m: _protect(m.group(0)), t)
    t = _FILE_TOKEN.sub(lambda m: _protect(m.group(0)), t)

    # Sentence boundaries: . ! ? ... newlines. Keep the delimiter attached.
    raw_parts = re.split(r"(?<=[.!?])\s+|(?:\.\.\.)\s*|\n+", t)
    segments: list[str] = []
    for part in raw_parts:
        part = _restore(part.strip(), protected)
        if not part:
            continue
        # Further split over-long segments at commas for better rhythm.
        if len(part) > max_len and "," in part:
            for sub in part.split(","):
                sub = sub.strip()
                if sub:
                    segments.append(sub + ",")
        else:
            segments.append(part)

    # Restore any leftover protected tokens in segments.
    out = []
    for s in segments:
        s = _restore(s, protected)
        s = s.strip()
        if s:
            out.append(s)
    return out


def _restore(s: str, protected: list[str]) -> str:
    def repl(m):
        idx = int(m.group(1))
        return protected[idx] if 0 <= idx < len(protected) else m.group(0)
    return re.sub(r"\u0001(\d+)\u0001", repl, s)
