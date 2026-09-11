"""Context-aware conversational reminder intelligence.

Sits on top of the deterministic :class:`RoutineEngine` reminder store.

Pipeline (per spec):
    USER MESSAGE -> temporal/intent extraction -> confidence scoring
    -> user-vs-other disambiguation -> duplicate/update detection
    -> (clarify | suggest | create) via the authoritative ReminderManager.

Groq is never the scheduler: it may *identify* a candidate, but the
deterministic ``RoutineEngine`` owns creation, persistence and triggering.
This module performs the deterministic extraction (offline-friendly) and is
structured so an LLM could be plugged in later without changing the flow.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from routine_engine import _parse_time, _date_str

# --- Configurable thresholds ------------------------------------------------
AUTO_CREATE_MIN = 0.9   # >= this -> AUTO-create (in AUTO mode)
CONFIRM_MIN = 0.7       # >= this -> ask confirmation (CONFIRM mode / medium)

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
    "saturday": 5, "sunday": 6, "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}
REL_DAYS = {
    "tomorrow": 1, "kal": 1, "aaj": 0, "today": 0, "parso": 2,
    "day after tomorrow": 2, "tonight": 0, "tonite": 0,
}
EVENT_KEYWORDS = [
    "test", "exam", "class", "lecture", "meeting", "appointment", "gym",
    "workout", "call", "submit", "assignment", "homework", "teach",
    "teacher", "doctor", "dentist", "interview", "presentation", "deadline",
    "event", "party", "dinner", "lunch", "breakfast", "bank", "office",
    "school", "college", "tuition", "session", "webinar", "conference",
    "flight", "train", "bus", "pooja", "prayer", "lab", "workshop",
]

# Regexes ------------------------------------------------------------------
TIME_RE = re.compile(
    r'\b(\d{1,2}):(\d{2})(?:\s*(am|pm))?\b'
    r'|\b(?:at|around|by|on|from)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.|baje|o\'?clock)?\b'
    r'|\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.|baje|o\'?clock)\b',
    re.I)
IN_RE = re.compile(r'in (\d+)\s*(minute|min|hour|hr)s?', re.I)
WEEKDAY_RECUR_RE = re.compile(r'every\s+(\w+)\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', re.I)
COMMIT_RE = re.compile(
    r"\b(i|my)\b.*?\b(have|have to|have got|got to|need to|want to|must|will|"
    r"am going to|ve got|ve to|need|don'?t let me forget|jaana hai|karna hai|"
    r"karni hai)\b", re.I)
HING_COMMIT_RE = re.compile(
    r"\b(mera|mujhe|meri|apna|hamaara)\b.{0,40}\b(hai|hain|karni|karna|jaana|"
    r"rakhna|yaad)\b", re.I)
HYPO_RE = re.compile(
    r"\b(might|maybe|may be|thinking about|someday|one day|if i|should probably|"
    r"perhaps|was thinking|planning to\?)\b", re.I)
OTHER_RE = re.compile(
    r"\b(my friend|my brother|my sister|my cousin|his|her|their|they|he|she|"
    r"friend has|brother has|sister has|mom has|dad has|mother has|father has)\b", re.I)
FORGET_RE = re.compile(
    r"(don'?t want to forget|don'?t let me forget|bhoolna mat|mat bhoolna|"
    r"might forget|forget about it|i'll forget|yaad rakhna padega)", re.I)
FILLER_RE = re.compile(
    r"\b(a|an|the|to|my|online|about|for|of|some|that|this|gonna|going|hai|hain|"
    r"ka|ki|ko|se|bhi|to|mera|mujhe|meri|apna|hamaara|at|on|by|an?|am|pm|baje|"
    r"o'clock|tomorrow|today|kal|aaj|parso|tonight|tonite)\b", re.I)


def _norm_topic(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


class ReminderIntel:
    def __init__(self, engine) -> None:
        self.engine = engine

    # -- public API -------------------------------------------------------
    def detect_mode_command(self, text: str) -> Optional[str]:
        low = text.lower()
        if ("conversation reminders" in low or "conversation reminder" in low
                or "auto reminders" in low or "reminders auto" in low):
            if any(k in low for k in ("off", "disable", "stop", "don't", "dont", "never")):
                return "OFF"
            if "confirm" in low:
                return "CONFIRM"
            if any(k in low for k in ("auto", "on", "enable")):
                return "AUTO"
            return None
        if "automatically" in low and "remind" in low:
            if any(k in low for k in ("don't", "dont", "off", "stop", "never", "disable")):
                return "OFF"
            return "AUTO"
        return None

    def process_message(self, text: str, history: Optional[List[str]] = None
                        ) -> Dict[str, Any]:
        now = self.engine.now()
        low = (text or "").lower().strip()
        res = self._result("none")

        if not low:
            return res
        # Explicit "remind me ..." is handled by RoutineEngine.handle_intent.
        if self._is_explicit_remind(low):
            return res
        if self._is_hypothetical(low):
            res["note"] = "hypothetical"
            return res
        if not self._user_related(low):
            res["note"] = "other_person"
            return res
        has_commit = self._commitment_present(low) or self._hing_commit(low)
        # Hindi/Bare-event fallback: event keyword + future date/time is enough
        # to ask for clarification (e.g. "Kal test hai." -> we should ask time).
        if not has_commit:
            low_has_event = any(k in low for k in EVENT_KEYWORDS)
            has_temporal = bool(re.search(r"\b(kal|aaj|tomorrow|today|tonight|parso|every|monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", low)) or bool(TIME_RE.search(low) or IN_RE.search(low))
            is_update_phrase = bool(re.search(r"\b(actually|really|change|shift|move|update|correct|instead)\b", low))
            # Time-only follow-up with history containing an event (spec 20)
            is_time_followup = False
            if history and (TIME_RE.search(low) or IN_RE.search(low)):
                for hl in history[-3:]:
                    if any(k in (hl or "").lower() for k in EVENT_KEYWORDS):
                        is_time_followup = True
                        break
            if has_temporal and low_has_event:
                has_commit = True
            elif is_time_followup:
                has_commit = True
            elif is_update_phrase and (low_has_event or has_temporal):
                # "My test is actually at 8:30" – allow update path without strong commitment
                has_commit = True
            elif self._forgetting_concern(low):
                has_commit = True
            else:
                res["note"] = "no_commitment"
                return res

        clauses = self._split_clauses(text) or [text]
        forgetting = self._forgetting_concern(low)
        candidates: List[Dict[str, Any]] = []
        # For short follow-ups like "At 6." with no topic, borrow topic from history
        history_topics = []
        if history:
            for hl in history[-3:]:
                ht = self._extract_topic((hl or "").lower(), None)
                if ht and self._has_event_keyword(ht):
                    history_topics.append(ht)
        for clause in clauses:
            cl = clause.lower()
            td = self._extract_time_date(cl, now, history if history else None)
            topic = self._extract_topic(cl, td.get("time_raw"))
            if not topic and td["time"] is not None and history_topics:
                # Time-only follow-up: reuse last event topic from history
                topic = history_topics[-1]
            if not topic:
                continue
            # A clause with neither a time nor a concrete event keyword is just
            # filler (e.g. "don't let me forget") -> ignore it.
            if td["time"] is None and not self._has_event_keyword(topic):
                continue
            conf = self._confidence(td, forgetting, cl)
            # Borrow date from history if missing (e.g. "At 6." after "gym tomorrow")
            if td["date"] is None and history:
                for hl in reversed(history[-3:]):
                    hd = self._resolve_date((hl or "").lower(), now)
                    if hd:
                        td["date"] = hd
                        break
            candidates.append({
                "topic": topic, "time": td["time"], "date": td["date"],
                "recurring": td["recurring"], "confidence": conf,
                "user_related": True, "forgetting_concern": forgetting,
            })
        if not candidates:
            res["note"] = "no_event_topic"
            return res

        mode = self.engine.get_conversation_mode()
        created, updated, suggest, clarify, dup = [], [], None, None, False

        for cand in candidates:
            if cand["time"] is None:
                # Missing time but a clear personal event -> ask.
                clarify = {"topic": cand["topic"], "date": cand["date"],
                           "user_related": True}
                break
            if mode == "OFF":
                continue
            exist = self._match_existing(cand["topic"], cand["date"], cand["time"])
            if exist:
                if exist.get("time") == cand["time"]:
                    dup = True
                    continue
                self.engine.update_reminder(exist["id"], time=cand["time"],
                                            date=cand["date"])
                updated.append(self.engine.get_reminder(exist["id"]))
                continue
            if cand["confidence"] >= AUTO_CREATE_MIN:
                if mode == "AUTO":
                    r = self.engine.create_reminder(
                        cand["time"], cand["topic"],
                        repeat=(cand["recurring"] or "none"),
                        source="CONVERSATION", date=cand["date"])
                    created.append(r)
                    continue
                else:  # CONFIRM -> ask first
                    suggest = cand
                    break
            elif cand["confidence"] >= CONFIRM_MIN:
                # In AUTO, medium confidence still suggests rather than silently creating,
                # but we must NOT break early when multiple candidates exist – collect all.
                if len(candidates) > 1 and mode == "AUTO":
                    # Accumulate as created if forgetting concern pushes it (spec 14)
                    if cand["forgetting_concern"]:
                        r = self.engine.create_reminder(
                            cand["time"], cand["topic"],
                            repeat=(cand["recurring"] or "none"),
                            source="CONVERSATION", date=cand["date"])
                        created.append(r)
                        continue
                suggest = cand
                break
            else:
                continue

        if created:
            res = self._result("create", created=created,
                               log=["REMINDER_CREATED_FROM_CONVERSATION"])
        elif updated:
            res = self._result("update", updated=updated,
                               log=["REMINDER_UPDATED_FROM_CONVERSATION"])
        elif clarify:
            res = self._result("clarify", clarify=clarify,
                               log=["REMINDER_CONFIRMATION_REQUIRED"])
        elif suggest:
            res = self._result("suggest", suggest=suggest,
                               log=["REMINDER_CONFIRMATION_REQUIRED"])
        elif dup:
            res = self._result("none", duplicate=True,
                               log=["REMINDER_DUPLICATE_DETECTED"])
        return res

    # -- internals --------------------------------------------------------
    @staticmethod
    def _result(action, **kw):
        out = {"action": action, "created": [], "updated": [], "suggest": None,
               "clarify": None, "duplicate": False, "note": None,
               "response_hint": "", "log": []}
        out.update(kw)
        return out

    @staticmethod
    def _is_explicit_remind(low: str) -> bool:
        return "remind me" in low or bool(re.search(r"\bremind\b.{0,15}\b(me|us)\b", low))

    @staticmethod
    def _is_hypothetical(low: str) -> bool:
        return bool(HYPO_RE.search(low))

    @staticmethod
    def _user_related(low: str) -> bool:
        if OTHER_RE.search(low):
            # "call my mom" is still the user's action.
            if re.search(r"\b(call|text|message|msg|phone|video)\b.{0,15}"
                         r"\b(mom|dad|mother|father|papa|mummy|maa)\b", low):
                return True
            return False
        return True

    @staticmethod
    def _commitment_present(low: str) -> bool:
        return bool(COMMIT_RE.search(low))

    @staticmethod
    def _hing_commit(low: str) -> bool:
        return bool(HING_COMMIT_RE.search(low))

    @staticmethod
    def _forgetting_concern(low: str) -> bool:
        return bool(FORGET_RE.search(low))

    @staticmethod
    def _has_event_keyword(topic: str) -> bool:
        t = (topic or "").lower()
        return any(k in t for k in EVENT_KEYWORDS)

    @staticmethod
    def _split_clauses(text: str) -> List[str]:
        parts = re.split(r",|\band\b|then|after that|;| \+ ", text, flags=re.I)
        return [p.strip() for p in parts if p.strip()]

    def _extract_time_date(self, low: str, now: datetime,
                           history: Optional[List[str]] = None
                           ) -> Dict[str, Any]:
        res = {"time": None, "date": None, "recurring": None, "time_raw": None}

        m = IN_RE.search(low)
        if m:
            n = int(m.group(1))
            unit = m.group(2)[:3]
            dt = now + (timedelta(minutes=n) if unit == "min" else timedelta(hours=n))
            res["time"] = f"{dt.hour:02d}:{dt.minute:02d}"
            res["date"] = _date_str(dt)
            res["time_raw"] = m.group(0)
            return res

        mw = WEEKDAY_RECUR_RE.search(low)
        if mw and mw.group(1).lower() in WEEKDAYS:
            t = _parse_time(f"{mw.group(2)}:{mw.group(3) or '00'}"
                            f"{(' ' + mw.group(4)) if mw.group(4) else ''}")
            if t:
                res["recurring"] = "weekly"
                res["time"] = t
                res["time_raw"] = mw.group(0)
                return res

        src = TIME_RE.search(low)
        if src:
            if src.group(1) is not None:           # HH:MM
                h, mm = int(src.group(1)), int(src.group(2))
                ap = (src.group(3) or "").replace(".", "").lower()
            elif src.group(4) is not None:         # prep HH(:MM) [ap]
                h, mm = int(src.group(4)), int(src.group(5) or 0)
                ap = (src.group(6) or "").replace(".", "").lower()
            else:                                  # HH(am/pm/baje)
                h, mm = int(src.group(7)), int(src.group(8) or 0)
                ap = (src.group(9) or "").replace(".", "").lower()
            ap = ap or ""
            if ap == "pm":
                if h < 12:
                    h += 12
            elif ap == "am":
                if h == 12:
                    h = 0
            elif ap == "baje":
                pass  # leave; default AM for <=11
            else:
                if h <= 11 and re.search(r"(night|evening|tonight|tonite|raat|shaam|rat)", low):
                    h += 12
                if re.search(r"(morning|subah|savera)", low):
                    if h == 12:
                        h = 0
                    elif h > 12:
                        h -= 12
            res["time"] = f"{h:02d}:{mm:02d}"
            res["time_raw"] = src.group(0)

        # if still no time, try recent history context (TEST 20 style)
        if res["time"] is None and history:
            for hline in reversed(history[-3:]):
                hs = TIME_RE.search((hline or "").lower())
                if hs:
                    if hs.group(1) is not None:
                        h, mm = int(hs.group(1)), int(hs.group(2))
                    elif hs.group(4) is not None:
                        h, mm = int(hs.group(4)), int(hs.group(5) or 0)
                    else:
                        h, mm = int(hs.group(7)), int(hs.group(8) or 0)
                    res["time"] = f"{h:02d}:{mm:02d}"
                    res["time_raw"] = hs.group(0)
                    break

        res["date"] = self._resolve_date(low, now)
        return res

    @staticmethod
    def _resolve_date(low: str, now: datetime) -> Optional[str]:
        for kw, off in REL_DAYS.items():
            if re.search(r"\b" + re.escape(kw) + r"\b", low):
                return _date_str(now + timedelta(days=off))
        for wd, idx in WEEKDAYS.items():
            if re.search(r"\b" + re.escape(wd) + r"\b", low) and f"every {wd}" not in low:
                days_ahead = (idx - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                return _date_str(now + timedelta(days=days_ahead))
        return None

    def _extract_topic(self, clause_low: str, time_raw: Optional[str]) -> Optional[str]:
        s = clause_low
        if time_raw:
            s = s.replace(time_raw, " ")
        s = re.sub(r"^(i|my)\s+(have|have to|have got|got to|need to|want to|must|"
                   r"will|am going to|ve got|ve to|need|don'?t let me forget)\s*",
                   "", s)
        s = FILLER_RE.sub(" ", s)
        words = [w for w in re.findall(r"[a-z]+", s) if w]
        if not words:
            return None
        kw = None
        for w in words:
            if w in EVENT_KEYWORDS:
                kw = w
                break
        if kw:
            i = words.index(kw)
            window = words[max(0, i - 2):i + 3]
            topic = " ".join(window)
        else:
            topic = " ".join(words[:4])
        topic = topic.strip()
        return topic[:60] if topic else None

    @staticmethod
    def _confidence(td: Dict[str, Any], forgetting: bool, clause_low: str) -> float:
        c = 0.55
        if td.get("time"):
            c += 0.20
        if td.get("date"):
            c += 0.05
        if forgetting:
            c += 0.15
        if re.search(r"(need to|have to|don't let me forget|bhoolna mat|jaana hai|"
                     r"karna hai|karni hai)", clause_low):
            c += 0.10
        if td.get("topic"):
            c += 0.05
        return min(1.0, c)

    def _match_existing(self, topic: str, date: Optional[str],
                        time: str) -> Optional[Dict[str, Any]]:
        for r in self.engine.get_reminders():
            if not r.get("enabled", True):
                continue
            if r.get("status") not in ("scheduled", "triggered"):
                continue
            if not self._topic_match(topic, r["topic"]):
                continue
            if date is not None and r.get("date") is not None and date != r.get("date"):
                continue
            if r.get("time") == time:
                return r
        for r in self.engine.get_reminders():
            if not r.get("enabled", True):
                continue
            if self._topic_match(topic, r["topic"]):
                if date is not None and r.get("date") is not None and date != r.get("date"):
                    continue
                return r
        return None

    @staticmethod
    def _topic_match(a: str, b: str) -> bool:
        na, nb = _norm_topic(a), _norm_topic(b)
        if not na or not nb:
            return False
        if na == nb:
            return True
        if na in nb or nb in na:
            return True
        sa = set(re.findall(r"[a-z]+", na)) - {"test", "the", "my", "a", "an"}
        sb = set(re.findall(r"[a-z]+", nb)) - {"test", "the", "my", "a", "an"}
        shared = sa & sb
        return len(shared) >= 1
