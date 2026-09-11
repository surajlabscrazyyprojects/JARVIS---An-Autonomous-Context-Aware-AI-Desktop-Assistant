from __future__ import annotations

import re
from typing import Any, Optional


class Brain:
    def __init__(self, client: Any = None, model: Optional[str] = None) -> None:
        self.client = client
        self.model = model

    def _memory_required(self, prompt: str) -> bool:
        p = prompt.lower().strip()
        smalltalk = [
            "how are you", "hello", "hi", "hey", "who are you", "what are you",
            "good morning", "good evening", "thanks", "thank you"
        ]
        if any(p == s or p.startswith(s + " ") for s in smalltalk):
            return False
        keywords = ["task", "progress", "yesterday", "last", "remember", "project", "file", "routine", "study", "exam", "continue"]
        return any(k in p for k in keywords)

    async def respond(self, text: str) -> str:
        return f"Understood, sir: {text}."
