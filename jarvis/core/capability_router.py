from __future__ import annotations

from typing import List, Optional

from jarvis.models import IntentType


class CapabilityRouter:
    def for_intent(self, intent: IntentType | str) -> List[str]:
        if isinstance(intent, str):
            try:
                intent = IntentType(intent)
            except ValueError:
                pass

        if intent == IntentType.OPEN_APPLICATION:
            return ["application.open", "application.focus"]
        if intent == IntentType.CLOSE_APPLICATION:
            return ["application.close"]
        if intent == IntentType.OPEN_URL:
            return ["browser.open", "browser.navigate"]
        if intent in (IntentType.RESEARCH, IntentType.RESEARCH_AND_OPEN, IntentType.SITE_SEARCH):
            return ["browser.search", "browser.playback", "browser.extract_links", "browser.navigate"]
        if intent == IntentType.SCREEN_QUERY:
            return ["vision.analyze", "vision.ocr", "vision.active_window"]
        if intent == IntentType.TERMINAL_EXEC:
            return ["terminal.execute", "terminal.inspect"]
        if intent == IntentType.OPEN_FILE:
            return ["filesystem.open", "filesystem.read"]
        if intent == IntentType.CREATE_NOTE:
            return ["application.open", "keyboard.type", "filesystem.write"]
        if intent in (IntentType.STUDY_GOAL, IntentType.LEARN_GOAL):
            return ["browser.search", "browser.navigate", "application.open", "notes.create", "timer.start"]
        if intent == IntentType.CODE_FIX:
            return ["terminal.inspect", "filesystem.read", "filesystem.write", "terminal.execute"]
        if intent == IntentType.FILE_CLEAN:
            return ["filesystem.inspect", "filesystem.recycle"]
        return ["conversation.respond"]


_ROUTER_INSTANCE: Optional[CapabilityRouter] = None


def get_capability_router() -> CapabilityRouter:
    global _ROUTER_INSTANCE
    if _ROUTER_INSTANCE is None:
        _ROUTER_INSTANCE = CapabilityRouter()
    return _ROUTER_INSTANCE
