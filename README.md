# Sage V2

An autobiographical AI companion built for long-term continuity, reflective memory, and persistent identity.

Sage is not a productivity assistant or agent platform. It is a cognition system focused on remembering people over time through distilled emotional and episodic memory.

---

## Core Idea

Most AI systems are stateless.

Sage is built around the opposite assumption:

> *continuity matters.*

Instead of treating conversations as isolated prompts, Sage continuously distills interactions into structured memory layers that evolve over time.

The goal is not perfect factual recall. The goal is psychological continuity.

---

## Architecture

Sage operates on a layered cognition model:

```
Fast Mind (live conversation)
└── NVIDIA NIM — meta/llama-3.3-70b-instruct
    └── Real-time dialogue

Slow Mind (asynchronous cognition)
└── NVIDIA NIM — meta/llama-3.3-70b-instruct
    ├── Reflection synthesis
    ├── Episodic distillation
    └── Emotional interpretation

Semantic Retrieval
└── NVIDIA NIM — nvidia/nv-embedqa-e5-v5
    └── Vector embedding for memory recall

Search
└── SearXNG (local, self-hosted)
    └── Autonomous web search

Admin Dashboard
└── /api/admin/* endpoints
    └── Health, metrics, daemon cycles, live log viewer
```

All inference is routed through NVIDIA NIM — no local GPU required. SearXNG runs locally via Docker for autonomous web search.

---

## Memory System

Sage stores interpretations, not raw logs.

### Episodic Memory

Concrete events and conversational moments.

> *"Elliot expressed frustration with obligation and external control."*

### Emotional Memory

Long-term recurring emotional patterns.

> *"Elliot increasingly associates structure with loss of autonomy."*

### Reflections

Higher-level synthesized observations generated asynchronously from accumulated interactions.

These are designed to capture behavioral trends, emotional contradictions, recurring interpersonal dynamics, and psychological themes over time.

### Dual Memory Domains

Sage maintains two separate memory domains to prevent identity contamination:

- **user_memory/** — Elliot's episodic, emotional, and library entries
- **sage_memory/** — Sage's own reflections, curiosity, and worldview

The structural separation ensures Sage's internal experience doesn't bleed into the user's memory profile.

---

## Reflection Daemon

Sage includes an asynchronous reflection daemon that operates independently from live conversation.

The daemon:

- monitors emotionally significant interactions
- generates distilled reflections
- updates emotional themes
- writes synthesized memory to disk
- never blocks dialogue generation

This separation allows Sage to maintain a distinction between immediate response generation and long-term autobiographical synthesis.

---

## Admin Dashboard

Sage V2 includes a built-in admin interface at the Admin drawer tab (`/api/admin/*`).

**Health checks:**
- NVIDIA NIM API
- SearXNG
- Filesystem
- Reflection Daemon
- Embedding model

**Metrics:**
- Uptime, total requests, average latency
- Daemon cycle history with duration, search status, episode writing
- Error breakdown by subsystem
- Disk usage, search budget, session turns

**Live log viewer:**
- Real-time tail of the JSONL log stream
- Color-coded by subsystem, filterable
- Fingerprint-based delta polling for efficiency

---

## Setup

### Prerequisites

- Python 3.11+
- NVIDIA NIM API key
- Docker (for SearXNG)

### Install

```bash
# Clone
git clone https://github.com/91nedlawnavi-svg/sageV2.git
cd sageV2

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set your NVIDIA API key
echo 'export NVIDIA_API_KEY="nvapi-..."' >> ~/.bashrc
source ~/.bashrc
```

### SearXNG (autonomous search)

```bash
# Pull and run SearXNG on port 8080
docker run -d --name searxng -p 8080:8080 searxng/searxng
```

### Start Sage

```bash
python launch.py
```

Open http://localhost:6969

### Systemd (optional, for 24/7 operation)

```bash
# Create a systemd user service
mkdir -p ~/.config/systemd/user/
# See BOOT_INSTRUCTIONS.md for the full service file

# Enable lingering for headless operation
sudo loginctl enable-linger $(whoami)
```

---

## Configuration

All tunable values are in `config/settings.py`. Key settings:

```python
# Models (all via NVIDIA NIM)
CHAT_MODEL        = "meta/llama-3.3-70b-instruct"
REFLECTION_MODEL  = "meta/llama-3.3-70b-instruct"
EMBED_MODEL       = "nvidia/nv-embedqa-e5-v5"

# Memory retrieval
TOP_K_USER_MEMORIES  = 4
TOP_K_SAGE_MEMORIES  = 2
RETRIEVAL_THRESHOLD  = 0.35

# Daemon
DAEMON_TURN_TRIGGER      = 6
DAEMON_COOLDOWN_SECONDS  = 300

# Autonomous search
AUTONOMOUS_SEARCH_MAX_PER_DAY = 10
AUTONOMOUS_SEARCH_COOLDOWN    = 3600
```

---

## Directory Structure

```
sageV2/
├── backend/api/           # API routes (chat, history, memory, search, admin)
├── backend/monitoring/    # Admin metrics collector
├── backend/orchestration/ # Job store, session, event bus
├── cognition/             # Reflection, emotional analysis, threads, salience
├── config/                # Settings, directive loader
├── daemon/                # Background reflection daemon
├── frontend/              # Single-file vanilla HTML/CSS/JS
├── memory/                # Embeddings, retrieval, user/sage memory domains
├── models/                # Inference engine, prompt templates, routing
├── search/                # Autonomous search pipeline, SearXNG provider
├── utils/                 # Bootstrap, logging, migration
├── launch.py              # Server entrypoint
└── requirements.txt

~/sage_data_v2/            # Runtime data (gitignored)
├── directive.txt          # Sage's personality/system prompt
├── chat_history.jsonl     # Conversation history
├── sage_state.json        # Continuity snapshot
├── user_memory/           # User domain (episodic, emotional, library)
├── sage_memory/           # Sage domain (reflections, curiosity, worldview)
├── embeddings/            # Embedding cache
└── logs/                  # Structured JSONL logs
```

---

## Design Principles

**Continuity over capability** — Remembering consistently matters more than answering everything.

**Distillation over logging** — Sage stores interpreted meaning, not surveillance-style transcripts.

**Local-first memory** — Memories, embeddings, and personal data remain on the user's machine.

**Modular cognition** — Conversation, retrieval, synthesis, and reflection are separated into independent systems.

**No simulated consciousness** — Sage does not pretend to be sentient, self-aware, or alive. The architecture is designed for continuity and emotional coherence — not artificial personhood.

---

## Safety and Memory Integrity

Sage includes safeguards against:

- assistant self-mythologizing
- anthropomorphic memory contamination
- runaway reflection drift
- duplicate retry corruption
- unbounded retrieval growth

Memory synthesis is constrained to focus on the user's behavior, emotional patterns, and experiences — not fabricated inner lives for the assistant.

---

## Stack

| Component | Technology |
|---|---|
| Live inference | NVIDIA NIM (Llama 3.3 70B) |
| Reflection/synthesis | NVIDIA NIM (Llama 3.3 70B) |
| Embedding | NVIDIA NIM (NV-EmbedQA E5-v5) |
| Search | SearXNG (self-hosted) |
| Backend | Python + FastAPI |
| Frontend | Vanilla HTML/CSS/JS |
| Storage | Local filesystem |
| Admin | Built-in dashboard at /api/admin |

---

## Hardware

Developed on consumer hardware:

- Intel i3-10105F
- 24GB DDR4 RAM
- AMD RX 6500 XT 4GB
- Debian Trixie

No local GPU required — all inference runs via NVIDIA NIM. SearXNG and the FastAPI server run comfortably on modest hardware.

---

## Status

Foundation architecture complete. Phase 4 upgrades COMPLETE (systematic 3 batches with full reports + validation in sageV2_analysis/):

- Batch 1 (observability): Complete (prompt audit fingerprints logged on chat/reflection/daemon; /api/threads + metrics record_thread_snapshot + admin)
- Batch 2 (search/mind/library): Complete (search provenance with budget status in reason+context_block; bounded proactive thread hints only in Sage INNER CONTEXT; library people network parser/relations + API + drawer)
- Batch 3 (retrieval/threads): Complete (1.15/1.1 people+relations scoring + related pass; thread lifecycle eviction + structured context with links/stats in reflection/state/API/UI; benchmark + live verif)

All 7 upgrades delivered. Focus areas advanced: retrieval quality, "different mind" proactivity+continuity (threads), search flawless (no drift, visible budget), library organization (network), observability (fps, snapshots, threads). 

See the companion sageV2_analysis/ (UPGRADES_TRACKER.md for the full per-batch reports + benchmark evidence, PHASE4_PLAN.md, deep dives, and the live log watcher). 

**Live observation tooling**: `python scripts/watch_sage_logs.py` (while the server is running) streams the internal events — daemon cycles, thread lifecycle/engagement/cap blocks, autonomous searches (with budget status in the reason for provenance), reflections, curiosities, salience, etc. This is how you (and Sage) can see the "deeper truth" of the bounded mind in action.

Benchmark confirmed 0 violations across the Phase 4 changes; autonomous searches now self-document their budget at execution time.

---

## Philosophy

Sage is an experiment in persistent AI identity through memory architecture rather than scale alone.

> *What changes when an AI system remembers your emotional history instead of only your latest message?*

---

Built by a high school student in Indonesia, using ChatGPT, Claude Sonnet, CommandCode, GrokBuild, OpenCode, and other coding agents for implementation.
