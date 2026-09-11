from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class JournalEntry:
    entry_id: str
    task_id: str
    step_index: int
    step_description: str
    status: str  # "ACTIVE", "VERIFIED", "FAILED", "SKIPPED", "RECOVERED"
    evidence: str = ""
    error: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskCheckpoint:
    checkpoint_id: str
    task_id: str
    step_index: int
    goal: str
    status: str
    completed_steps: List[Dict[str, Any]]
    remaining_steps: List[Dict[str, Any]]
    context_snapshot: Dict[str, Any]
    artifacts: List[Dict[str, Any]]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskJournal:
    """Persistent audit trail and checkpointing system for JARVIS tasks.
    
    Prevents repeating verified steps and allows seamless crash recovery.
    """

    def __init__(self, journal_path: Optional[Path] = None, checkpoint_dir: Optional[Path] = None) -> None:
        self.journal_path = journal_path or Path("memory/task_journal.jsonl")
        self.checkpoint_dir = checkpoint_dir or Path("memory/checkpoints")
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._entries: List[JournalEntry] = []
        self._load_journal()

    def _load_journal(self) -> None:
        if not self.journal_path.exists():
            return
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        self._entries.append(JournalEntry(**d))
                    except Exception:
                        pass
        except Exception:
            pass

    def record_step(
        self,
        task_id: str,
        step_index: int,
        step_description: str,
        status: str,
        evidence: str = "",
        error: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> JournalEntry:
        entry_id = f"JRN-{task_id}-{step_index}-{int(time.time() * 1000) % 100000}"
        entry = JournalEntry(
            entry_id=entry_id,
            task_id=task_id,
            step_index=step_index,
            step_description=step_description,
            status=status.upper(),
            evidence=evidence,
            error=error,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._entries.append(entry)
        try:
            with open(self.journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except Exception:
            pass
        return entry

    def is_step_completed(self, task_id: str, step_description: str) -> bool:
        """Check if a step was already verified for this task to avoid repeating work."""
        norm_target = step_description.strip().lower()
        for e in self._entries:
            if e.task_id == task_id and e.status == "VERIFIED":
                if e.step_description.strip().lower() == norm_target:
                    return True
        return False

    def get_task_entries(self, task_id: str) -> List[JournalEntry]:
        return [e for e in self._entries if e.task_id == task_id]

    def create_checkpoint(
        self,
        task_id: str,
        step_index: int,
        goal: str,
        status: str,
        completed_steps: List[Dict[str, Any]],
        remaining_steps: List[Dict[str, Any]],
        context_snapshot: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
    ) -> TaskCheckpoint:
        checkpoint_id = f"chk_{task_id}_{step_index}_{int(time.time())}"
        cp = TaskCheckpoint(
            checkpoint_id=checkpoint_id,
            task_id=task_id,
            step_index=step_index,
            goal=goal,
            status=status,
            completed_steps=completed_steps,
            remaining_steps=remaining_steps,
            context_snapshot=context_snapshot or {},
            artifacts=artifacts or [],
            timestamp=time.time(),
        )
        file_path = self.checkpoint_dir / f"{task_id}.json"
        try:
            file_path.write_text(json.dumps(cp.to_dict(), indent=2), encoding="utf-8")
        except Exception:
            pass
        return cp

    def load_latest_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        file_path = self.checkpoint_dir / f"{task_id}.json"
        if not file_path.exists():
            return None
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return TaskCheckpoint(**data)
        except Exception:
            return None

    def generate_status_summary(self, task_id: str, goal: str = "") -> str:
        """Generate accurate natural-language progress report from verified journal entries."""
        entries = self.get_task_entries(task_id)
        if not entries:
            return f"Task '{goal}' is starting."

        verified = [e for e in entries if e.status == "VERIFIED"]
        active = [e for e in entries if e.status == "ACTIVE"]
        failed = [e for e in entries if e.status == "FAILED"]

        parts = []
        if verified:
            last_verified = verified[-1].step_description
            parts.append(f"I have completed {len(verified)} steps, most recently: {last_verified}.")
        if active:
            parts.append(f"Currently working on: {active[-1].step_description}.")
        if failed:
            parts.append(f"Encountered an issue with {failed[-1].step_description}: {failed[-1].error}. Investigating now.")

        return " ".join(parts) if parts else f"Task is currently in progress."
