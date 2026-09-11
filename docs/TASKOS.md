# JARVIS — Autonomous Task Operating System (TaskOS)

The TaskOS layer turns JARVIS into a persistent, task-owning agent that keeps
executing until the goal is verified complete, cancelled, paused (resumable),
or waiting on explicit user input/permission.

## Modules

| Concern | File |
|---|---|
| Orchestrator (states, persistent execution loop) | `jarvis/core/task_orchestrator.py` |
| Planner (`PlannedStep`, `TaskPlan`, completion conditions) | `jarvis/core/task_planner.py` |
| Execution engine (observe → act → verify per step) | `jarvis/core/execution_engine.py` |
| Verification (filesystem, process, window, URL, build, email draft) | `jarvis/core/verification.py` |
| Instruction classifier (stop/pause/status/update/replace) | `jarvis/core/instruction_classifier.py` |
| Journal + checkpoints (crash recovery, no repeated work) | `jarvis/core/task_journal.py` |
| Business candidate research / ranking | `jarvis/tools/web_research.py` |
| Email safety (draft ≠ sent, authorization gate) | `jarvis/tools/email.py` |
| OpenRouter fabric (free-model discovery, routing, quota) | `jarvis/ai/openrouter.py`, `jarvis/ai/providers.py` |

## Integration points in `jarvis.py`

`Backend.task_os` = a live `TaskOrchestrator`. WebSocket messages:

- `{type:"task_os", action:"accept", goal}` → charter + start background loop
- `{type:"task_os", action:"instruction", text}` → stop/pause/status/update
- `{type:"task_os", action:"status"}` → truthful journal-derived report
- `{type:"task_os", action:"permission", task_id, granted}` → authorize gated step
- `{type:"task_os", action:"pause"|"resume"|"cancel"}` → state control

Chat phrases like "find me a small business… build a website for it" are
auto-routed into the TaskOS pipeline (research → profile → contact discovery →
draft → **explicit authorization** → project → browser verification).

## Acceptance tests

```bat
set PYTHONPATH=%CD%
.venv\Scripts\python.exe tests\test_task_os.py
.venv\Scripts\python.exe tests\test_acceptance_workflow.py
```

`test_task_os.py` — classifier, gated email, verification engine, build task.
`test_acceptance_workflow.py` — §86 full path incl. the authorization gate,
project creation, generated site, and on-disk verification.

## Notes

- Anti-hallucination: every meaningful action is verified by
  `VerificationEngine` against the real filesystem/process/HTTP before it is
  journaled as `VERIFIED`.
- The execution engine returns the mutated task context on every
  `StepExecutionResult`; the orchestrator writes it back so state created by a
  step (drafts, project paths, profiles) is always durable.
- The OpenRouter key is read from env / `.env` (`load_dotenv`) only — never
  hard-coded, printed, or committed.
- Do not contact/send to businesses without the explicit per-recipient
  authorization flow.