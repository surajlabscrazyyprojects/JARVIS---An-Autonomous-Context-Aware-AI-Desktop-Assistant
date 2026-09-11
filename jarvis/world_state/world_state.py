from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ContextSource:
    source: str
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    availability: str = "available"
    permission: str = "not_required"
    scope: str = "session"
    retention: str = "ephemeral"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VisionState:
    summary: str = ""
    screen_state_label: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class TerminalState:
    running: bool = False
    cwd: str = ""
    last_command: str = ""
    last_exit_code: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class BrowserState:
    active: bool = False
    url: str = ""
    title: str = ""
    text: str = ""
    target_id: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProjectState:
    root: str = ""
    language: str = ""
    framework: str = ""
    package_manager: str = ""
    active_file: str = ""
    git_branch: str = ""
    last_error: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class TaskState:
    task_id: str = ""
    goal: str = ""
    status: str = ""
    request_id: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConversationState:
    recent_transcript: str = ""
    recent_intent: str = ""
    last_tool_result: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class SystemStateDict:
    inference_mode: str = "normal"


@dataclass
class WorldState:
    timestamp: float = field(default_factory=time.time)
    active_window: str = ""
    active_application: str = ""
    vision: VisionState = field(default_factory=VisionState)
    terminal: TerminalState = field(default_factory=TerminalState)
    browser: BrowserState = field(default_factory=BrowserState)
    project: ProjectState = field(default_factory=ProjectState)
    task: TaskState = field(default_factory=TaskState)
    conversation: ConversationState = field(default_factory=ConversationState)
    system: SystemStateDict = field(default_factory=SystemStateDict)
    permissions: Dict[str, str] = field(default_factory=dict)
    available_tools: List[str] = field(default_factory=list)
    sources: Dict[str, ContextSource] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("application", "browser", "screen", "camera", "project", "task", "voice"):
            self.sources.setdefault(name, ContextSource(source=name, availability="unavailable"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "active_window": self.active_window,
            "active_application": self.active_application,
            "vision": asdict(self.vision),
            "terminal": asdict(self.terminal),
            "browser": asdict(self.browser),
            "project": asdict(self.project),
            "task": asdict(self.task),
            "conversation": asdict(self.conversation),
            "system": asdict(self.system),
            "permissions": dict(self.permissions),
            "available_tools": list(self.available_tools),
            "sources": {name: source.to_dict() for name, source in self.sources.items()},
        }


class WorldStateManager:
    def __init__(self, observer: Any = None, resource_manager: Any = None) -> None:
        self.observer = observer
        self.resource_manager = resource_manager
        self._state = WorldState()
        self._listeners: List[Callable[[str, Dict[str, Any]], None]] = []

    def subscribe(self, listener: Callable[[str, Dict[str, Any]], None]) -> None:
        self._listeners.append(listener)

    def _record_source(self, name: str, **metadata: Any) -> None:
        self._state.sources[name] = ContextSource(source=name, **metadata)
        self._state.timestamp = time.time()

    def _notify(self, event: str, payload: Dict[str, Any]) -> None:
        for listener in tuple(self._listeners):
            listener(event, payload)

    def apply_event(self, event: str, payload: Optional[Dict[str, Any]] = None) -> WorldState:
        payload = payload or {}
        now = time.time()
        if event == "ACTIVE_WINDOW_CHANGED":
            self._state.active_window = str(payload.get("title") or payload.get("active_window") or "")
            self._state.active_application = str(payload.get("application") or "")
            self._record_source("application", timestamp=now, confidence=float(payload.get("confidence", 1.0)), availability=payload.get("availability", "available"))
        elif event == "TRANSCRIPT_FINAL":
            self._state.conversation.recent_transcript = str(payload.get("text") or "")
            self._state.conversation.recent_intent = str(payload.get("intent") or "")
            self._state.conversation.timestamp = now
            self._record_source("voice", timestamp=now, confidence=float(payload.get("confidence", 1.0)), permission=payload.get("permission", "granted"))
        elif event in {"TASK_STARTED", "TASK_PROGRESS", "TASK_EXECUTING", "TASK_VERIFYING", "TASK_FAILED", "TASK_COMPLETED"}:
            self._state.task = TaskState(
                task_id=str(payload.get("task_id") or self._state.task.task_id),
                goal=str(payload.get("goal") or self._state.task.goal),
                status=str(payload.get("status") or event.removeprefix("TASK_").lower()),
                request_id=str(payload.get("request_id") or self._state.task.request_id),
                timestamp=now,
            )
            self._record_source("task", timestamp=now)
        elif event == "PROJECT_CHANGED":
            for key in ("root", "language", "framework", "package_manager", "active_file", "git_branch", "last_error"):
                if key in payload:
                    setattr(self._state.project, key, str(payload[key] or ""))
            self._state.project.timestamp = now
            self._record_source("project", timestamp=now, scope="workspace")
        elif event in {"BROWSER_TAB_CHANGED", "URL_CHANGED", "PAGE_CONTEXT_CHANGED"}:
            self._state.browser.active = bool(payload.get("active", True))
            self._state.browser.url = str(payload.get("url") or "")
            self._state.browser.title = str(payload.get("title") or "")
            self._state.browser.text = str(payload.get("text") or "")[:12000]
            self._state.browser.target_id = str(payload.get("target_id") or "")
            self._state.browser.timestamp = now
            self._record_source("browser", timestamp=now, confidence=float(payload.get("confidence", 1.0)), availability=payload.get("availability", "available"), permission="granted")
        elif event == "PERMISSION_CHANGED":
            name = str(payload.get("name") or "")
            if name:
                self._state.permissions[name] = str(payload.get("state") or "unknown")
                self._record_source(name, timestamp=now, permission=self._state.permissions[name])
        elif event == "TOOLS_CHANGED":
            self._state.available_tools = [str(tool) for tool in payload.get("tools", [])]
            self._record_source("tools", timestamp=now)
        elif event == "TOOL_RESULT":
            self._state.conversation.last_tool_result = str(payload.get("result") or "")
            self._state.conversation.timestamp = now
            self._record_source("tool", timestamp=now)
        else:
            return self._state
        self._notify(event, payload)
        return self._state

    def snapshot(self) -> Dict[str, Any]:
        return self.get().to_dict()

    def get(self) -> WorldState:
        if self.observer and hasattr(self.observer, "get_active_window"):
            active_window = self.observer.get_active_window()
            if active_window != self._state.active_window:
                self.apply_event("ACTIVE_WINDOW_CHANGED", {"active_window": active_window})
        return self._state

    def update_vision(self, summary: str, screen_state_label: str = "") -> None:
        self._state.vision.summary = summary
        self._state.vision.screen_state_label = screen_state_label
        self._state.vision.timestamp = time.time()
        self._record_source("screen", timestamp=self._state.vision.timestamp)

    def update_terminal(self, running: bool, cwd: str, last_command: str, last_exit_code: int) -> None:
        self._state.terminal.running = running
        self._state.terminal.cwd = cwd
        self._state.terminal.last_command = last_command
        self._state.terminal.last_exit_code = last_exit_code
        self._state.terminal.timestamp = time.time()
        self._record_source("terminal", timestamp=self._state.terminal.timestamp)

    def update_browser(self, active: bool, url: str, title: str = "") -> None:
        self._state.browser.active = active
        self._state.browser.url = url
        self._state.browser.title = title
        self._state.browser.timestamp = time.time()
        self._record_source("browser", timestamp=self._state.browser.timestamp, permission="granted" if active else "unknown")
