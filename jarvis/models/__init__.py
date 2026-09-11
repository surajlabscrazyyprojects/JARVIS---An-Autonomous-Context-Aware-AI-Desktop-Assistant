from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class IntentType(str, Enum):
    OPEN_APPLICATION = "open_application"
    CLOSE_APPLICATION = "close_application"
    OPEN_URL = "open_url"
    SITE_SEARCH = "site_search"
    RESEARCH = "research"
    RESEARCH_AND_OPEN = "research_and_open"
    SCREEN_QUERY = "screen_query"
    OPEN_FILE = "open_file"
    CREATE_NOTE = "create_note"
    TERMINAL_EXEC = "terminal_exec"
    TASK_CONTROL = "task_control"
    CONVERSATION = "conversation"
    STUDY_GOAL = "study_goal"
    LEARN_GOAL = "learn_goal"
    CODE_FIX = "code_fix"
    FILE_CLEAN = "file_clean"
    DIRECT_ACTION = "direct_action"
    UNKNOWN = "unknown"


@dataclass
class ToolResult:
    success: bool = True
    verified: bool = True
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: int = 0
    verification_method: str = "none"


@dataclass
class ActionStep:
    tool: str
    description: str
    args: Dict[str, Any] = field(default_factory=dict)
    verify: Optional[Dict[str, Any]] = None
    risk: str = "safe"
    requires_confirmation: bool = False


@dataclass
class Plan:
    goal: str
    explanation: str = ""
    emotion: str = "neutral"
    requires_confirmation: bool = False
    permission_text: str = ""
    steps: List[ActionStep] = field(default_factory=list)


@dataclass
class ActionIntent:
    intent: IntentType | str = IntentType.UNKNOWN
    confidence: float = 1.0
    goal: str = ""
    raw: str = ""
    app: Optional[str] = None
    url: Optional[str] = None
    destination: Optional[str] = None
    query: Optional[str] = None
    path: Optional[str] = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    success: bool
    verified: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


__all__ = [
    "ActionIntent",
    "ActionResult",
    "ActionStep",
    "IntentType",
    "Plan",
    "ToolResult",
]
