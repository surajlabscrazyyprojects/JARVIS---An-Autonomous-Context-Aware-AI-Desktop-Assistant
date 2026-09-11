from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from jarvis.world_state import WorldStateManager


@dataclass
class CurrentContextSnapshot:
    user_intent: str = ""
    active_application: str = ""
    active_window: str = ""
    browser: Dict[str, Any] = field(default_factory=dict)
    project: Dict[str, Any] = field(default_factory=dict)
    task: Dict[str, Any] = field(default_factory=dict)
    referenced_entity: Dict[str, Any] = field(default_factory=dict)
    known: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    confidence: float = 0.0
    sources: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ContextFusionEngine:
    """Fuse current authorized state into an inspectable reasoning snapshot."""

    _REFERENCE_PATTERN = re.compile(r"\b(this|that|here|there|it|current page|this business|this file|the project|that result)\b", re.I)

    def __init__(self, world_state: WorldStateManager) -> None:
        self.world_state = world_state

    def snapshot(self, transcript: Optional[str] = None) -> CurrentContextSnapshot:
        state = self.world_state.get()
        transcript = transcript if transcript is not None else state.conversation.recent_transcript
        intent = self._infer_intent(transcript)
        reference = self._resolve_reference(transcript, state)
        known: List[str] = []
        unknown: List[str] = []

        if state.browser.active and (state.browser.title or state.browser.url):
            known.extend(item for item in (state.browser.title, state.browser.url) if item)
        else:
            unknown.append("current browser page")
        if state.project.root:
            known.append(f"project root: {state.project.root}")
        else:
            unknown.append("active project")
        if state.task.task_id:
            known.append(f"task status: {state.task.status}")
        else:
            unknown.append("running task")
        if state.active_window:
            known.append(f"active window: {state.active_window}")
        else:
            unknown.append("active window")

        confidence = 0.0
        if intent:
            confidence = 0.7
        if reference:
            confidence = max(confidence, float(reference.get("confidence", 0.0)))
        return CurrentContextSnapshot(
            user_intent=intent,
            active_application=state.active_application,
            active_window=state.active_window,
            browser=asdict(state.browser),
            project=asdict(state.project),
            task=asdict(state.task),
            referenced_entity=reference,
            known=known,
            unknown=unknown,
            confidence=confidence,
            sources={name: source.to_dict() for name, source in state.sources.items()},
        )

    def _infer_intent(self, transcript: str) -> str:
        text = (transcript or "").lower()
        if re.search(r"\b(build|create|make|develop)\b.*\b(website|site|app|application)\b", text):
            return "build_website" if "website" in text or "site" in text else "build_application"
        if re.search(r"\b(open|launch)\b", text):
            return "open"
        if re.search(r"\b(stop|cancel|abort|pause|wait)\b", text):
            return "cancel_task"
        if text:
            return "conversation"
        return ""

    def _resolve_reference(self, transcript: str, state: Any) -> Dict[str, Any]:
        match = self._REFERENCE_PATTERN.search(transcript or "")
        if not match:
            return {}
        if state.browser.active and (state.browser.title or state.browser.url):
            return {
                "type": "browser_page",
                "title": state.browser.title,
                "url": state.browser.url,
                "phrase": match.group(0),
                "confidence": 0.88,
                "basis": "authorized browser metadata",
            }
        if state.project.root and state.project.active_file:
            return {
                "type": "project_file",
                "root": state.project.root,
                "file": state.project.active_file,
                "phrase": match.group(0),
                "confidence": 0.84,
                "basis": "project context",
            }
        return {
            "type": "unresolved_reference",
            "phrase": match.group(0),
            "confidence": 0.2,
            "basis": "no authorized matching source available",
        }
