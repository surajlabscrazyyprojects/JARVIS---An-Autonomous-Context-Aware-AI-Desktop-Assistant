# NOVA: Next-Generation Omniscient Virtual Assistant
## A Complete Engineering Guide to Building a JARVIS-Class AI System

---

> **Classification:** Proprietary Technical Specification  
> **Version:** 1.0.0  
> **Audience:** Senior Engineering Teams, AI/ML Engineers, System Architects  
> **Document Status:** Final Draft

---

## TABLE OF CONTENTS

1. [Vision, Philosophy & System Overview](#1-vision-philosophy--system-overview)
2. [Complete Feature Catalogue — Fundamental to Advanced](#2-complete-feature-catalogue)
3. [Technical Implementation Deep-Dive](#3-technical-implementation-deep-dive)
4. [System Architecture & Design](#4-system-architecture--design)
5. [PRD, FSD & Tech Stack](#5-prd-fsd--tech-stack)
6. [Agile Development Roadmap](#6-agile-development-roadmap)
7. [Security, Legal & IP Framework](#7-security-legal--ip-framework)
8. [Scalability, Maintainability & Future Expansion](#8-scalability-maintainability--future-expansion)
9. [Setup, Integration & Testing — Step-by-Step](#9-setup-integration--testing)
10. [Appendices](#10-appendices)

---

# 1. VISION, PHILOSOPHY & SYSTEM OVERVIEW

## 1.1 What We Are Building

**NOVA** (Next-generation Omniscient Virtual Assistant) is a fully autonomous, multimodal, always-on AI system that perceives, understands, and interacts with your entire digital environment in real time. Unlike simple voice assistants or chatbots, NOVA operates as a cognitive layer over your operating system — watching your screen, hearing your commands, reading your context, anticipating your needs, and executing multi-step tasks across applications, APIs, and services without hand-holding.

Think of it as Iron Man's JARVIS, but rebuilt from the ground up with 2024–2026 AI capabilities: large language models with 200K+ token context windows, vision models that understand screen content semantically, autonomous agent frameworks that plan and execute multi-step workflows, and a persistent memory system that learns how you think.

## 1.2 Core Design Principles

| Principle | Description |
|-----------|-------------|
| **Proactivity over Reactivity** | NOVA acts before you ask. It monitors context and surfaces relevant assistance without prompting. |
| **Contextual Awareness** | NOVA always knows what application is active, what content is visible, what you worked on yesterday, and what your calendar says next. |
| **Zero-Trust Privacy** | All sensitive processing runs locally. Nothing leaves the machine without explicit permission. |
| **Composable Agent Architecture** | Every capability is a modular agent. Agents can be combined, extended, or replaced independently. |
| **Human-in-the-Loop by Default** | For irreversible actions (delete, send email, deploy code), NOVA requires confirmation unless the user has granted autonomous authority. |
| **Graceful Degradation** | If cloud APIs are offline, NOVA falls back to local models and cached knowledge without crashing. |
| **Explainability** | NOVA explains every action it takes and every recommendation it makes. No black boxes. |

## 1.3 High-Level System Summary

```
┌─────────────────────────────────────────────────────────────┐
│                      USER INTERFACE LAYER                   │
│   Voice   │   Chat/Text   │   HUD Overlay   │   Mobile App  │
└─────────────────────────────────────────────────────────────┘
                             │
┌─────────────────────────────────────────────────────────────┐
│                   PERCEPTION LAYER                          │
│  Screen Capture  │  Audio Input  │  System Events  │  APIs  │
└─────────────────────────────────────────────────────────────┘
                             │
┌─────────────────────────────────────────────────────────────┐
│                   COGNITION LAYER (AI Core)                 │
│  LLM Orchestrator  │  Vision Model  │  Memory Manager      │
│  Intent Parser     │  Context Engine│  Planning Engine     │
└─────────────────────────────────────────────────────────────┘
                             │
┌─────────────────────────────────────────────────────────────┐
│                    EXECUTION LAYER                          │
│  OS Control  │  App Automation  │  API Executor  │  Shell  │
└─────────────────────────────────────────────────────────────┘
                             │
┌─────────────────────────────────────────────────────────────┐
│                    PERSISTENCE LAYER                        │
│  Vector DB   │  SQL DB   │  File Store   │  Event Log      │
└─────────────────────────────────────────────────────────────┘
```

---

# 2. COMPLETE FEATURE CATALOGUE

## 2.1 Tier 1 — Foundational Capabilities

These form the non-negotiable core. Without these, nothing else works.

### F-001: Voice Recognition & Natural Language Understanding

**What it does:** Converts spoken language to text with >97% accuracy and understands intent, entities, and context across multi-turn conversations.

**Key requirements:**
- Wake word detection ("Hey NOVA") with <200ms latency
- Continuous listening with Voice Activity Detection (VAD) to avoid transcribing ambient noise
- Speaker diarization (identifies who is speaking in multi-person setups)
- Accent and dialect robustness
- Technical vocabulary support (code terms, domain jargon)
- Noise suppression in loud environments

### F-002: Text-to-Speech with Personality

**What it does:** Responds in a natural, consistent voice that feels like a character — not a robot.

**Key requirements:**
- Neural TTS with <300ms first-byte latency
- Configurable voice persona (tone, pace, formality)
- Emotional modulation — calm for routine tasks, alert for warnings
- Streaming audio output (starts speaking before full response is generated)
- SSML support for emphasis and pausing

### F-003: Conversational Memory & Context Management

**What it does:** Maintains coherent context across the entire session and across sessions. Remembers that you said "my Python project" two hours ago.

**Key requirements:**
- Short-term context: full conversation window (last 50 turns)
- Long-term memory: semantic search over past interactions
- User preference memory: learns how you like things done
- Entity resolution: "the project" always maps to the right project
- Forgetting mechanism: GDPR-compliant data expiry controls

### F-004: Basic System Control

**What it does:** Controls the operating system — opens apps, manages windows, controls volume, reads files, manages the clipboard.

**Key requirements:**
- Cross-platform OS abstraction layer (macOS, Windows, Linux)
- Application lifecycle management (open, close, focus, minimize)
- File system navigation and manipulation
- Clipboard read/write
- Screenshot and screen region capture on demand
- System settings control (brightness, volume, Wi-Fi, Bluetooth)

### F-005: Calendar, Email & Communication Integration

**What it does:** Reads and writes to Google Calendar, Outlook, Gmail, Slack, and Teams. Schedules meetings, drafts emails, summarizes threads.

**Key requirements:**
- OAuth 2.0 integration with all major providers
- Smart scheduling (finds open slots based on constraints: "schedule 90 minutes with Ahmed next week, not before 10am")
- Email drafting with tone control (formal, casual, urgent)
- Thread summarization ("what's the status of the Acme project from Slack?")
- Notification management — surface important things, suppress noise

### F-006: Web Search & Information Retrieval

**What it does:** Searches the web, reads pages, synthesizes information, and cites sources.

**Key requirements:**
- Multi-engine search (Google, Bing, DuckDuckGo, Perplexity)
- Web page reading with JavaScript rendering support
- Fact verification against multiple sources
- Research mode: follows chains of links to build deep understanding
- Citation generation in APA, MLA, or custom format

---

## 2.2 Tier 2 — Intelligent Capabilities

These transform NOVA from a voice assistant into a thinking system.

### F-007: Real-Time Screen Analysis Engine

**What it does:** Continuously captures and semantically understands your screen — identifies applications, content, UI elements, code, documents, and their meaning.

**Key requirements:**
- Configurable capture rate (default: 2fps, can spike to 30fps on activity)
- Semantic segmentation: "There's a Python file open, line 47 has a bug"
- OCR with structure understanding (tables, forms, code blocks)
- UI element detection: buttons, fields, menus — NOVA can click them
- Privacy zones: user-defined regions that are never captured
- Diff detection: only analyze when screen content changes meaningfully

### F-008: Proactive Intelligence Engine

**What it does:** Watches your context and surfaces relevant actions without being asked.

**Examples:**
- Detects you've been on the same bug for 30 minutes → suggests approach
- Sees a meeting in 10 minutes → prepares a brief on attendees from your email history
- Notices a git conflict in your IDE → explains the conflict and proposes a merge strategy
- Sees a high-priority email → interrupts appropriately to surface it

**Key requirements:**
- Attention scoring: ranks proactive suggestions by relevance and urgency
- Non-interruptive UI: suggestions appear as subtle overlays, not popups
- Configurable verbosity: "focused mode" suppresses all proactive suggestions
- Learning loop: user feedback trains the relevance model

### F-009: Autonomous Multi-Step Task Execution

**What it does:** Given a high-level goal, plans and executes a sequence of actions across multiple tools and applications.

**Example:** "NOVA, prepare the quarterly board report"
- Pulls revenue data from Salesforce
- Gets headcount from HR system
- Pulls last quarter's report from Google Drive for structure reference
- Writes the new report
- Creates slides in PowerPoint
- Emails draft to CFO for review

**Key requirements:**
- Goal decomposition with dependency resolution
- Parallel execution where possible
- Checkpoint and rollback: if step 4 fails, doesn't leave system in broken state
- Progress narration: tells you what it's doing in plain language
- Human confirmation gates for irreversible steps

### F-010: Code Intelligence & Engineering Assistant

**What it does:** Understands your codebase, writes code, reviews PRs, explains errors, and navigates repositories.

**Key requirements:**
- Deep codebase indexing via AST (Abstract Syntax Tree) parsing
- Language support: Python, JavaScript/TypeScript, Rust, Go, Java, C++, SQL, and more
- IDE integration: VS Code, JetBrains, Vim/Neovim via LSP
- Test generation with coverage targets
- Security vulnerability scanning (OWASP Top 10)
- Architectural review: "explain why this service is slow"
- Git integration: commit history analysis, PR description generation

### F-011: System Monitoring & Self-Healing

**What it does:** Monitors CPU, memory, disk, network, running processes, and logs. Detects anomalies and remediates automatically.

**Key requirements:**
- Real-time metrics with configurable alert thresholds
- Log aggregation and anomaly detection (ML-based)
- Process management: kill runaway processes, restart crashed services
- Disk space management: identify and clean up safely
- Network diagnostics: identify bandwidth hogs, broken connections
- Predictive alerts: "Disk will fill in ~4 hours at current rate"

### F-012: File Intelligence & Document Management

**What it does:** Understands the content of your files — not just names. Can find, organize, summarize, compare, and transform documents.

**Key requirements:**
- Semantic file search: "find the Q3 budget with the conservative assumptions"
- Document summarization (PDF, DOCX, PPTX, XLSX, images)
- Cross-document analysis: "how has our pricing changed across these three proposals?"
- Automatic organization suggestions
- Duplicate detection
- Format conversion (e.g., PDF to structured data)

---

## 2.3 Tier 3 — Advanced & Autonomous Capabilities

These give NOVA genuine agency over complex, high-stakes work.

### F-013: Multi-Agent Orchestration

**What it does:** Spawns, coordinates, and synthesizes results from multiple specialized sub-agents running in parallel.

**Architecture:** A Supervisor Agent receives a goal and delegates to:
- Research Agent (web search + knowledge retrieval)
- Code Agent (writing, testing, executing code)
- Communication Agent (emails, Slack messages)
- Data Agent (database queries, analytics)
- File Agent (document creation and management)

**Key requirements:**
- Agent registry with capability declarations
- Inter-agent message passing via structured protocol
- Conflict resolution when agents disagree
- Cost management: controls API spend across agents
- Timeout and retry logic per agent

### F-014: Computer Vision & GUI Automation

**What it does:** NOVA can literally see and operate any application, even those with no API, by understanding the GUI and controlling mouse/keyboard.

**Key requirements:**
- Element detection via vision model (not brittle CSS selectors)
- Action planning: "to submit this form, I need to fill fields A, B, C then click Submit"
- Verification after each action: confirms the expected state change occurred
- Error recovery: if click missed, re-centers and retries
- Recording mode: watches user actions to learn new workflows
- Cross-platform automation: macOS Accessibility API, Windows UI Automation, X11/AT-SPI

### F-015: Behavioral Learning & Personalization

**What it does:** Builds a deep model of your work patterns, preferences, and communication style. Gets smarter the more you use it.

**Learning dimensions:**
- Work schedule patterns (peak focus hours, meeting habits)
- Communication style (tone, vocabulary, formality per recipient)
- Task patterns (how you approach debugging, how you structure documents)
- Application preferences (keyboard shortcuts you use, UI preferences)
- Decision patterns (how you make technical tradeoffs)

**Key requirements:**
- On-device federated learning — model updates stay local
- Explicit teaching mode: "NOVA, remember that I always want test files in `__tests__/`"
- Preference dashboard: full visibility and control over learned behaviors
- Privacy-preserving: never sends behavioral data to cloud

### F-016: Security Intelligence & Threat Detection

**What it does:** Monitors your system for security threats, suspicious activity, data exposure, and policy violations.

**Key requirements:**
- File access monitoring: alerts on unexpected access to sensitive directories
- Network traffic analysis: detects unusual outbound connections
- Credential scanning: finds hardcoded secrets in code before they're committed
- Phishing detection: evaluates links and emails for social engineering
- Software vulnerability alerting: cross-references installed packages with CVE database
- Incident response playbook execution

### F-017: API Integration Hub

**What it does:** Connects NOVA to any external service via REST, GraphQL, or gRPC without custom code per integration.

**Key requirements:**
- OpenAPI spec parser: given a swagger file, NOVA can use the API
- Authentication management: handles OAuth, API keys, JWT securely
- Rate limit management and retry logic
- Response caching
- Integration marketplace: pre-built connectors for 100+ common services
- Custom connector builder with NOVA's assistance

### F-018: Predictive Task Management

**What it does:** Tracks your projects, deadlines, and priorities. Proactively manages your workload.

**Key requirements:**
- Natural language task capture from conversation
- Deadline inference: "before the board meeting" → maps to calendar event
- Priority scoring based on deadlines, stakeholder importance, and dependencies
- Daily brief: morning summary of what matters today and why
- Workload forecasting: "you have 6 hours of committed work, 2 hours buffer — reschedule or delegate?"
- Integration with Jira, Linear, Notion, Asana, Trello

### F-019: Knowledge Base & Second Brain

**What it does:** Builds and maintains a personal knowledge base from everything you read, write, say, and do.

**Key requirements:**
- Automatic knowledge capture from web pages, documents, conversations
- Knowledge graph construction: entities, relationships, concepts
- Semantic search across all captured knowledge
- Automatic linking: "this article relates to that research you saved in March"
- Export to Notion, Obsidian, Roam Research
- Spaced repetition prompts for important knowledge

### F-020: Voice & Visual HUD Overlay

**What it does:** Provides a non-intrusive heads-up display that overlays information on your screen without interrupting your workflow.

**Key requirements:**
- Transparent overlay window (always-on-top, non-blocking)
- Status indicators: NOVA's attention state, active agents, pending tasks
- Contextual info cards: surfaces relevant info as you work
- Voice waveform visualization during speech
- Collapsible sidebar with conversation history
- Dark/light modes with full theme customization

---

# 3. TECHNICAL IMPLEMENTATION DEEP-DIVE

## 3.1 Core Language & Framework Decisions

### Primary Language: Python 3.11+

Python is the backbone because:
- Richest AI/ML ecosystem (PyTorch, HuggingFace, LangChain)
- AsyncIO for concurrent agent execution
- Excellent system access libraries (psutil, subprocess, pyautogui)
- Fast prototyping with production-grade performance when optimized

**Critical Python libraries by domain:**

```
AI & LLM Orchestration:
  langchain==0.3.x         # Agent framework
  langgraph==0.2.x         # Stateful multi-agent graphs
  anthropic==0.37.x        # Claude API
  openai==1.50.x           # GPT-4 / Whisper API
  litellm==1.50.x          # Unified LLM API (model agnostic)

Vision & Screen Analysis:
  pillow==10.x             # Image processing
  pytesseract==0.3.x       # OCR engine wrapper
  easyocr==1.7.x           # Neural OCR (better accuracy)
  anthropic (vision)       # Claude-3.5 Sonnet for screen understanding
  
Audio Processing:
  faster-whisper==1.0.x    # Local STT (OpenAI Whisper, fast)
  pyaudio==0.2.x           # Audio capture
  webrtcvad==2.0.x         # Voice Activity Detection
  piper-tts==1.2.x         # Local neural TTS
  elevenlabs==1.0.x        # Cloud TTS (high quality)

System Control:
  pyautogui==0.9.x         # Mouse/keyboard control
  pynput==1.7.x            # Low-level input events
  psutil==5.9.x            # System metrics
  watchdog==4.0.x          # File system monitoring
  dbus-python==1.3.x       # Linux D-Bus integration

Data & Memory:
  chromadb==0.5.x          # Local vector database
  sqlalchemy==2.0.x        # SQL ORM
  redis==5.0.x             # Cache and message bus
  pydantic==2.8.x          # Data validation
  
Web & APIs:
  fastapi==0.115.x         # REST API server
  httpx==0.27.x            # Async HTTP client
  playwright==1.47.x       # Browser automation
  beautifulsoup4==4.12.x   # HTML parsing
```

### Secondary Language: TypeScript (Node.js 20+)

Used for the desktop application shell (Electron) and frontend overlay:

```
electron==31.x             # Desktop app framework
react==18.x                # UI library
tailwindcss==3.x           # Styling
zustand==5.x               # State management
socket.io-client==4.x      # Real-time backend communication
framer-motion==11.x        # Smooth animations for HUD
```

### System-Level: Rust

Performance-critical components written in Rust with Python bindings via PyO3:
- Screen capture daemon (60fps-capable, minimal CPU overhead)
- Audio ring buffer and VAD processing
- Cryptographic operations for local data encryption

### Why Not Fully Local?

The architecture supports **both local and cloud** inference, switchable per request:

| Task | Local Model | Cloud Model |
|------|------------|-------------|
| Wake word detection | ✅ Always local | — |
| STT (speech-to-text) | ✅ Faster-Whisper | OpenAI Whisper API |
| General conversation | Ollama + Llama 3.1 70B | Claude 3.5 Sonnet |
| Screen understanding | LLaVA-1.6 (7B) | Claude 3.5 Sonnet Vision |
| Code generation | DeepSeek-Coder-V2 | GPT-4o / Claude 3.5 |
| Document OCR | EasyOCR (local) | — |
| TTS | Piper TTS | ElevenLabs |

---

## 3.2 Voice Recognition Implementation

### Architecture

```
Microphone → PyAudio Ring Buffer → WebRTC VAD → Porcupine Wake Word
                                                       │
                                               Wake Word Detected
                                                       │
                                    ┌──────────────────┴──────────────────┐
                                    │        Faster-Whisper STT           │
                                    │  (large-v3, float16, CUDA/MPS)     │
                                    └──────────────────┬──────────────────┘
                                                       │
                                              Transcript Text
                                                       │
                                          NLU + Intent Classification
```

### Wake Word Detection

```python
# wake_word_engine.py
import pvporcupine
import pyaudio
import numpy as np
from typing import Callable

class WakeWordDetector:
    """
    Uses Picovoice Porcupine for ultra-low-latency wake word detection.
    Runs entirely on CPU, <5% utilization, <50MB RAM.
    """
    
    def __init__(
        self, 
        access_key: str,
        wake_word: str = "nova",  # Custom wake word or built-in
        sensitivity: float = 0.7,
        on_detection: Callable = None
    ):
        self.porcupine = pvporcupine.create(
            access_key=access_key,
            keywords=[wake_word],
            sensitivities=[sensitivity]
        )
        self.on_detection = on_detection
        self._audio = pyaudio.PyAudio()
        self._stream = None
        
    def start(self):
        """Begin continuous wake word monitoring."""
        self._stream = self._audio.open(
            rate=self.porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.porcupine.frame_length,
            stream_callback=self._audio_callback
        )
        self._stream.start_stream()
        
    def _audio_callback(self, in_data, frame_count, time_info, status):
        pcm = np.frombuffer(in_data, dtype=np.int16)
        result = self.porcupine.process(pcm)
        if result >= 0 and self.on_detection:
            self.on_detection()
        return (in_data, pyaudio.paContinue)
```

### Continuous Speech Transcription

```python
# transcription_engine.py
from faster_whisper import WhisperModel
import webrtcvad
import numpy as np
from collections import deque

class TranscriptionEngine:
    """
    Transcribes speech after wake word detection.
    Uses faster-whisper (CTranslate2 backend) for 4-8x speedup vs original.
    Supports: CUDA, ROCm, MPS (Apple Silicon), CPU fallback.
    """
    
    def __init__(self, model_size: str = "large-v3", device: str = "auto"):
        # Auto-detect best available compute device
        if device == "auto":
            device = self._detect_device()
            
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type="float16" if device != "cpu" else "int8",
            num_workers=2
        )
        self.vad = webrtcvad.Vad(aggressiveness=2)  # 0-3, 3 = most aggressive
        self.sample_rate = 16000
        self.frame_duration_ms = 30  # 10, 20, or 30 ms
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)
        
    def _detect_device(self) -> str:
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            elif torch.backends.mps.is_available():
                return "mps"  # Apple Silicon
        except ImportError:
            pass
        return "cpu"
        
    def transcribe_stream(self, audio_frames: list[bytes]) -> str:
        """
        Transcribes buffered audio with Voice Activity Detection filtering.
        Only processes frames where speech is detected.
        """
        voiced_frames = []
        for frame in audio_frames:
            if len(frame) == self.frame_size * 2:  # 16-bit samples
                if self.vad.is_speech(frame, self.sample_rate):
                    voiced_frames.append(frame)
        
        if not voiced_frames:
            return ""
            
        # Combine voiced frames into numpy array
        audio_data = np.frombuffer(b"".join(voiced_frames), dtype=np.int16)
        audio_float = audio_data.astype(np.float32) / 32768.0
        
        # Transcribe with word-level timestamps
        segments, info = self.model.transcribe(
            audio_float,
            beam_size=5,
            language="en",  # Or auto-detect: language=None
            condition_on_previous_text=True,
            word_timestamps=True,
            vad_filter=True
        )
        
        full_transcript = " ".join(seg.text.strip() for seg in segments)
        return full_transcript
```

---

## 3.3 Screen Analysis Engine

This is the most technically complex component. Getting it right is what separates NOVA from a basic assistant.

### Capture Pipeline

```python
# screen_capture.py
import mss
import numpy as np
from PIL import Image
import asyncio
from dataclasses import dataclass

@dataclass
class ScreenFrame:
    image: Image.Image
    timestamp: float
    resolution: tuple[int, int]
    active_app: str
    changed: bool  # Whether this frame differs significantly from previous

class ScreenCaptureEngine:
    """
    Efficient screen capture with intelligent change detection.
    Uses MSS (Multi-Screen Shot) for cross-platform capture.
    Implements perceptual hashing for change detection.
    """
    
    def __init__(self, fps: float = 2.0, change_threshold: float = 0.05):
        self.fps = fps
        self.change_threshold = change_threshold  # 5% pixel change = significant
        self._previous_hash = None
        self._sct = mss.mss()
        
    async def capture_loop(self, on_frame_callback):
        """
        Async capture loop. Fires callback only on significant changes.
        Spikes to 30fps during high-activity detection (mouse movement, typing).
        """
        interval = 1.0 / self.fps
        while True:
            frame = await self._capture_frame()
            if frame.changed:
                await on_frame_callback(frame)
            await asyncio.sleep(interval)
            
    async def _capture_frame(self) -> ScreenFrame:
        # Capture primary monitor
        screenshot = self._sct.grab(self._sct.monitors[1])
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        
        # Perceptual hash for change detection
        img_small = img.resize((32, 32), Image.LANCZOS).convert("L")
        pixels = np.array(img_small).flatten()
        current_hash = (pixels > pixels.mean()).tobytes()
        
        changed = (self._previous_hash is None or 
                  self._hamming_distance(current_hash, self._previous_hash) 
                  > self.change_threshold * 1024)
        self._previous_hash = current_hash
        
        return ScreenFrame(
            image=img,
            timestamp=asyncio.get_event_loop().time(),
            resolution=img.size,
            active_app=self._get_active_app(),
            changed=changed
        )
        
    def _hamming_distance(self, hash1: bytes, hash2: bytes) -> int:
        return sum(bin(b1 ^ b2).count("1") for b1, b2 in zip(hash1, hash2))
        
    def _get_active_app(self) -> str:
        """Cross-platform active application detection."""
        import platform
        if platform.system() == "Darwin":
            from AppKit import NSWorkspace
            return NSWorkspace.sharedWorkspace().frontmostApplication().localizedName()
        elif platform.system() == "Windows":
            import win32gui, win32process
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            import psutil
            return psutil.Process(pid).name()
        else:  # Linux
            import subprocess
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True
            )
            return result.stdout.strip()
```

### Vision AI Analysis

```python
# screen_analyzer.py
import anthropic
import base64
from io import BytesIO
from PIL import Image

class ScreenAnalyzer:
    """
    Uses Claude Vision (or local LLaVA) to semantically understand screen content.
    Returns structured analysis: active task, visible content, UI state, anomalies.
    """
    
    ANALYSIS_PROMPT = """
    You are an expert screen analyzer for NOVA, an AI assistant.
    
    Analyze this screenshot and return a JSON object with:
    {
        "active_app": "Name of the frontmost application",
        "active_task": "What the user appears to be working on",
        "visible_content_summary": "1-2 sentence summary of what's on screen",
        "ui_elements": ["list of interactive UI elements visible"],
        "code_visible": true/false,
        "code_language": "programming language if code is visible, else null",
        "errors_visible": "description of any error messages, null if none",
        "text_content": "key text content visible on screen",
        "suggested_actions": ["0-3 proactive actions NOVA could take"],
        "urgency": "low/medium/high - how urgent is proactive assistance?"
    }
    
    Be precise. Be brief. Return ONLY valid JSON.
    """
    
    def __init__(self, use_cloud: bool = True):
        self.use_cloud = use_cloud
        if use_cloud:
            self.client = anthropic.Anthropic()
        else:
            # Local LLaVA via Ollama
            import ollama
            self.ollama = ollama
            
    async def analyze(self, frame: "ScreenFrame") -> dict:
        if self.use_cloud:
            return await self._analyze_with_claude(frame)
        else:
            return await self._analyze_with_llava(frame)
            
    async def _analyze_with_claude(self, frame) -> dict:
        # Compress image for API efficiency
        img_compressed = frame.image.copy()
        img_compressed.thumbnail((1920, 1080), Image.LANCZOS)
        
        buffer = BytesIO()
        img_compressed.save(buffer, format="JPEG", quality=85)
        img_b64 = base64.standard_b64encode(buffer.getvalue()).decode()
        
        message = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": img_b64
                        }
                    },
                    {"type": "text", "text": self.ANALYSIS_PROMPT}
                ]
            }]
        )
        
        import json
        return json.loads(message.content[0].text)
```

---

## 3.4 LLM Orchestration & Agent Framework

### The Brain: LangGraph Multi-Agent System

```python
# agent_graph.py
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from typing import TypedDict, Annotated
import operator

class AgentState(TypedDict):
    """The state passed between all agents in the graph."""
    messages: Annotated[list, operator.add]  # Conversation history
    screen_context: dict                      # Current screen analysis
    user_intent: str                          # Parsed user goal
    active_agents: list[str]                  # Currently running sub-agents
    task_plan: list[dict]                     # Planned steps
    completed_steps: list[dict]               # Executed steps + results
    requires_confirmation: bool               # Waiting for user approval
    final_response: str                       # Response to speak/display

class NOVAOrchestrator:
    """
    Supervisor agent that routes between specialized sub-agents.
    Built on LangGraph for stateful, cyclical agent execution.
    """
    
    def __init__(self, llm, tools_registry):
        self.llm = llm
        self.tools_registry = tools_registry
        self.graph = self._build_graph()
        
    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)
        
        # Add all nodes (agents)
        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("planner", self._planner_node)
        workflow.add_node("code_agent", self._code_agent_node)
        workflow.add_node("research_agent", self._research_agent_node)
        workflow.add_node("file_agent", self._file_agent_node)
        workflow.add_node("system_agent", self._system_agent_node)
        workflow.add_node("communication_agent", self._communication_agent_node)
        workflow.add_node("confirm_action", self._confirm_action_node)
        workflow.add_node("executor", self._executor_node)
        workflow.add_node("responder", self._responder_node)
        
        # Entry point
        workflow.set_entry_point("supervisor")
        
        # Routing logic
        workflow.add_conditional_edges(
            "supervisor",
            self._route_from_supervisor,
            {
                "plan": "planner",
                "code": "code_agent", 
                "research": "research_agent",
                "file": "file_agent",
                "system": "system_agent",
                "communicate": "communication_agent",
                "respond": "responder",
                "end": END
            }
        )
        
        workflow.add_conditional_edges(
            "planner",
            self._route_from_planner,
            {
                "execute": "executor",
                "confirm": "confirm_action"
            }
        )
        
        workflow.add_edge("executor", "supervisor")
        workflow.add_edge("confirm_action", "executor")
        
        return workflow.compile()
        
    async def _supervisor_node(self, state: AgentState) -> AgentState:
        """
        Master routing agent. Analyzes intent, screen context, and decides
        which specialist agent to invoke or whether to respond directly.
        """
        system_prompt = f"""
        You are NOVA's supervisor. Your role is to analyze what the user wants,
        understand the current computer context, and route to the right specialist.
        
        Current screen context: {state.get('screen_context', {})}
        
        Routing options:
        - "plan": Complex multi-step task requiring planning
        - "code": Anything involving writing/analyzing/running code
        - "research": Web search, fact-finding, information gathering
        - "file": File operations, document creation, organization
        - "system": System control, monitoring, settings
        - "communicate": Email, Slack, calendar, meetings
        - "respond": Simple Q&A, can answer directly from knowledge
        - "end": Conversation complete, no further action needed
        
        Return ONLY the routing key and a brief reasoning.
        """
        
        response = await self.llm.ainvoke(
            [{"role": "system", "content": system_prompt}] + state["messages"]
        )
        
        # Parse routing decision and update state
        # ... (routing logic)
        return state
```

---

## 3.5 Memory System Architecture

```
Memory Architecture:

┌─────────────────────────────────────────────────────────────┐
│                    WORKING MEMORY                           │
│   Current conversation (last 50 turns)                     │
│   Active task state                                         │
│   Current screen context                                    │
│   Redis — in-memory, sub-millisecond access                │
└─────────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────────┐
│                  EPISODIC MEMORY                            │
│   Past conversations (semantic search)                      │
│   Events and actions taken                                  │
│   ChromaDB — vector embeddings, cosine similarity search   │
│   Retention: 90 days default (configurable)                │
└─────────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────────┐
│                   SEMANTIC MEMORY                           │
│   Facts about the user, their projects, preferences        │
│   Knowledge graph (entities + relationships)               │
│   PostgreSQL (structured) + ChromaDB (semantic)            │
│   Retention: Permanent (until explicitly deleted)          │
└─────────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────────┐
│                  PROCEDURAL MEMORY                          │
│   Learned workflows and task templates                      │
│   Automation scripts NOVA has generated                     │
│   SQLite + Python pickle for workflows                     │
│   Retention: Permanent                                      │
└─────────────────────────────────────────────────────────────┘
```

```python
# memory_manager.py
import chromadb
from chromadb.utils import embedding_functions
import redis
import json
from datetime import datetime
from typing import Optional

class MemoryManager:
    """
    Unified interface over all memory tiers.
    Automatically routes writes and reads to the appropriate store.
    """
    
    def __init__(self):
        # Working memory: Redis
        self.redis = redis.Redis(host="localhost", port=6379, decode_responses=True)
        self.session_ttl = 3600  # 1 hour session TTL
        
        # Episodic + Semantic memory: ChromaDB
        self.chroma = chromadb.PersistentClient(path="~/.nova/memory/chroma")
        self.embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"  # Runs fully locally
        )
        
        self.episodes = self.chroma.get_or_create_collection(
            name="episodes",
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"}
        )
        
        self.facts = self.chroma.get_or_create_collection(
            name="facts",
            embedding_function=self.embed_fn
        )
        
    def remember_conversation_turn(
        self, 
        user_msg: str, 
        assistant_msg: str,
        session_id: str,
        screen_context: dict = None
    ):
        """Store a conversation exchange in both working and episodic memory."""
        turn = {
            "user": user_msg,
            "assistant": assistant_msg,
            "timestamp": datetime.utcnow().isoformat(),
            "screen_context": screen_context or {}
        }
        
        # Working memory: append to session history
        self.redis.rpush(f"session:{session_id}:history", json.dumps(turn))
        self.redis.expire(f"session:{session_id}:history", self.session_ttl)
        
        # Episodic memory: embed and store for semantic search
        episode_text = f"User: {user_msg}\nNOVA: {assistant_msg}"
        self.episodes.add(
            documents=[episode_text],
            ids=[f"{session_id}-{datetime.utcnow().timestamp()}"],
            metadatas=[{"timestamp": turn["timestamp"], "session": session_id}]
        )
        
    def remember_fact(self, fact: str, category: str, confidence: float = 1.0):
        """Store a learned fact about the user or their environment."""
        self.facts.add(
            documents=[fact],
            ids=[f"fact-{datetime.utcnow().timestamp()}"],
            metadatas=[{
                "category": category,
                "confidence": confidence,
                "created": datetime.utcnow().isoformat()
            }]
        )
        
    def recall(self, query: str, n_results: int = 5) -> list[dict]:
        """
        Semantic search across episodic and factual memory.
        Returns most relevant past context for the current query.
        """
        episode_results = self.episodes.query(
            query_texts=[query],
            n_results=n_results
        )
        fact_results = self.facts.query(
            query_texts=[query],
            n_results=n_results
        )
        
        # Merge and rank by relevance
        memories = []
        for doc, meta, dist in zip(
            episode_results["documents"][0],
            episode_results["metadatas"][0],
            episode_results["distances"][0]
        ):
            memories.append({"type": "episode", "content": doc, 
                           "relevance": 1 - dist, "metadata": meta})
                           
        for doc, meta, dist in zip(
            fact_results["documents"][0],
            fact_results["metadatas"][0],
            fact_results["distances"][0]
        ):
            memories.append({"type": "fact", "content": doc, 
                           "relevance": 1 - dist, "metadata": meta})
        
        return sorted(memories, key=lambda x: x["relevance"], reverse=True)
        
    def get_session_history(self, session_id: str) -> list[dict]:
        """Retrieve full working memory for current session."""
        history = self.redis.lrange(f"session:{session_id}:history", 0, -1)
        return [json.loads(h) for h in history]
```

---

## 3.6 GUI Automation Engine

```python
# gui_automation.py
import pyautogui
import platform
from dataclasses import dataclass
from typing import Optional

@dataclass  
class UIElement:
    label: str
    element_type: str  # button, textfield, dropdown, etc.
    bounds: tuple[int, int, int, int]  # x, y, width, height
    confidence: float

class GUIAutomationEngine:
    """
    Executes GUI actions (click, type, scroll, drag) based on
    visual element detection. Uses PyAutoGUI with accessibility API fallback.
    """
    
    def __init__(self, screen_analyzer: "ScreenAnalyzer"):
        self.screen = screen_analyzer
        pyautogui.PAUSE = 0.1  # 100ms between actions
        pyautogui.FAILSAFE = True  # Move to corner to abort
        
    async def click_element(
        self, 
        element_description: str,
        screenshot=None
    ) -> bool:
        """
        Find and click a UI element described in natural language.
        Example: click_element("the Submit button")
        """
        if screenshot is None:
            import mss
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
        
        # Ask vision model to locate the element
        location_prompt = f"""
        In this screenshot, find: "{element_description}"
        Return ONLY a JSON object:
        {{
            "found": true/false,
            "x": pixel_x_coordinate_of_center,
            "y": pixel_y_coordinate_of_center,
            "confidence": 0.0_to_1.0
        }}
        """
        
        location = await self.screen.analyze_with_prompt(screenshot, location_prompt)
        
        if location.get("found") and location.get("confidence", 0) > 0.8:
            x, y = location["x"], location["y"]
            pyautogui.moveTo(x, y, duration=0.3)
            pyautogui.click()
            return True
        return False
        
    async def type_in_field(self, field_description: str, text: str):
        """Find a text field and type into it."""
        clicked = await self.click_element(field_description)
        if clicked:
            pyautogui.hotkey("ctrl", "a")  # Select all existing content
            pyautogui.typewrite(text, interval=0.05)
            
    async def execute_plan(self, action_plan: list[dict]) -> list[dict]:
        """
        Execute a sequence of GUI actions.
        Each action: {"type": "click|type|scroll|hotkey", "target": "...", "value": "..."}
        """
        results = []
        for action in action_plan:
            result = {"action": action, "success": False}
            try:
                if action["type"] == "click":
                    result["success"] = await self.click_element(action["target"])
                elif action["type"] == "type":
                    await self.type_in_field(action["target"], action["value"])
                    result["success"] = True
                elif action["type"] == "hotkey":
                    pyautogui.hotkey(*action["keys"].split("+"))
                    result["success"] = True
                elif action["type"] == "scroll":
                    pyautogui.scroll(action.get("amount", 3))
                    result["success"] = True
            except Exception as e:
                result["error"] = str(e)
            results.append(result)
        return results
```

---

# 4. SYSTEM ARCHITECTURE & DESIGN

## 4.1 Full Component Architecture

```
                          ╔══════════════════════════════════════╗
                          ║         NOVA SYSTEM ARCHITECTURE     ║
                          ╚══════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                               │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │  Electron    │  │  Mobile App  │  │  CLI Client  │             │
│  │  Desktop     │  │  (iOS/Droid) │  │  (Power user)│             │
│  │  (HUD+Chat)  │  │              │  │              │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
└─────────┼─────────────────┼─────────────────┼───────────────────┘
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │ WebSocket + REST
┌─────────────────────────────────────────────────────────────────────┐
│                        API GATEWAY LAYER                            │
│              FastAPI  ·  Nginx Reverse Proxy  ·  SSL/TLS            │
│              Rate Limiting  ·  Auth (JWT)  ·  Request Routing       │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────────────┐
│                    EVENT BUS (Redis Pub/Sub)                        │
│     screen.changed  │  voice.detected  │  task.created  │  alert   │
└─────────────────────┬───────────────────────────────────────────────┘
         ┌────────────┼────────────┬────────────────┬─────────────────┐
         ▼            ▼            ▼                ▼                 ▼
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌─────────────┐
│  Voice     │ │  Screen    │ │   NOVA     │ │ System   │ │  Security   │
│  Service   │ │  Analysis  │ │   Brain    │ │ Monitor  │ │  Scanner    │
│            │ │  Service   │ │  Service   │ │ Service  │ │  Service    │
│ STT + TTS  │ │            │ │            │ │          │ │             │
│ Wake Word  │ │ Capture    │ │ LangGraph  │ │ psutil   │ │ File watch  │
│ VAD        │ │ Vision AI  │ │ Agents     │ │ Metrics  │ │ Net monitor │
│ Speaker ID │ │ OCR        │ │ Memory     │ │ Alerts   │ │ CVE scan    │
└────────────┘ └────────────┘ └─────┬──────┘ └──────────┘ └─────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌───────────┐  ┌───────────────┐  ┌──────────┐
            │  Tool     │  │   External    │  │  Local   │
            │  Executor │  │   API Hub     │  │  Models  │
            │           │  │               │  │          │
            │ OS Ctrl   │  │ Google APIs   │  │ LLaMA    │
            │ GUI Auto  │  │ Slack/Teams   │  │ Whisper  │
            │ Shell Cmd │  │ Jira/Linear   │  │ LLaVA    │
            │ Browser   │  │ Salesforce    │  │ Piper    │
            └───────────┘  └───────────────┘  └──────────┘
                    │
┌─────────────────────────────────────────────────────────────────────┐
│                      PERSISTENCE LAYER                              │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │  Redis       │  │  PostgreSQL  │  │  ChromaDB    │             │
│  │  (working    │  │  (structured │  │  (vector DB  │             │
│  │   memory,    │  │   data:      │  │   for        │             │
│  │   cache,     │  │   tasks,     │  │   semantic   │             │
│  │   pub/sub)   │  │   users,     │  │   memory,    │             │
│  │              │  │   configs)   │  │   knowledge) │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐                               │
│  │  Local FS    │  │  SQLite      │                               │
│  │  (~/.nova/)  │  │  (device     │                               │
│  │  (models,    │  │   prefs,     │                               │
│  │   recordings,│  │   workflows, │                               │
│  │   exports)   │  │   local log) │                               │
│  └──────────────┘  └──────────────┘                               │
└─────────────────────────────────────────────────────────────────────┘
```

## 4.2 Data Flow: Voice Command Lifecycle

```
User speaks: "NOVA, what's in my inbox from Ahmed today?"

    1. [Wake Word Engine] "NOVA" detected → triggers STT
    2. [STT Engine] "what's in my inbox from Ahmed today?" → transcript
    3. [NLU] Intent: FETCH_EMAILS, Entity: {sender: "Ahmed", timeframe: "today"}
    4. [Memory] Recall: "Ahmed = Ahmed Al-Rashid, VP Engineering, ahmed@company.com"
    5. [Supervisor Agent] Route → Communication Agent
    6. [Communication Agent] 
         → Gmail API: search(from: ahmed@company.com, after: today)
         → Returns: 3 threads found
    7. [LLM] Synthesize response: "Ahmed sent you 3 emails today..."
    8. [TTS] Speak response
    9. [Memory] Log interaction, update episodic memory
   10. [HUD] Display email summaries as visual cards

Total latency target: < 2 seconds (voice in → voice out)
```

## 4.3 Microservices Communication

All services communicate via:
- **Async events:** Redis Pub/Sub for real-time events (screen changes, voice detected)
- **REST API:** FastAPI for request/response interactions (tasks, queries)
- **WebSocket:** For streaming responses to the frontend (TTS audio, partial text)

```yaml
# docker-compose.yml (development)
version: "3.9"

services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: ["redis_data:/data"]
    
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: nova
      POSTGRES_USER: nova
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: ["postgres_data:/var/lib/postgresql/data"]
    
  nova-brain:
    build: ./services/brain
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=postgresql://nova:${POSTGRES_PASSWORD}@postgres/nova
    depends_on: [redis, postgres]
    
  nova-voice:
    build: ./services/voice
    devices: ["/dev/snd:/dev/snd"]  # Audio device access
    environment:
      - REDIS_URL=redis://redis:6379
      - ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}
      
  nova-screen:
    build: ./services/screen
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - REDIS_URL=redis://redis:6379
    shm_size: "256m"  # Shared memory for screen captures
    
  nova-api:
    build: ./services/api
    ports: ["8000:8000"]
    environment:
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=postgresql://nova:${POSTGRES_PASSWORD}@postgres/nova
      
  nova-frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - VITE_API_URL=http://localhost:8000
```

---

# 5. PRD, FSD & TECH STACK

## 5.1 Product Requirements Document (PRD)

### Product Name: NOVA — Next-Generation Omniscient Virtual Assistant

**Version:** 1.0  
**Product Manager:** [To be assigned]  
**Status:** Approved for Development

---

### 5.1.1 Executive Summary

NOVA is a proprietory AI assistant platform designed to function as a cognitive operating layer over any computer system. The system combines multimodal AI perception, autonomous agent capabilities, and deep system integration to deliver an experience analogous to a highly capable AI colleague — one that observes context, anticipates needs, and executes complex tasks end-to-end.

### 5.1.2 Objectives and Key Results (OKRs)

**Objective 1: Achieve human-quality contextual understanding**
- KR1: Screen analysis correctly identifies active task context with >90% accuracy
- KR2: Voice command intent recognized correctly >95% of utterances
- KR3: Proactive suggestions rated "relevant" by user >75% of the time

**Objective 2: Autonomous task execution**
- KR1: 80% of multi-step tasks completed without user intervention after initial instruction
- KR2: Task completion latency <30 seconds for tasks with <5 steps
- KR3: Error recovery successful >85% of the time without user escalation

**Objective 3: Seamless, natural interaction**
- KR1: Voice response latency (first word spoken) <2 seconds end-to-end
- KR2: User rates conversations "natural" or "very natural" >80% of sessions
- KR3: System uptime >99.5%

### 5.1.3 Target Users

**Primary:** Technical knowledge workers (software engineers, product managers, data scientists) who spend 8+ hours daily in front of a computer and manage complex, multi-tool workflows.

**Secondary:** Executives and business leaders who need an AI chief-of-staff for communication management, research synthesis, and strategic task delegation.

**Tertiary:** Power users who want deep computer automation and are comfortable granting system-level access.

### 5.1.4 Functional Requirements

| ID | Requirement | Priority | Complexity |
|----|-------------|----------|------------|
| FR-001 | Wake word detection with <200ms latency | P0 | Medium |
| FR-002 | Speech-to-text with >97% accuracy | P0 | Medium |
| FR-003 | Natural language conversation (multi-turn, context-aware) | P0 | High |
| FR-004 | Text-to-speech, natural voice | P0 | Low |
| FR-005 | Screen capture and semantic analysis | P0 | High |
| FR-006 | Basic OS control (open/close apps, file ops) | P0 | Medium |
| FR-007 | Email read/write (Gmail + Outlook) | P1 | Medium |
| FR-008 | Calendar management | P1 | Medium |
| FR-009 | Web search and information synthesis | P1 | Medium |
| FR-010 | Code intelligence (analysis, generation, review) | P1 | High |
| FR-011 | Multi-step autonomous task execution | P1 | Very High |
| FR-012 | Persistent semantic memory | P1 | High |
| FR-013 | System health monitoring | P2 | Medium |
| FR-014 | GUI automation (click, type, scrape any app) | P2 | High |
| FR-015 | Multi-agent parallel execution | P2 | Very High |
| FR-016 | Behavioral learning and personalization | P3 | Very High |
| FR-017 | Security threat detection | P3 | High |
| FR-018 | Mobile companion app | P3 | High |

### 5.1.5 Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| **Latency** | Voice round-trip: <2s; Screen analysis: <5s; Task execution start: <1s |
| **Privacy** | All conversation data encrypted at rest (AES-256). No audio stored beyond session unless user opts in. All cloud API calls made with user's own API keys — no data passes through NOVA servers. |
| **Availability** | Local mode: 100% (no internet required). Cloud-enhanced mode: 99.5% (depends on API availability) |
| **Resource Usage** | Idle CPU: <5%. Active processing: <40% CPU, <4GB RAM baseline, <8GB peak. Disk: <10GB for full local model suite. |
| **Compatibility** | macOS 13+, Windows 11, Ubuntu 22.04+ |
| **Security** | TLS 1.3 for all network communication. Local data encrypted with user-derived key. Audit log of all system actions. |

### 5.1.6 Out of Scope (Version 1.0)

- Physical device control (smart home, IoT) — V2
- Multi-user enterprise deployment — V2
- Mobile primary interface (mobile is companion-only) — V2
- Video call participation — V3
- Self-improvement (NOVA writing its own code) — V3

---

## 5.2 Functional Specification Document (FSD)

### 5.2.1 System Startup Sequence

```
Boot Sequence (targeting <5 seconds to fully operational):

T+0.0s  Launch nova-daemon process
T+0.5s  Initialize Redis connection pool
T+0.5s  Load local models into GPU/CPU memory:
         - Porcupine wake word engine
         - WebRTC VAD
         - Sentence transformer (for memory embeddings)
T+2.0s  Connect to PostgreSQL, verify schema
T+2.0s  Load user configuration and preferences
T+2.5s  Start screen capture daemon
T+2.5s  Start audio input stream
T+3.0s  Connect to external APIs (verify tokens, warm connections)
T+3.0s  Start FastAPI server
T+4.0s  Launch Electron frontend
T+4.5s  Run self-diagnostic (all systems check)
T+5.0s  NOVA speaks: "NOVA online. Good morning, [name]."
```

### 5.2.2 Conversation State Machine

```
States:
  IDLE        → Listening for wake word only
  LISTENING   → Recording user speech after wake word
  PROCESSING  → Running STT + NLU + Agent
  RESPONDING  → Speaking response
  EXECUTING   → Running a background task
  WAITING     → Awaiting user confirmation for risky action
  ERROR       → Something failed, explaining to user

Transitions:
  IDLE + wake_word_detected → LISTENING
  LISTENING + silence_timeout(2s) → PROCESSING
  LISTENING + manual_interrupt → IDLE
  PROCESSING + response_ready → RESPONDING
  PROCESSING + action_required → EXECUTING
  PROCESSING + risky_action_detected → WAITING
  RESPONDING + response_complete → IDLE (or LISTENING if followup expected)
  EXECUTING + task_complete → RESPONDING
  WAITING + user_confirms → EXECUTING
  WAITING + user_denies → RESPONDING (explain cancellation)
  ANY + error → ERROR → IDLE
```

### 5.2.3 API Specification

```yaml
# Core NOVA API Endpoints (FastAPI)

POST /api/v1/chat
  Description: Send a text message to NOVA
  Body: { message: string, session_id: string, context?: object }
  Response: { response: string, actions_taken: [], suggestions: [] }
  
POST /api/v1/voice/transcribe  
  Description: Upload audio for transcription
  Body: multipart/form-data (audio file, WAV or MP3)
  Response: { transcript: string, confidence: float }
  
GET /api/v1/screen/current
  Description: Get current screen analysis
  Response: { analysis: ScreenAnalysis, timestamp: float }
  
POST /api/v1/tasks/create
  Description: Create a new autonomous task
  Body: { goal: string, priority: low|medium|high, constraints?: object }
  Response: { task_id: string, plan: Step[], estimated_duration_s: int }

GET /api/v1/tasks/{task_id}
  Description: Get task status and results
  Response: { status: pending|running|complete|failed, steps: Step[], result?: any }
  
DELETE /api/v1/tasks/{task_id}
  Description: Cancel a running task
  
GET /api/v1/memory/search?q={query}
  Description: Semantic search over memory
  Response: { memories: Memory[], total: int }
  
GET /api/v1/system/health
  Description: System health metrics
  Response: { cpu: float, memory: float, disk: float, services: ServiceStatus[] }
  
WebSocket /ws/stream
  Description: Real-time streaming channel
  Events emitted: voice.transcript, analysis.update, task.progress, 
                  nova.response.chunk, system.alert, proactive.suggestion
```

---

## 5.3 Recommended Tech Stack Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    NOVA TECH STACK                          │
├─────────────────┬───────────────────────────────────────────┤
│ LAYER           │ TECHNOLOGY                                │
├─────────────────┼───────────────────────────────────────────┤
│ AI Models       │ Claude 3.5 Sonnet (primary LLM + vision) │
│                 │ GPT-4o (fallback)                        │
│                 │ LLaMA 3.1 70B via Ollama (local)        │
│                 │ LLaVA 1.6 (local vision)                │
│                 │ Faster-Whisper large-v3 (local STT)     │
│                 │ ElevenLabs / Piper TTS                  │
│                 │ Porcupine (wake word)                   │
├─────────────────┼───────────────────────────────────────────┤
│ AI Framework    │ LangChain 0.3 + LangGraph 0.2           │
│                 │ LiteLLM (model router)                  │
├─────────────────┼───────────────────────────────────────────┤
│ Backend         │ Python 3.11 + FastAPI + AsyncIO          │
│                 │ Pydantic v2 (data validation)           │
│                 │ Celery + Redis (task queue)             │
├─────────────────┼───────────────────────────────────────────┤
│ Frontend        │ Electron 31 + React 18 + TypeScript      │
│                 │ Tailwind CSS + Framer Motion            │
│                 │ Socket.io (real-time)                   │
├─────────────────┼───────────────────────────────────────────┤
│ Databases       │ PostgreSQL 16 (structured data)          │
│                 │ ChromaDB 0.5 (vector/semantic memory)   │
│                 │ Redis 7 (cache, events, working memory) │
│                 │ SQLite (local device preferences)       │
├─────────────────┼───────────────────────────────────────────┤
│ Infra           │ Docker + Docker Compose (dev/staging)    │
│                 │ Kubernetes (production enterprise)      │
│                 │ Nginx (reverse proxy)                   │
├─────────────────┼───────────────────────────────────────────┤
│ System Control  │ PyAutoGUI (GUI automation)               │
│                 │ PyWinAuto (Windows accessibility)       │
│                 │ AppKit / AppScript (macOS automation)   │
│                 │ X11/AT-SPI (Linux accessibility)        │
│                 │ Playwright (browser automation)         │
├─────────────────┼───────────────────────────────────────────┤
│ Monitoring      │ Prometheus + Grafana (metrics)           │
│                 │ Sentry (error tracking)                 │
│                 │ OpenTelemetry (distributed tracing)     │
├─────────────────┼───────────────────────────────────────────┤
│ Security        │ AES-256-GCM (data at rest)               │
│                 │ TLS 1.3 (data in transit)               │
│                 │ Vault by HashiCorp (secrets management) │
│                 │ JWT (API authentication)                │
├─────────────────┼───────────────────────────────────────────┤
│ CI/CD           │ GitHub Actions / GitLab CI              │
│                 │ pytest + coverage (Python testing)      │
│                 │ Vitest + Playwright (frontend testing)  │
│                 │ SonarQube (code quality)                │
└─────────────────┴───────────────────────────────────────────┘
```

---

# 6. AGILE DEVELOPMENT ROADMAP

## 6.1 Project Structure

**Duration:** 40 weeks (10 months)  
**Team:** 
- 1x AI/ML Engineer (lead)
- 2x Backend Engineers
- 1x Frontend Engineer
- 1x DevOps / Platform Engineer
- 1x QA Engineer
- 1x Product Manager / Architect

**Sprint Cadence:** 2-week sprints  
**Environments:** Development → Staging → Production

---

## 6.2 Sprint Plan

### PHASE 1: FOUNDATION (Sprints 1–4, Weeks 1–8)

---

**MILESTONE 1: NOVA Speaks and Listens**

**Sprint 1 (Weeks 1–2): Infrastructure & Voice Core**

*Objective: NOVA can hear a command and respond verbally.*

| User Story | Acceptance Criteria | Story Points |
|------------|---------------------|--------------|
| As a user, I can say "Hey NOVA" and the system wakes up | Wake word detected <200ms, false positive rate <1/hour | 8 |
| As a user, my speech is converted to text accurately | WER (Word Error Rate) <3% on standard English, technical vocabulary | 13 |
| As a user, NOVA responds in a natural voice | First audio byte <300ms after response generated, natural prosody | 5 |
| As a developer, all services run in Docker containers | docker-compose up starts all services, passes health checks | 8 |
| As a developer, a CI pipeline runs tests on every commit | GitHub Actions: lint + unit tests + build < 5 minutes | 5 |

*Technical deliverables:*
- Docker Compose environment (Redis, PostgreSQL, nova-voice, nova-brain)
- Wake word detection service (Porcupine)
- STT service (Faster-Whisper, large-v3)
- TTS service (ElevenLabs API + Piper local fallback)
- Basic FastAPI gateway
- GitHub Actions CI pipeline

---

**Sprint 2 (Weeks 3–4): Conversation Engine**

*Objective: NOVA holds a coherent multi-turn conversation.*

| User Story | Acceptance Criteria | Story Points |
|------------|---------------------|--------------|
| As a user, NOVA remembers context within a conversation | References entities from 10+ turns ago without re-prompting | 13 |
| As a user, NOVA can answer general knowledge questions | Correct factual responses with appropriate uncertainty | 8 |
| As a user, NOVA understands follow-up questions | "What about tomorrow?" works after asking about today's weather | 5 |
| As a user, I can see my conversation history in the UI | Electron UI shows conversation log with timestamps | 8 |
| As a developer, I have a memory system foundation | Redis working memory + ChromaDB episodic memory functional | 13 |

*Technical deliverables:*
- LangGraph conversation graph (supervisor + responder nodes)
- Memory manager (Redis + ChromaDB integration)
- Basic Electron frontend with conversation view
- Context window management (50-turn sliding window)
- Unit tests for memory system (>80% coverage)

---

**Sprint 3 (Weeks 5–6): OS Control & File System**

*Objective: NOVA can control the computer at a basic level.*

| User Story | Acceptance Criteria | Story Points |
|------------|---------------------|--------------|
| As a user, I can ask NOVA to open any application | Opens correctly on macOS, Windows, Linux | 8 |
| As a user, I can ask NOVA to find files | Finds files by name and content, <3 seconds | 8 |
| As a user, I can ask NOVA to take a screenshot | Screenshots saved to ~/nova/screenshots/ with timestamp | 3 |
| As a user, I can ask NOVA to control volume/brightness | System settings changed immediately | 5 |
| As a user, NOVA can read file contents to me | Reads text files, PDFs, DOCX; summarizes long documents | 8 |

*Technical deliverables:*
- OS abstraction layer (cross-platform: macOS/Win/Linux)
- File search engine (filename + content-based via ripgrep)
- System settings controller
- Document reader (PDF, DOCX, TXT support)
- Tool definitions for LangGraph tool executor
- Integration tests for OS control on all platforms

---

**Sprint 4 (Weeks 7–8): Email, Calendar & Web Search**

*Objective: NOVA integrates with productivity tools.*

| User Story | Acceptance Criteria | Story Points |
|------------|---------------------|--------------|
| As a user, NOVA can read my emails | Gmail + Outlook integration, shows last 20 emails | 13 |
| As a user, NOVA can draft and send emails | Draft appears for approval before sending | 8 |
| As a user, NOVA can show my calendar | Today's events with time, title, attendees | 8 |
| As a user, NOVA can schedule meetings | Creates event via natural language, confirms details | 8 |
| As a user, NOVA can search the web | Returns synthesized answer with sources, <10 seconds | 8 |

*Technical deliverables:*
- Gmail API integration (OAuth 2.0, read/write)
- Outlook/MS Graph API integration
- Google Calendar + Outlook Calendar integration
- Web search tool (Serper API or Bing Search API)
- Web page reader (Playwright + content extraction)
- Secure credential storage (OS Keychain integration)

---

**MILESTONE 1 UAT: End-to-End Voice Interaction Test**

Test cases to validate before Phase 2:
```
UAT-001: Wake word detection in noisy environment (>90% detection rate)
UAT-002: "Schedule a meeting with Ahmed tomorrow at 2pm" → calendar event created
UAT-003: "What are my emails from Sarah today?" → emails summarized verbally
UAT-004: "Open Chrome and search for Python documentation" → executed correctly
UAT-005: 10-turn conversation maintains context throughout
UAT-006: Graceful handling of ambiguous requests (NOVA asks for clarification)
UAT-007: Offline mode: conversation works without internet (local models)
```

---

### PHASE 2: PERCEPTION (Sprints 5–8, Weeks 9–16)

---

**MILESTONE 2: NOVA Sees and Understands**

**Sprint 5 (Weeks 9–10): Screen Capture & Basic Analysis**

*Objective: NOVA continuously understands what's on screen.*

| User Story | Acceptance Criteria | Story Points |
|------------|---------------------|--------------|
| As a user, NOVA can describe what I'm looking at | Describes active app and content accurately >90% of the time | 13 |
| As a user, NOVA only analyzes when the screen changes | CPU usage <5% when screen is static | 8 |
| As a user, I can define privacy zones on my screen | Defined regions are blurred/excluded from analysis | 8 |
| As a developer, screen analysis runs asynchronously | Does not block voice or conversation processing | 5 |
| As a user, NOVA knows which application I'm using | Active app detected instantly, >99% accuracy | 5 |

*Technical deliverables:*
- Screen capture engine (MSS + perceptual hashing)
- Claude Vision integration for semantic analysis
- Local LLaVA fallback for offline/privacy mode
- Privacy zone manager (UI to define excluded regions)
- Async event pipeline: screen changes → analysis queue

---

**Sprint 6 (Weeks 11–12): OCR & Document Understanding**

*Objective: NOVA can read and understand any text visible on screen.*

| User Story | Acceptance Criteria | Story Points |
|------------|---------------------|--------------|
| As a user, NOVA can read text from any screen region | OCR accuracy >98% on clear text, >92% on low-quality | 8 |
| As a user, NOVA understands code on screen | Identifies language, function names, bugs in visible code | 13 |
| As a user, NOVA can answer questions about what I'm reading | "Summarize this article" works on any readable page | 8 |
| As a user, NOVA can extract data from tables on screen | Tables extracted as structured data | 8 |

*Technical deliverables:*
- EasyOCR integration with post-processing
- Code detection and AST-level analysis (Tree-sitter)
- Structured data extraction from tables/forms
- Document Q&A via vision + RAG pipeline

---

**Sprint 7 (Weeks 13–14): Proactive Intelligence**

*Objective: NOVA surfaces relevant help without being asked.*

| User Story | Acceptance Criteria | Story Points |
|------------|---------------------|--------------|
| As a user, NOVA suggests help when I'm stuck (30min on same task) | Triggers proactive offer after 30 minutes of no progress | 13 |
| As a user, NOVA warns me before meetings | 10-minute calendar alert with attendee brief | 5 |
| As a user, I can configure proactive suggestion frequency | Settings: off/subtle/normal/proactive | 5 |
| As a user, proactive suggestions appear as non-intrusive overlays | HUD notification, not popup modal | 8 |
| As a developer, relevance scoring trained on user feedback | Thumbs up/down on suggestions updates relevance model | 13 |

*Technical deliverables:*
- Attention/stuckness detector (time on task + activity signals)
- Calendar pre-brief generator
- Proactive suggestion ranking model
- HUD notification component (Electron overlay)
- Feedback collection and relevance model update pipeline

---

**Sprint 8 (Weeks 15–16): Code Intelligence Integration**

*Objective: NOVA is a genuine pair programmer.*

| User Story | Acceptance Criteria | Story Points |
|------------|---------------------|--------------|
| As a developer, NOVA explains any error message I see | Explains error, root cause, and fix within 3 seconds | 8 |
| As a developer, NOVA can review visible code for bugs | Identifies issues not caught by linter | 13 |
| As a developer, NOVA generates code in my project's style | Studies codebase and matches naming/patterns | 13 |
| As a developer, NOVA explains unfamiliar code | Walk-through with inline annotations | 8 |
| As a developer, NOVA integrates with my IDE (VS Code) | VS Code extension that calls NOVA API | 13 |

*Technical deliverables:*
- Error explanation engine (OCR → LLM analysis → solution)
- Codebase indexer (Tree-sitter AST, embedding-based search)
- Style analyzer (learns project conventions)
- VS Code extension (TypeScript, NOVA API client)
- JetBrains plugin (Kotlin, NOVA API client)

---

### PHASE 3: AGENCY (Sprints 9–14, Weeks 17–28)

---

**MILESTONE 3: NOVA Acts Autonomously**

**Sprint 9 (Weeks 17–18): Multi-Step Task Planning**

| User Story | Story Points |
|------------|--------------|
| NOVA can decompose a complex goal into ordered steps | 21 |
| NOVA shows its plan before executing and awaits approval | 8 |
| NOVA handles plan failures with automatic retry + re-planning | 13 |
| NOVA narrates progress on long-running tasks | 5 |

**Sprint 10 (Weeks 19–20): GUI Automation**

| User Story | Story Points |
|------------|--------------|
| NOVA can click UI elements using vision-based targeting | 13 |
| NOVA can fill out forms in any application | 13 |
| NOVA can record user workflows and replay them | 13 |
| NOVA detects if automation actions failed and retries | 8 |

**Sprint 11 (Weeks 21–22): Multi-Agent Orchestration**

| User Story | Story Points |
|------------|--------------|
| NOVA spawns specialist sub-agents for parallel work | 21 |
| Sub-agents share context via message bus | 8 |
| Supervisor agent synthesizes results from all sub-agents | 13 |
| Cost management: user sets monthly API spend limit | 8 |

**Sprint 12 (Weeks 23–24): System Monitoring & Self-Healing**

| User Story | Story Points |
|------------|--------------|
| NOVA monitors CPU, memory, disk, network in real-time | 8 |
| NOVA alerts user to anomalous system conditions | 5 |
| NOVA can kill runaway processes with user permission | 8 |
| NOVA predicts resource exhaustion before it happens | 13 |

**Sprint 13 (Weeks 25–26): Knowledge Base & Second Brain**

| User Story | Story Points |
|------------|--------------|
| NOVA automatically captures key info from what I read | 13 |
| I can ask NOVA about anything I've ever shown it | 13 |
| NOVA builds a knowledge graph of my projects | 21 |
| Knowledge exports to Notion/Obsidian | 8 |

**Sprint 14 (Weeks 27–28): Security Intelligence**

| User Story | Story Points |
|------------|--------------|
| NOVA scans for hardcoded secrets before git commits | 8 |
| NOVA alerts on unusual file access patterns | 8 |
| NOVA detects and explains suspicious network activity | 13 |
| NOVA checks installed packages against CVE database | 8 |

---

### PHASE 4: INTELLIGENCE (Sprints 15–18, Weeks 29–36)

---

**MILESTONE 4: NOVA Learns and Adapts**

**Sprint 15 (Weeks 29–30): Behavioral Learning**

- Learns work schedule and energy patterns
- Adapts response formality to context
- Remembers stated preferences permanently
- Learning dashboard with full visibility/control

**Sprint 16 (Weeks 31–32): API Hub & Custom Integrations**

- OpenAPI spec parser for instant new integrations
- Pre-built connectors: Jira, Linear, Slack, Salesforce, GitHub, Notion
- Custom connector builder with NOVA assistance
- OAuth management dashboard

**Sprint 17 (Weeks 33–34): Predictive Task Management**

- Daily morning brief
- Workload analysis and rebalancing recommendations
- Natural language task capture from any conversation
- Integration with Jira/Linear/Asana

**Sprint 18 (Weeks 35–36): Performance Optimization & Polish**

- Profiling and bottleneck elimination
- Voice latency optimization (<1.5s target)
- UI polish: animations, themes, accessibility
- Battery/power optimization for laptops
- Startup time optimization (<3 seconds)

---

### PHASE 5: HARDENING (Sprints 19–20, Weeks 37–40)

**Sprint 19: Security Hardening & Penetration Testing**

- External penetration test (third-party firm)
- Fix all critical and high-severity findings
- Cryptographic audit
- Privacy review (data flow documentation complete)

**Sprint 20: Production Release**

- Final UAT sign-off
- Documentation complete (user guide + developer guide)
- Performance benchmarks met and documented
- Rollout plan executed: Dev → Staging → Production
- Post-launch monitoring and incident response plan

---

## 6.3 Environment Strategy

```
DEVELOPMENT ENVIRONMENT
  Purpose: Daily development and experimentation
  Infrastructure: Developer's local machine + Docker Compose
  Data: Synthetic/anonymized test data only
  Deployment: Manual (docker-compose up)
  AI Models: Mix of local and cloud (developer's own API keys)
  Access: Developer team only
  
STAGING ENVIRONMENT  
  Purpose: Integration testing, UAT, pre-production validation
  Infrastructure: Identical to production (same Docker images, same resource limits)
  Data: Sanitized copy of production-like data, no real PII
  Deployment: Automated on merge to `develop` branch
  AI Models: Same as production (shared test API keys with spend limits)
  Access: QA team + stakeholders for UAT
  
PRODUCTION ENVIRONMENT
  Purpose: Live user system
  Infrastructure: Local machine installation (v1 is single-user desktop app)
  Data: User's real data, encrypted locally
  Deployment: Signed installer package (macOS .pkg, Windows .msi, Linux .deb/.rpm)
  AI Models: User provides own API keys OR fully local model suite
  Access: End user only
```

## 6.4 User Acceptance Testing Plan

### UAT Phase 1: Core Voice & Conversation (End of Sprint 2)
```
Test Environment: Staging
Testers: Product Manager + 2 internal users
Duration: 3 days

Test Scripts:
UAT-C-001  Wake word detection at various distances (0.5m, 1m, 2m, 3m)
UAT-C-002  Voice command accuracy with different accents (5 testers)
UAT-C-003  10-turn conversation maintaining context
UAT-C-004  NOVA handles ambiguity (asks for clarification, not guessing)
UAT-C-005  Offline mode: full conversation without internet
UAT-C-006  NOVA personality consistency across all interactions

Pass Criteria: >90% of test cases pass. No P0 bugs.
```

### UAT Phase 2: Productivity Integration (End of Sprint 4)
```
Test Environment: Staging + real user accounts (test accounts, not primary)
Testers: 5 internal users
Duration: 5 days

Test Scripts:
UAT-P-001  Email: read, summarize, draft, send workflow
UAT-P-002  Calendar: create, update, delete events; find free slots
UAT-P-003  "Prepare me for my 3pm meeting" → full brief generated
UAT-P-004  Web research: "Summarize the latest news on [topic]"
UAT-P-005  File operations: find, read, organize, rename files

Pass Criteria: >85% test cases pass. P0 and P1 bugs resolved.
```

### UAT Phase 3: Screen Understanding (End of Sprint 6)
```
Test Environment: Staging
Testers: 8 internal users (mix of technical and non-technical)
Duration: 5 days

Test Scripts:
UAT-S-001  "What am I looking at?" in 10 different apps
UAT-S-002  "What does this error mean?" on 10 different error types
UAT-S-003  "Summarize what I'm reading" on web pages, PDFs, docs
UAT-S-004  Privacy zone: defined region never appears in analysis
UAT-S-005  Code explanation: 5 different languages, 5 complexity levels

Pass Criteria: >85% of test cases pass.
```

### UAT Phase 4: Autonomous Execution (End of Sprint 11)
```
Test Environment: Staging (isolated VM to prevent side effects)
Testers: 5 power users + QA team
Duration: 10 days

Test Scripts:
UAT-A-001  "Prepare the weekly status report" (multi-step, multi-tool)
UAT-A-002  NOVA requests confirmation before sending email/deleting file
UAT-A-003  Task fails mid-way: NOVA recovers or escalates gracefully
UAT-A-004  GUI automation: fill a 10-field form in a real application
UAT-A-005  Multi-agent: parallel tasks complete faster than sequential

Pass Criteria: >80% of autonomous tasks complete correctly. Zero data loss incidents.
```

### UAT Phase 5: Final Acceptance (End of Sprint 20)
```
Test Environment: Production-equivalent
Testers: Full target user group (10-20 users), 2-week beta period
Duration: 14 days

Metrics:
  - Task completion rate: >80%
  - User satisfaction score: >4.0/5.0
  - System uptime: >99.5%
  - Voice response latency: <2s (p95)
  - Zero critical security vulnerabilities
  - Full feature set operational
  
Sign-off: Product Manager + Tech Lead + Security Officer
```

---

# 7. SECURITY, LEGAL & IP FRAMEWORK

## 7.1 Data Security Architecture

### Encryption at Rest

All local data is encrypted using AES-256-GCM with a key derived from the user's system credentials:

```python
# security/encryption.py
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
import os
import secrets

class LocalEncryption:
    """
    Encrypts NOVA's local data store.
    Key derived from user credentials via Scrypt KDF.
    Never stores the key — derived fresh each session.
    """
    
    def __init__(self, user_passphrase: bytes):
        # Load or generate salt (stored in keychain, not the key itself)
        self.salt = self._get_or_create_salt()
        self.key = self._derive_key(user_passphrase)
        self.cipher = AESGCM(self.key)
        
    def _derive_key(self, passphrase: bytes) -> bytes:
        kdf = Scrypt(
            salt=self.salt,
            length=32,  # AES-256 requires 32 bytes
            n=2**14,    # CPU/memory cost parameter
            r=8,
            p=1
        )
        return kdf.derive(passphrase)
        
    def encrypt(self, plaintext: bytes) -> bytes:
        nonce = secrets.token_bytes(12)  # 96-bit nonce for AES-GCM
        ciphertext = self.cipher.encrypt(nonce, plaintext, None)
        return nonce + ciphertext  # Prepend nonce for decryption
        
    def decrypt(self, ciphertext: bytes) -> bytes:
        nonce, data = ciphertext[:12], ciphertext[12:]
        return self.cipher.decrypt(nonce, data, None)
```

### API Key Security

```python
# security/keychain.py
import keyring
import platform

class APIKeyManager:
    """
    Stores all API keys in OS native secure storage:
    - macOS: Keychain
    - Windows: Credential Manager
    - Linux: libsecret / GNOME Keyring
    
    Keys NEVER stored in plaintext files, environment variables on disk,
    or application databases.
    """
    
    SERVICE_NAME = "NOVA-Assistant"
    
    def store_key(self, service: str, key_value: str):
        keyring.set_password(self.SERVICE_NAME, service, key_value)
        
    def get_key(self, service: str) -> str | None:
        return keyring.get_password(self.SERVICE_NAME, service)
        
    def delete_key(self, service: str):
        keyring.delete_password(self.SERVICE_NAME, service)
```

### Audit Logging

```python
# security/audit_log.py
import sqlite3
import json
from datetime import datetime

class AuditLogger:
    """
    Immutable audit log of all actions NOVA takes.
    Stored in append-only SQLite table.
    User can review, export, or purge.
    """
    
    def log_action(
        self,
        action_type: str,         # "file_read", "email_sent", "shell_exec", etc.
        target: str,              # What was acted upon
        details: dict,            # Action parameters
        user_authorized: bool,    # Did user explicitly authorize?
        outcome: str              # "success", "failed", "cancelled"
    ):
        with sqlite3.connect("~/.nova/audit.db") as conn:
            conn.execute("""
                INSERT INTO audit_log 
                (timestamp, action_type, target, details, user_authorized, outcome)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.utcnow().isoformat(),
                action_type,
                target,
                json.dumps(details),
                int(user_authorized),
                outcome
            ))
```

## 7.2 Privacy Architecture

### What NOVA Does NOT Do (Hard Guarantees):

1. **No persistent audio recording.** Audio is processed in-memory and discarded after transcription. No audio files saved unless user explicitly enables recording.
2. **No screen recordings stored.** Screen frames are analyzed and immediately discarded. No video or screenshots retained beyond analysis.
3. **No data transmitted to NOVA servers.** The system connects directly to LLM provider APIs (Anthropic, OpenAI) using the user's own API keys. No NOVA-operated intermediary sees the data.
4. **No behavioral data sold or shared.** All learned preferences stay on-device.
5. **No cloud sync without explicit opt-in.** All data lives locally by default.

### Data Residency Options:

```
Option A: Fully Local (Maximum Privacy)
  - All models run locally (Ollama + LLaMA + LLaVA + Whisper + Piper)
  - No internet connection required for core functionality
  - Trade-off: Lower quality than cloud models

Option B: Hybrid (Recommended Default)
  - Cloud APIs for LLM inference (user's own API keys)
  - Local models for audio (Whisper, Piper)
  - Data goes directly to Anthropic/OpenAI per their privacy policies
  - No intermediary servers

Option C: Enterprise
  - Private LLM deployment (Azure OpenAI or AWS Bedrock)
  - Company controls all data residency
  - Air-gapped deployment option available
```

## 7.3 NDA and IP Framework

### Non-Disclosure Agreement (NDA) Requirements

**All personnel with access to NOVA's codebase must execute:**

```
NOVA DEVELOPMENT NON-DISCLOSURE AGREEMENT — SUMMARY

Parties: NOVA IP Owner ("Disclosing Party") and Developer/Contractor ("Receiving Party")

Covered Information:
  - All source code, algorithms, and architectural designs
  - AI model configurations and fine-tuning data
  - API integrations and proprietary connectors
  - User behavioral data and learning models
  - Any trade secrets disclosed during development

Obligations:
  - Keep all information strictly confidential
  - Use information solely for NOVA development work
  - Do not disclose to any third party without written consent
  - Maintain security controls equivalent to the Disclosing Party's own

Duration: 5 years from date of execution, indefinite for trade secrets

Return of Materials: All materials returned within 30 days of engagement end

IP Ownership: See Section 7.4 (IP Assignment)

Remedies: Acknowledges that breach would cause irreparable harm; 
          injunctive relief available without posting bond

Jurisdiction: [Specify governing law and jurisdiction]
```

**Mandatory NDA execution checklist:**
- [ ] All FTE developers (employment contract includes NDA clause)
- [ ] All contractors (standalone NDA before any code access)
- [ ] All QA testers with access to codebase
- [ ] All cloud service vendors (ensure their DPAs cover your data)
- [ ] All security auditors / penetration testers

### 7.4 IP Ownership Framework

```
INTELLECTUAL PROPERTY OWNERSHIP MATRIX

┌──────────────────────────────────┬─────────────┬────────────────────┐
│ Asset                            │ Owner       │ Notes              │
├──────────────────────────────────┼─────────────┼────────────────────┤
│ NOVA source code (original)      │ NOVA IP Co  │ Work-for-hire      │
│ Architectural designs            │ NOVA IP Co  │                    │
│ Trained fine-tuned models        │ NOVA IP Co  │                    │
│ Brand, name, logo                │ NOVA IP Co  │ Trademark filing   │
│ Training datasets (generated)    │ NOVA IP Co  │                    │
│ User-created workflows/scripts   │ End User    │ License back       │
│ Open source dependencies         │ Respective  │ License compliance │
│                                  │ maintainers │ required           │
│ Underlying LLM models (Claude)   │ Anthropic   │ API license only   │
│ Underlying LLM models (GPT)      │ OpenAI      │ API license only   │
└──────────────────────────────────┴─────────────┴────────────────────┘

IP ASSIGNMENT CLAUSE (for all contractors):
"All work product created by Contractor in connection with NOVA,
including but not limited to code, designs, documentation, and 
inventions, is hereby assigned to [NOVA IP Owner] as work made
for hire. To the extent any work product does not qualify as
work made for hire, Contractor hereby assigns all right, title,
and interest in such work product to [NOVA IP Owner]."

OPEN SOURCE LICENSE COMPLIANCE:
NOVA must audit all dependencies for license compatibility.
Required actions:
- GPL-licensed code: must not be included in proprietary core
- LGPL-licensed code: dynamic linking permitted, document usage
- Apache 2.0, MIT, BSD: permitted with attribution
- Use FOSSA or TLDR Legal for automated compliance scanning
```

---

# 8. SCALABILITY, MAINTAINABILITY & FUTURE EXPANSION

## 8.1 Scalability Architecture

### Challenge 1: Screen Analysis Throughput

**Problem:** Analyzing every screen frame with a cloud vision model would cost ~$0.50 per hour of use at 2fps.

**Solution — Tiered Analysis Pipeline:**
```
Frame captured
     │
     ▼
[Change Detector] ──── No significant change ──→ Discard
     │
     │ Significant change detected
     ▼
[Fast Local Classifier] (LLaVA-1.6 7B, <100ms)
     │
     ├── Low complexity (email, browser, document) → Use local analysis only
     │
     └── High complexity (multi-app, code review, errors) → Escalate to Claude Vision
     
Cost result: $0.02-0.05/hour (10-25x cheaper)
Latency result: 95% of analyses completed locally in <200ms
```

### Challenge 2: LLM Context Window Management

**Problem:** A full day of conversation far exceeds any model's context window (even 200K tokens).

**Solution — Hierarchical Context Compression:**
```python
class ContextManager:
    """
    Manages context window with automatic compression.
    
    Strategy:
    1. Keep last 10 turns verbatim (recent memory)
    2. Compress turns 11-50 into bullet-point summaries
    3. Beyond turn 50: move to episodic memory (vector DB)
    4. Relevant episodic memories retrieved via semantic search
       and injected into context on each new turn
    """
    
    MAX_VERBATIM_TURNS = 10
    MAX_SUMMARY_TURNS = 40
    TOKENS_PER_TURN_BUDGET = 500  # Compressed turns get 500 tokens max
    
    def build_context(self, session_id: str, query: str) -> list[dict]:
        full_history = self.memory.get_session_history(session_id)
        
        # Most recent turns — verbatim
        recent = full_history[-self.MAX_VERBATIM_TURNS:]
        
        # Middle turns — compressed
        middle = full_history[-(self.MAX_VERBATIM_TURNS + self.MAX_SUMMARY_TURNS):
                              -self.MAX_VERBATIM_TURNS]
        compressed = self._compress_turns(middle)
        
        # Long-term memory — semantic retrieval
        relevant_memories = self.memory.recall(query, n_results=3)
        
        return self._assemble_context(relevant_memories, compressed, recent)
```

### Challenge 3: Multi-Agent Cost Control

**Problem:** Multiple parallel agents can quickly exhaust API budgets.

**Solution — Token Budget Manager:**
```python
class TokenBudgetManager:
    """
    Enforces per-task and per-day token budgets.
    Automatically selects cheaper models for simpler sub-tasks.
    """
    
    MODEL_COSTS = {
        "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},  # per 1M tokens
        "claude-3-haiku-20240307":    {"input": 0.25, "output": 1.25},
        "gpt-4o-mini":                {"input": 0.15, "output": 0.60},
        "llama-3.1-70b-local":        {"input": 0.0,  "output": 0.0},
    }
    
    TASK_COMPLEXITY_MODEL_MAP = {
        "simple_qa":         "gpt-4o-mini",
        "code_review":       "claude-3-5-sonnet-20241022",
        "screen_analysis":   "claude-3-haiku-20240307",
        "complex_planning":  "claude-3-5-sonnet-20241022",
        "basic_automation":  "llama-3.1-70b-local"
    }
    
    def select_model(self, task_type: str, remaining_budget: float) -> str:
        preferred = self.TASK_COMPLEXITY_MODEL_MAP.get(task_type, "claude-3-haiku-20240307")
        if remaining_budget < 0.10:  # Less than 10 cents remaining today
            return "llama-3.1-70b-local"  # Always fall back to free local
        return preferred
```

## 8.2 Maintainability Principles

### Modularity Requirements

Every NOVA component MUST follow these rules:

1. **Single Responsibility:** One class does one thing. Screen capture ≠ screen analysis.
2. **Dependency Injection:** Never instantiate dependencies inside a class. Inject them.
3. **Interface over Implementation:** Define protocols/abstract base classes first.
4. **Configuration Externalization:** No hardcoded values. All config in `~/.nova/config.yaml`.
5. **Comprehensive Logging:** Every significant action logged with structured JSON.
6. **Instrumentation:** Every service exposes Prometheus metrics at `/metrics`.

### Testing Standards

```
Required coverage thresholds:
  Unit tests:         >85% line coverage
  Integration tests:  All critical paths covered
  E2E tests:          All user journeys covered
  
Test pyramid:
  E2E (Playwright):   10% — slow but highest confidence
  Integration:        30% — test service boundaries
  Unit:               60% — fast, cheap, exhaustive
  
Required for every new feature:
  □ Unit tests for all business logic
  □ Integration test for API endpoint
  □ Happy path E2E test
  □ One failure scenario test
  □ Performance benchmark (if latency-sensitive)
```

### Code Quality Gates

```yaml
# .github/workflows/quality.yml
- SonarQube: Quality Gate must pass (0 new critical issues)
- Bandit: No high-severity Python security issues
- Safety: No known vulnerable dependencies
- Black + isort: Code formatting enforced
- Mypy: Type checking at strict level
- Coverage: Must not decrease from baseline
```

## 8.3 Future Expansion Roadmap (V2 and Beyond)

```
V1.0 — Desktop AI Assistant (Months 1-10)
  Single-user, desktop-first, core features

V1.5 — Enhanced Intelligence (Months 11-14)
  - Video understanding (analyze YouTube, Zoom recordings)
  - Browser-native mode (Chrome extension, not just OS-level)
  - Zapier/Make.com integration (1000+ app connectors instantly)
  - Advanced scheduling AI (travel time, energy-aware scheduling)

V2.0 — Team Intelligence (Months 15-22)
  - Multi-user deployment (shared team knowledge base)
  - Team assistant features (meeting notes shared with all attendees)
  - Enterprise SSO (SAML, OIDC)
  - Admin dashboard and policy management
  - Mobile primary app (iOS + Android)

V2.5 — Physical World (Months 23-28)
  - Smart home integration (Matter protocol)
  - IoT device monitoring
  - Wearable companion (Apple Watch, Pixel Watch)
  - Spatial computing (Apple Vision Pro, Meta Quest)

V3.0 — Meta-Intelligent (Months 29-36)
  - Self-improvement: NOVA improves its own code (human-supervised)
  - Autonomous research assistant (days-long research projects)
  - Digital twin simulation (test plans in simulation before execution)
  - Cross-user anonymous learning (privacy-preserving federated learning)
```

---

# 9. SETUP, INTEGRATION & TESTING — STEP-BY-STEP

## 9.1 Prerequisites

```bash
# System Requirements (minimum):
# CPU: 8-core, x86-64 or Apple Silicon
# RAM: 16GB (32GB recommended for local models)
# GPU: NVIDIA RTX 3060+ or Apple M1 Pro+ (optional but recommended)
# Disk: 50GB free (models take 20-40GB)
# OS: macOS 13+, Windows 11, Ubuntu 22.04+

# Software Prerequisites:
# - Python 3.11+ 
# - Node.js 20 LTS
# - Docker Desktop 24+
# - Git 2.40+
# - Rust 1.80+ (for native components)

# Verify prerequisites:
python3 --version    # Should be 3.11+
node --version       # Should be v20+
docker --version     # Should be 24+
git --version        # Should be 2.40+
```

## 9.2 Repository Structure

```
nova/
├── services/
│   ├── brain/              # LLM orchestration, agent framework
│   │   ├── agents/         # Specialist agents (code, research, file, etc.)
│   │   ├── memory/         # Memory system (working, episodic, semantic)
│   │   ├── tools/          # Tool definitions for LangGraph
│   │   └── main.py         # FastAPI app entry point
│   ├── voice/              # STT, TTS, wake word
│   │   ├── stt/            # Speech-to-text engine
│   │   ├── tts/            # Text-to-speech engine  
│   │   ├── wakeword/       # Wake word detection
│   │   └── main.py
│   ├── screen/             # Screen capture and analysis
│   │   ├── capture/        # Screen capture daemon
│   │   ├── analyzer/       # Vision AI analysis
│   │   ├── ocr/            # OCR engine
│   │   └── main.py
│   ├── system/             # OS control and monitoring
│   │   ├── control/        # App/file/settings control
│   │   ├── monitor/        # System metrics
│   │   ├── automation/     # GUI automation
│   │   └── main.py
│   └── security/           # Security monitoring
│       ├── scanner/        # File and network scanning
│       ├── audit/          # Audit logging
│       └── main.py
├── frontend/               # Electron + React app
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── store/          # Zustand state management
│   │   ├── hooks/          # Custom React hooks
│   │   ├── overlay/        # HUD overlay components
│   │   └── App.tsx
│   ├── electron/           # Electron main process
│   └── package.json
├── shared/                 # Shared types, utilities, constants
│   ├── types/              # Pydantic models + TypeScript interfaces
│   └── utils/              # Shared utilities
├── models/                 # Local AI models (not in git, downloaded separately)
│   ├── whisper/            # Faster-Whisper model files
│   ├── llm/                # Ollama models
│   └── tts/                # Piper TTS model files
├── tests/
│   ├── unit/               # Unit tests per service
│   ├── integration/        # Cross-service integration tests
│   └── e2e/                # End-to-end tests (Playwright)
├── infrastructure/
│   ├── docker/             # Dockerfiles
│   ├── k8s/                # Kubernetes manifests (production)
│   └── monitoring/         # Prometheus + Grafana configs
├── scripts/                # Setup, migration, utility scripts
├── docs/                   # Documentation
├── docker-compose.yml      # Development environment
├── docker-compose.staging.yml
└── .github/workflows/      # CI/CD pipelines
```

## 9.3 Initial Setup (Step by Step)

### Step 1: Clone and Configure

```bash
git clone https://github.com/[your-org]/nova.git
cd nova

# Copy environment template
cp .env.example .env

# Edit .env with your API keys
nano .env
```

```bash
# .env file contents:
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...
PICOVOICE_ACCESS_KEY=...

# Database
POSTGRES_PASSWORD=<generate-strong-password>
POSTGRES_DB=nova

# Security
JWT_SECRET=<generate-32-char-random-string>
ENCRYPTION_SALT=<generate-32-char-random-string>

# Optional integrations (add as needed)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
SLACK_BOT_TOKEN=...
```

### Step 2: Download Local Models

```bash
# Run the model download script
python scripts/download_models.py

# This downloads:
# 1. Faster-Whisper large-v3 (~3GB)
# 2. Piper TTS voice model (~100MB)
# 3. Sentence transformer for embeddings (~90MB)
# 4. Optional: LLaMA 3.1 70B via Ollama (~40GB, only if running fully local)

# Model download script:
# scripts/download_models.py

import os
from faster_whisper import WhisperModel
import requests
from pathlib import Path

def download_whisper():
    print("Downloading Whisper large-v3...")
    model = WhisperModel("large-v3", download_root="./models/whisper")
    print("✓ Whisper downloaded")

def download_piper():
    print("Downloading Piper TTS model...")
    models_dir = Path("./models/tts")
    models_dir.mkdir(parents=True, exist_ok=True)
    
    url = "https://github.com/rhasspy/piper/releases/download/v1.2.0/voice-en-us-ryan-high.tar.gz"
    response = requests.get(url, stream=True)
    with open(models_dir / "ryan-high.tar.gz", "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    os.system(f"tar -xzf {models_dir}/ryan-high.tar.gz -C {models_dir}/")
    print("✓ Piper TTS downloaded")

def setup_ollama_local():
    """Optional: Install Ollama and pull LLaMA for fully local operation."""
    print("Setting up Ollama for local LLM...")
    os.system("curl -fsSL https://ollama.ai/install.sh | sh")
    os.system("ollama pull llama3.1:70b")
    print("✓ Ollama + LLaMA 3.1 70B ready")

if __name__ == "__main__":
    download_whisper()
    download_piper()
    # Uncomment for fully local mode:
    # setup_ollama_local()
    print("\n✓ All models downloaded. Run 'docker-compose up' to start NOVA.")
```

### Step 3: Start Development Environment

```bash
# Start all services
docker-compose up -d

# Watch logs
docker-compose logs -f

# Verify all services healthy
docker-compose ps
# Expected output:
# nova-redis      Up (healthy)
# nova-postgres   Up (healthy)  
# nova-brain      Up (healthy)
# nova-voice      Up (healthy)
# nova-screen     Up (healthy)
# nova-api        Up (healthy)

# Run database migrations
docker-compose exec nova-brain python scripts/migrate.py
```

### Step 4: Install Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start in development mode (hot reload)
npm run dev

# This starts:
# - Electron desktop app
# - React dev server (Vite, port 3000)
# - WebSocket connection to nova-api
```

### Step 5: Platform-Specific System Permissions

#### macOS:
```bash
# NOVA requires these permissions — grant in System Settings > Privacy & Security:
# 1. Microphone Access
# 2. Screen Recording (for screen capture)
# 3. Accessibility (for GUI automation)
# 4. Automation (to control other apps)

# Script to verify permissions:
python scripts/check_permissions_macos.py
```

```python
# scripts/check_permissions_macos.py
import subprocess
import sys

def check_macos_permissions():
    checks = {
        "Microphone": "microphone",
        "Screen Recording": "screen-recording", 
        "Accessibility": "accessibility",
    }
    
    all_ok = True
    for name, perm in checks.items():
        result = subprocess.run(
            ["osascript", "-e", f'tell application "System Events" to return accessibility enabled'],
            capture_output=True, text=True
        )
        status = "✓" if "true" in result.stdout.lower() else "✗ NEEDS GRANT"
        print(f"{status} {name}")
        if "✗" in status:
            all_ok = False
    
    if not all_ok:
        print("\nGo to System Settings > Privacy & Security to grant missing permissions.")
        sys.exit(1)
    else:
        print("\nAll permissions granted. NOVA is ready.")

check_macos_permissions()
```

#### Windows:
```powershell
# Run as Administrator to grant required permissions
# NOVA requires:
# 1. Microphone access (Settings > Privacy > Microphone)
# 2. UI Automation access (no special setting needed, but requires non-elevated execution)

# Enable developer mode for full feature access
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock" `
                 -Name "AllowDevelopmentWithoutDevLicense" -Value 1
```

#### Linux (Ubuntu):
```bash
# Required packages
sudo apt-get install -y \
    portaudio19-dev \      # Audio
    python3-xlib \         # X11 control
    xdotool \              # Window management
    at-spi2-core \         # Accessibility
    scrot                  # Screenshots

# Add user to audio group
sudo usermod -a -G audio $USER

# Enable accessibility
gsettings set org.gnome.desktop.interface toolkit-accessibility true
```

### Step 6: Run Test Suite

```bash
# Unit tests
cd services/brain
python -m pytest tests/unit/ -v --cov=. --cov-report=html
# Expected: 85%+ coverage, all tests green

# Integration tests (requires running services)
python -m pytest tests/integration/ -v --timeout=30

# Voice subsystem test
python -m pytest services/voice/tests/ -v -m "not hardware"

# E2E tests (requires Playwright + running frontend)
cd tests/e2e
npx playwright test --reporter=html

# Performance benchmarks
python scripts/benchmark.py
# Expected outputs:
# Wake word detection: 45ms avg ✓
# STT transcription: 1.2s avg (30s audio) ✓  
# Screen analysis: 2.8s avg ✓
# End-to-end voice response: 1.8s avg ✓
```

### Step 7: Configure Google OAuth (Email + Calendar)

```python
# scripts/setup_google_auth.py
# Run this once to set up OAuth for Gmail and Google Calendar

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import os

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar"
]

def setup_google_auth():
    creds = None
    token_path = os.path.expanduser("~/.nova/google_token.pickle")
    
    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials/google_oauth_client.json",  # Download from Google Cloud Console
            SCOPES
        )
        creds = flow.run_local_server(port=0)
        
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)
    
    print("✓ Google authentication configured")
    print(f"✓ Token stored at {token_path}")

setup_google_auth()
```

## 9.4 Monitoring Setup

```bash
# Start monitoring stack
docker-compose -f docker-compose.monitoring.yml up -d

# Access Grafana dashboard
open http://localhost:3001
# Username: admin, Password: nova-admin (change immediately)

# Import NOVA dashboard
# In Grafana: Dashboards > Import > Upload JSON
# File: infrastructure/monitoring/nova-dashboard.json

# Key metrics to monitor:
# - nova_response_latency_seconds (target: p95 < 2.0)
# - nova_screen_analysis_latency_seconds (target: p95 < 5.0)
# - nova_agent_success_rate (target: > 0.85)
# - nova_api_errors_total (target: < 1% error rate)
# - nova_memory_usage_bytes (alert: > 6GB)
# - nova_active_sessions (informational)
```

---

# 10. APPENDICES

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| AST | Abstract Syntax Tree — structured representation of source code |
| ChromaDB | Open-source vector database for storing and searching embeddings |
| Diarization | Identifying who is speaking in audio with multiple speakers |
| Embedding | Dense numerical vector representation of text for semantic search |
| HNSW | Hierarchical Navigable Small World — efficient ANN algorithm used by vector DBs |
| LangGraph | Graph-based framework for building stateful multi-agent workflows |
| LiteLLM | Unified Python library for calling 100+ LLM APIs with consistent interface |
| Ollama | Tool for running large language models locally on consumer hardware |
| Perceptual Hash | Compact fingerprint of an image for detecting visual similarity |
| PyO3 | Rust library for writing Python extension modules in Rust |
| RAG | Retrieval-Augmented Generation — combining search with LLM generation |
| SSML | Speech Synthesis Markup Language — controls TTS pronunciation, pitch, pace |
| TTS | Text-to-Speech — converting text to spoken audio |
| VAD | Voice Activity Detection — detecting presence of speech in audio stream |
| WER | Word Error Rate — STT accuracy metric (lower is better) |

## Appendix B: Performance Benchmarks (Targets)

| Operation | Target (P50) | Target (P95) | Measurement Method |
|-----------|-------------|-------------|-------------------|
| Wake word detection | 45ms | 150ms | Porcupine built-in |
| STT transcription (5s audio) | 800ms | 1.5s | Before/after timestamps |
| Screen analysis (Claude Vision) | 2s | 4s | API response time |
| Screen analysis (Local LLaVA) | 400ms | 800ms | Model inference time |
| LLM response (first token) | 300ms | 800ms | Time to first streamed token |
| End-to-end voice round-trip | 1.5s | 2.5s | Wake word → TTS starts |
| Task planning | 2s | 5s | Goal received → plan shown |
| Simple file operation | 500ms | 1s | Command → file modified |
| Email send | 2s | 5s | Command → email in sent |
| Memory retrieval | 20ms | 100ms | Query → results returned |

## Appendix C: Common Failure Modes and Mitigations

| Failure | Likelihood | Impact | Mitigation |
|---------|-----------|--------|-----------|
| LLM API timeout | Medium | High | Local model fallback, retry with backoff |
| Wake word false positive | Low-Medium | Low | Confirmation prompt before sensitive actions |
| Screen analysis misidentification | Medium | Low | Always show analysis to user, easy correction |
| GUI automation click miss | Medium | Medium | Verify state after action, retry logic |
| Memory context drift | Low | Medium | Periodic context summarization, explicit memory commands |
| Runaway task cost | Low | High | Token budget enforced per-task and per-day |
| System permission revoked | Low | High | Check permissions on startup, graceful degradation |
| Audio feedback loop | Low | Medium | Echo cancellation, headphone mode |

## Appendix D: External API Rate Limits and Costs

| Service | Rate Limit | Cost | Notes |
|---------|-----------|------|-------|
| Claude 3.5 Sonnet | 50K TPM (Tier 1) | $3/$15 per 1M tokens in/out | Primary LLM |
| Claude 3 Haiku | 50K TPM | $0.25/$1.25 per 1M tokens | Fast/cheap tasks |
| OpenAI Whisper | 500 reqs/min | $0.006/minute audio | Cloud STT fallback |
| ElevenLabs | 20K chars/day (free), unlimited (paid) | $22/month (Creator) | Cloud TTS |
| Google Gmail | 10K requests/day | Free (below quota) | Email integration |
| Google Calendar | 10K requests/day | Free (below quota) | Calendar integration |
| Serper (Search) | 2500 reqs/month (free) | $50/month (50K reqs) | Web search |

## Appendix E: Recommended Hardware Configurations

**Minimum (Cloud-dependent mode):**
- CPU: Apple M1 or Intel Core i7 (8th gen+)
- RAM: 16GB
- Disk: 20GB free
- GPU: Not required
- Expected cost: ~$50/month API costs for heavy use

**Recommended (Hybrid mode):**
- CPU: Apple M2 Pro / AMD Ryzen 9 7900X / Intel Core i9-13900K
- RAM: 32GB
- Disk: 100GB NVMe SSD
- GPU: NVIDIA RTX 3080 / Apple M2 Pro integrated
- Expected cost: ~$20/month API costs (smaller models run locally)

**Optimal (Fully local mode):**
- CPU: Apple M3 Max / Intel Core i9 / AMD Threadripper
- RAM: 64GB
- Disk: 500GB NVMe SSD
- GPU: NVIDIA RTX 4090 (24GB VRAM) for fast local inference
- Expected cost: ~$0/month API costs (everything runs locally)

---

## Final Notes for the Development Team

### The 10 Things Most Likely to Go Wrong

1. **Audio device conflicts** — Multiple apps competing for microphone. Solution: Request exclusive microphone access or use virtual audio routing.

2. **Screen capture permission on macOS** — Users forget to grant Screen Recording permission and wonder why NOVA "can't see." Build a first-run permissions wizard.

3. **LLM response inconsistency** — Different LLM responses on identical inputs break deterministic testing. Solution: Set `temperature=0` for all structured outputs, use `temperature=0.7` only for conversational responses.

4. **Context window blow-out** — Long tasks generate thousands of tokens, hitting context limits mid-execution. Solution: Implement the hierarchical context compression from Section 8.1 before launch.

5. **GUI automation fragility on Windows** — Windows UI Automation is more reliable than PyAutoGUI on Windows. Use it as the primary automation method on Windows, fall back to PyAutoGUI for operations not supported.

6. **Wake word false positives on unusual names** — "NOVA" is relatively rare so false positives are low, but in meetings with people named Nova this will trigger constantly. Implement pause-on-video-call detection.

7. **Database schema migrations** — As NOVA evolves, schema changes will break running instances. Implement Alembic migrations from Day 1 and never modify schema outside migrations.

8. **Cost overruns from screen analysis** — If every frame triggers Claude Vision, costs explode. The change detection + tiered analysis system is not optional — implement it in Sprint 5 before enabling continuous screen monitoring.

9. **Privacy perception vs. reality** — Users (and their colleagues) will be uncomfortable knowing NOVA is watching the screen. Build privacy indicators (clear visual state of when screen is/isn't being analyzed), make it easy to pause, and let users configure exactly what is captured.

10. **Scope creep on autonomous tasks** — NOVA will occasionally do things that are 90% right but 10% wrong in a way that causes real problems (deletes wrong file, sends email to wrong person). Implement irreversibility detection from Sprint 1 and make confirmation dialogs clear and non-bypassable for destructive actions.

---

*Document prepared for the NOVA development team. All technical specifications are subject to revision based on development findings. Treat this document as a living specification — update it as decisions are made.*

*Classification: CONFIDENTIAL — Covered by NDA. Do not distribute outside the development team.*

---

**END OF DOCUMENT**

*Version 1.0.0 | 40-Week Development Plan | 20 Sprints | 7-Person Team*
