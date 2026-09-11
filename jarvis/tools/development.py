from __future__ import annotations

import shutil
from typing import Dict, Iterable

from jarvis.runtime import Capability, CapabilityRegistry


DEVELOPMENT_TOOLS = {
    "OpenCode": ("opencode", "opencode"),
    "Codex": ("codex", "codex"),
    "Antigravity": ("antigravity", "antigravity"),
}


def register_development_tools(registry: CapabilityRegistry, candidates: Dict[str, Iterable[str]] | None = None) -> None:
    candidates = candidates or {name: (executable,) for name, (executable, _) in DEVELOPMENT_TOOLS.items()}
    for name, executables in candidates.items():
        executable = next((item for item in executables if shutil.which(item)), None)
        registry.register(Capability(
            name,
            f"External development tool: {name}",
            permissions=["filesystem", "terminal"],
            launch_method="verified_process_launch",
            input_method="adapter",
            execution_method="adapter",
            verification_method="process_and_workspace_check",
            executable=executable or next(iter(candidates[name]), ""),
            availability="available" if executable else "unavailable",
        ))
