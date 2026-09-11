from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

from jarvis.ai.openrouter import ModelRole
from jarvis.ai.providers import ProviderRouter

logger = logging.getLogger("jarvis.classifier")


class InstructionType(str, Enum):
    GLOBAL_COMMAND = "GLOBAL_COMMAND"
    TASK_UPDATE = "TASK_UPDATE"
    TASK_REPLACEMENT = "TASK_REPLACEMENT"
    TASK_CANCELLATION = "TASK_CANCELLATION"
    TASK_PAUSE = "TASK_PAUSE"
    QUESTION = "QUESTION"
    STATUS_REQUEST = "STATUS_REQUEST"
    NEW_INDEPENDENT_TASK = "NEW_INDEPENDENT_TASK"


class InstructionClassifier:
    """Classifies new user speech received during an active task session.
    
    Uses deterministic sub-millisecond regex matching for unambiguous commands
    (stop, pause, how's it going, cancel) and FAST_INTENT AI for semantic nuance.
    """

    # Fast patterns for cancellation
    CANCEL_PATTERNS = re.compile(
        r"^(stop|cancel|abort|halt|stand down|quit|terminate|never mind|forget it|leave it|don'?t do (that|it)|drop this|shut down)\b",
        re.IGNORECASE,
    )

    # Fast patterns for pause
    PAUSE_PATTERNS = re.compile(
        r"^(pause|hold on|wait|give me a second|freeze|hold up|pause this)\b",
        re.IGNORECASE,
    )

    # Fast patterns for status
    STATUS_PATTERNS = re.compile(
        r"\b(how('?s| is) it going|what are you doing|current status|status update|progress report|where are we|what('?s| is) the progress|how far are you)\b",
        re.IGNORECASE,
    )

    def __init__(self, provider_router: Optional[ProviderRouter] = None) -> None:
        self.router = provider_router

    def classify_deterministic(self, text: str, has_active_task: bool = False) -> Optional[InstructionType]:
        cleaned = text.strip().lower()

        # 1. Cancellation check
        if self.CANCEL_PATTERNS.search(cleaned):
            return InstructionType.TASK_CANCELLATION

        # 2. Pause check
        if self.PAUSE_PATTERNS.search(cleaned):
            return InstructionType.TASK_PAUSE

        # 3. Status check
        if self.STATUS_PATTERNS.search(cleaned):
            return InstructionType.STATUS_REQUEST

        # 4. Global system commands (volume, brightness, mute)
        if re.search(r"\b(mute|unmute|volume up|volume down|set volume|screen brightness)\b", cleaned):
            return InstructionType.GLOBAL_COMMAND

        # 5. Task Replacement
        if re.search(r"\b(forget this|instead of this|change the plan completely|scrap this|switch to a different|do another)\b", cleaned):
            return InstructionType.TASK_REPLACEMENT

        return None

    def classify(self, text: str, active_task_goal: str = "") -> InstructionType:
        """Classify user instruction against the current active task."""
        det = self.classify_deterministic(text, has_active_task=bool(active_task_goal))
        if det:
            return det

        # If no active task, it's either a question, global command, or a new task
        if not active_task_goal:
            if text.strip().endswith("?") or re.search(r"^(who|what|when|where|why|how|can you tell me)\b", text.strip(), re.I):
                return InstructionType.QUESTION
            return InstructionType.NEW_INDEPENDENT_TASK

        # If there is an active task and deterministic didn't match, check if it's modifying the active task
        # Examples: "Make it darker", "Make the hero section smaller", "Actually use Python"
        if re.search(r"\b(make it|change the|use|add|remove|update|smaller|bigger|darker|lighter|instead|actually)\b", text, re.I):
            return InstructionType.TASK_UPDATE

        # Use FAST_INTENT model if available for nuanced utterances
        if self.router:
            try:
                prompt = (
                    f"You are a fast intent classifier for a computer assistant.\n"
                    f"Active Task: '{active_task_goal}'\n"
                    f"User just said: '{text}'\n\n"
                    f"Classify into exactly ONE of:\n"
                    f"- TASK_UPDATE: modifies/adjusts requirements for the active task\n"
                    f"- TASK_REPLACEMENT: replaces active task with something entirely different\n"
                    f"- TASK_CANCELLATION: stops the active task\n"
                    f"- TASK_PAUSE: pauses the active task\n"
                    f"- STATUS_REQUEST: asks how the active task is going\n"
                    f"- QUESTION: conversational question unrelated to modifying the task\n"
                    f"- NEW_INDEPENDENT_TASK: completely independent new task to run alongside\n"
                    f"- GLOBAL_COMMAND: system-level utility command\n\n"
                    f"Output ONLY the category name."
                )
                res = self.router.chat(
                    messages=[{"role": "user", "content": prompt}],
                    role=ModelRole.FAST_INTENT,
                    max_tokens=32,
                    temperature=0.0,
                    is_foreground=True,
                )
                choices = res.get("response", {}).get("choices", [])
                if choices:
                    cat = choices[0].get("message", {}).get("content", "").strip().upper()
                    for t in InstructionType:
                        if t.value in cat:
                            return t
            except Exception as e:
                logger.warning(f"[InstructionClassifier] LLM classification fallback: {e}")

        # Default fallback: if question-like, QUESTION, else TASK_UPDATE if task active, else NEW_INDEPENDENT_TASK
        if text.strip().endswith("?"):
            return InstructionType.QUESTION
        return InstructionType.TASK_UPDATE if active_task_goal else InstructionType.NEW_INDEPENDENT_TASK
