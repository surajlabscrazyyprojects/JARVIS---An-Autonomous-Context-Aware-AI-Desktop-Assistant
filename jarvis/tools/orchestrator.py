from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from jarvis.runtime import CapabilityRegistry


@dataclass
class OrchestrationResult:
    success: bool
    verified: bool
    tool: str
    action: str
    message: str = ""
    before: Any = None
    after: Any = None
    data: Dict[str, Any] = field(default_factory=dict)


class ToolOrchestrator:
    """Execute registered tool actions only when observation and verification pass."""

    def __init__(self, registry: CapabilityRegistry, adapters: Optional[Dict[str, Any]] = None) -> None:
        self.registry = registry
        self.adapters = adapters or {}

    def register_adapter(self, name: str, adapter: Any) -> None:
        self.adapters[name] = adapter

    def execute(
        self,
        tool: str,
        action: str,
        args: Optional[Dict[str, Any]] = None,
        observe: Optional[Callable[[], Any]] = None,
        verify: Optional[Callable[[Any, Any], bool]] = None,
    ) -> OrchestrationResult:
        capability = self.registry.detect(tool)
        if capability is None:
            return OrchestrationResult(False, False, tool, action, "Tool is not registered.")
        if capability.availability != "available":
            return OrchestrationResult(False, False, tool, action, f"Tool is {capability.availability}.")
        adapter = self.adapters.get(tool)
        if adapter is None or not hasattr(adapter, action):
            return OrchestrationResult(False, False, tool, action, "Tool action is unavailable.")

        before = observe() if observe else None
        try:
            result = getattr(adapter, action)(**(args or {}))
        except Exception as exc:  # noqa: BLE001
            return OrchestrationResult(False, False, tool, action, str(exc), before=before)
        after = observe() if observe else None
        verified = bool(verify(before, after)) if verify else False
        return OrchestrationResult(bool(result is not False), verified, tool, action, "Executed" if result is not False else "Action failed", before, after)
