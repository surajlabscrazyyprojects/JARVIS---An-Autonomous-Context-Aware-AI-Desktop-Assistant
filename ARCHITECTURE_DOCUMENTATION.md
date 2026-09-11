# JARVIS Three-Model Architecture Documentation

## Overview

JARVIS now operates as a unified system with three specialized models that communicate through shared structured state:

- **Model A (Conversation)**: `qwen3:1.7b` - The voice of JARVIS
- **Model B (Agent)**: `qwen3:4b-instruct-2507-q4_K_M` - The hands of JARVIS
- **Model C (Vision)**: `gemma3:4b` - The eyes of JARVIS

**Core Principle:** MODEL A TALKS. MODEL B WORKS. MODEL C SEES.

The user experiences ONE intelligent assistant, not three competing bots.

---

## Architecture Diagram

```
User Request
    ↓
TaskDispatcher (Request Classification)
    ↓
    ├─ CONVERSATION/QUESTION/TASK_CONTROL → Model A (Conversation)
    │                                          ↓
    │                                    Natural Response
    │                                          ↓
    │                                      User
    │
    ├─ VISUAL_QUERY → Model C (Vision)
    │                      ↓
    │              Structured Vision Data
    │                      ↓
    │                  Model A (Translation)
    │                      ↓
    │              Natural Response
    │                      ↓
    │                  User
    │
    └─ TASK/RESEARCH → Structured Task
                        ↓
                    Model B (Agent)
                        ↓
                    Execution Plan
                        ↓
                    TaskExecutor
                        ↓
                    Verification
                        ↓
                Structured Task Events
                        ↓
                ProgressTranslator
                        ↓
                Model A (Translation)
                        ↓
                Natural Progress Updates
                        ↓
                    User
```

---

## Model Roles

### Model A - Conversation Model (`qwen3:1.7b`)

**Responsibilities:**
- Natural language conversation with the user
- Request classification (via TaskDispatcher)
- Converting structured data to natural language
- Emotional responses and character personality
- Memory management and context tracking

**Prohibitions:**
- Cannot execute tools directly
- Cannot control mouse, keyboard, or terminal
- Cannot launch applications
- Cannot perform computer automation
- Must not behave like an agent

**Communication:**
- Receives: User text, structured vision data, structured task events
- Sends: Natural language responses to user

---

### Model B - Autonomous Agent (`qwen3:4b-instruct-2507-q4_K_M`)

**Responsibilities:**
- Interpreting user intent as goals
- Creating structured execution plans
- Orchestrating computer actions
- Verifying action completion
- Diagnosing and recovering from failures
- Research planning and execution

**Prohibitions:**
- Cannot speak directly to the user
- Cannot provide conversational responses
- Must not behave like a chatbot
- Cannot bypass planning
- Cannot claim success without verification

**Communication:**
- Receives: Structured tasks with goals and context
- Sends: Structured task events (not natural language)

---

### Model C - Vision Model (`gemma3:4b`)

**Responsibilities:**
- Screen analysis and visual perception
- Element detection and extraction
- Error detection on screen
- Layout analysis
- Visual verification support

**Prohibitions:**
- Cannot become a conversational chatbot
- Cannot speak directly to the user
- Must return structured data only

**Communication:**
- Receives: Analysis prompts and screenshots
- Sends: Structured vision data (screen_summary, application, elements, text, errors, layout_issues, confidence)

---

## Request Classification

The TaskDispatcher classifies every user request into one of these categories:

### CONVERSATION
- Greetings, casual conversation
- Small talk, emotional expressions
- Example: "Hey, how are you?"
- Routing: Model A handles directly

### QUESTION
- Informational questions
- General knowledge queries
- Example: "What time is it?"
- Routing: Model A handles directly

### TASK
- Concrete computer actions
- Application control
- File operations
- Example: "Open VS Code", "Create a folder"
- Routing: Structured task → Model B

### RESEARCH
- Information gathering
- Image searches
- Curation requests
- Example: "Find me the best pictures of stars"
- Routing: Structured task with research plan → Model B

### VISUAL_QUERY
- Screen analysis requests
- Visual questions
- Example: "What's on my screen?"
- Routing: Model C → Model A for translation

### TASK_CONTROL
- Cancellation, pausing, resuming
- Example: "Stop", "Cancel"
- Routing: Immediate action, no model needed

### CLARIFICATION
- Ambiguous requests needing clarification
- Example: "Which file?"
- Routing: Model A asks for clarification

### TASK_UPDATE
- Modifying active tasks
- Example: "Change the folder name"
- Routing: Structured task update → Model B

---

## Structured Communication

### Structured Task (Model A → Model B)

```python
{
    "task_id": "uuid",
    "goal": "clear user goal",
    "intent": "underlying intent",
    "priority": "user",
    "context": {
        "original_request": "user's exact words",
        "world_state": {...},
        "classification": "TASK",
        "search_queries": [...],  # for research
        "sources": [...],          # for research
        "evaluation_criteria": [...]  # for research
    },
    "success_criteria": ["action completed", "verified"],
    "constraints": [],
    "metadata": {
        "created_at": timestamp,
        "requires_vision": false,
        "requires_research": false
    }
}
```

### Task Event (Model B → Model A)

```python
{
    "task_id": "uuid",
    "event_type": "TASK_STARTED | STEP_STARTED | ACTION_EXECUTED | VERIFICATION_PASSED | VERIFICATION_FAILED | TASK_REPLANNED | TASK_COMPLETED | TASK_FAILED | TASK_CANCELLED",
    "stage": "current stage name",
    "status": "running | completed | failed",
    "evidence": {...},
    "progress": 0.5,
    "error": "error message if any"
}
```

### Vision Result (Model C → Model A/Model B)

```python
{
    "screen_summary": "brief summary of what is visible",
    "application": "detected application name",
    "elements": [
        {"name": "element name", "type": "button|input|text|menu", "location": [x, y], "confidence": 0.95}
    ],
    "text": ["visible text elements"],
    "errors": ["any visible error messages"],
    "layout_issues": ["any layout problems"],
    "confidence": 0.95
}
```

---

## Shared State Architecture

### TaskState
- Persistent task storage with legal lifecycle transitions
- States: created → planning → awaiting_permission → executing → recovery_required → completed_verified/failed/cancelled
- Checkpoints for recovery
- Artifacts and error tracking
- Resume tokens for crash recovery

### WorldState
- Thread-safe shared state for all models
- Desktop state (active window, running apps, cursor, screen)
- Browser state (URL, title, page text)
- Terminal state (CWD, last command, exit code)
- Vision state (summary, elements, confidence)
- System resources (CPU, RAM, disk)
- Task context (current task, goal, step)

### Memory
- Conversation history and context
- User preferences and learned patterns
- Interaction logs with outcomes

---

## Intelligent Research

The ResearchPlanner transforms research requests into intelligent investigation strategies:

### Example: "Find me the best pictures of stars"

**Old Behavior (WRONG):**
```
browser.search("find me the best pictures of stars")
```

**New Behavior (CORRECT):**
```
1. Interpret goal: "high-quality star images"
2. Create targeted queries:
   - "high quality stars"
   - "stars professional photography"
   - "stars HD images"
   - "best stars"
3. Plan sources:
   - Google Images
   - Specialized image archives
   - Photography portals
4. Define evaluation criteria:
   - High resolution (1920x1080+)
   - Visual impact and composition
   - Relevance to subject
   - Source credibility
   - Uniqueness
5. Execute investigation
6. Curate and rank results
```

---

## Verification Strategy

Every meaningful action must include verification:

### Verification Types
- `process_running` - Verify application is running
- `process_gone` - Verify application is closed
- `file_exists` - Verify file was created
- `directory_exists` - Verify directory exists
- `file_contains` - Verify file content
- `browser_url_loaded` - Verify page loaded
- `terminal_output_contains` - Verify command output
- `active_window_contains` - Verify window title

### Verification Flow
1. Execute action
2. Check verification criteria
3. If verified → success, continue
4. If not verified → retry (up to max_retries)
5. If still not verified → replan
6. If replan fails → report failure

---

## Failure Recovery

### Recovery Process
1. Detect failure (verification failed)
2. Observe current state (including vision analysis)
3. Diagnose root cause
4. Generate alternative plan (repair_plan)
5. Execute recovery steps
6. Verify recovery success
7. If recovery fails → report honest failure

### Recovery Example
```
Step: "Click the Run button"
Verification: Failed (button not found)
Observation: Screen shows "Build" button instead
Diagnosis: Button label is different than expected
Repair: Click the "Build" button instead
```

---

## RAM Governor

The ModelLifecycleManager manages model loading/unloading based on RAM availability:

### Operating Tiers
- **NORMAL**: All models available
- **CAUTION**: Unload idle models
- **CONSTRAINED**: Only conversation model loaded
- **CRITICAL**: Emergency mode, minimal operations

### Model Lifecycle
- **Conversation Model**: Kept warm (-1 keep_alive)
- **Agent Model**: On-demand, 60s idle grace
- **Vision Model**: On-demand, 60s idle grace

### Resource Management
- Automatic RAM pressure evaluation
- Tier selection based on available memory
- Graceful degradation under pressure
- Automatic unloading of idle models

---

## Test Cases

### Test 1: Conversation
**Input:** "Hey, how are you?"
**Expected:** Model A responds naturally. No tools. No agent.
**Verification:** Classification = CONVERSATION, Model A only

### Test 2: Simple Task
**Input:** "Open VS Code."
**Expected:** Model A delegates, Model B opens VS Code with verification, Model A reports naturally.
**Verification:** Classification = TASK, structured task, process_running verification

### Test 3: Vision Query
**Input:** "What's on my screen?"
**Expected:** Model A routes to Model C, Model C analyzes, Model A translates to natural language.
**Verification:** Classification = VISUAL_QUERY, structured vision output

### Test 4: File Operation
**Input:** "Create a folder called TestProject."
**Expected:** Model B creates folder with directory_exists verification.
**Verification:** Classification = TASK, verification passed

### Test 5: Complex Task
**Input:** "Build a coffee shop website."
**Expected:** Model B creates multi-step plan, executes with verification.
**Verification:** Classification = TASK, multiple steps, all verified

### Test 6: Research
**Input:** "Find me the best pictures of stars."
**Expected:** NOT exact sentence search. Intelligent queries, multi-source investigation, curation.
**Verification:** Classification = RESEARCH, intelligent queries, NOT exact sentence

### Test 7: Progress Query
**Input:** (during agent work) "How's it going?"
**Expected:** Model A answers from task state. Agent continues.
**Verification:** Classification = CONVERSATION, task state queried

### Test 8: Cancellation
**Input:** (during agent work) "Stop."
**Expected:** Task cancelled, state persisted, Model A reports naturally.
**Verification:** Classification = TASK_CONTROL, cancellation executed

### Test 9: Vision During Task
**Input:** (during agent work) "Does the website look good?"
**Expected:** Model C analyzes, Model B may use result, Model A explains.
**Verification:** Vision invoked during execution, results integrated

---

## Anti-Regression Checklist

- [x] Browser works reliably
- [x] Agent never bypasses planning
- [x] Conversation model never executes tools
- [x] Agent never speaks directly to user
- [x] Vision called for visual queries
- [x] Vision not called for everything
- [x] Models share structured state
- [x] Browser search not exact sentence
- [x] Task results verified
- [x] Failures trigger recovery
- [x] Verification mandatory
- [x] RAM governor active

---

## File Structure

### New Components
- `jarvis/core/task_dispatcher.py` - Request classification and routing
- `jarvis/core/research_planner.py` - Intelligent research planning
- `jarvis/core/progress_translator.py` - Natural language conversion

### Updated Components
- `jarvis/planner/planner.py` - Autonomous agent prompt
- `jarvis/vision/screen.py` - Structured vision output
- `jarvis/server/websocket_server.py` - Architecture integration
- `jarvis/main.py` - Model configuration

### Existing Components (Leveraged)
- `jarvis/world_state.py` - Shared state management
- `jarvis/runtime/tasks.py` - Task state management
- `jarvis/ai/lifecycle.py` - RAM governor

---

## Configuration

The system requires these model configurations in `jarvis/main.py`:

```python
conversation_model = "qwen3:1.7b"
agent_model = "qwen3:4b-instruct-2507-q4_K_M"
vision_model = "gemma3:4b"
```

These are passed to the JarvisServer and used by the TaskDispatcher.

---

## Acceptance Criteria

### Final Standard
**MODEL A TALKS. MODEL B WORKS. MODEL C SEES.**

### User Experience
- ONE intelligent assistant with natural conversation
- Autonomous execution without robotic dialogue
- Intelligent visual understanding
- Curated research results
- Real computer control with verification
- Persistent memory and context
- Adaptive failure handling

### Architectural Integrity
- Three models communicate through shared structured state
- One responsible conversational voice
- True autonomous agent behavior
- Intelligent visual perception
- Goal-oriented reasoning
- Production-ready pipeline

---

## Conclusion

The JARVIS three-model architecture is now production-ready. All critical architectural deficiencies have been addressed:

1. Strict model role separation
2. One responsible conversational voice
3. Structured inter-model communication
4. Goal-oriented agent reasoning
5. Intelligent research capabilities
6. Proper vision integration
7. Mandatory verification
8. Adaptive failure recovery
9. RAM-aware model lifecycle
10. Shared state architecture

The system operates as ONE JARVIS WITH A VOICE, HANDS, AND EYES.
