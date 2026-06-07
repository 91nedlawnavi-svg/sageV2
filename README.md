# Sage

> Formerly known as SageV2 during its architectural maturation (Phases 1–4). The name was simplified after the core "V2" foundations (dual memory domains, bounded threads, provenanceful search, local embeddings, observability) were stabilized.

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

Sage uses a dual-tempo cognition system plus supporting structures developed through Phase 4:

**Fast Mind** (live conversation)
- NVIDIA NIM — meta/llama-3.3-70b-instruct
- Real-time dialogue with memory retrieval injected at prompt time

**Slow Mind** (asynchronous cognition)
- Reflection daemon (triggered by conversation volume or emotional signals)
- Thread-based "different mind": bounded longitudinal threads (nascent/active/dormant/resolved) that give Sage its own narrative continuity, curiosity, and worldview
- Synthesis pipelines for reflections, emotional patterns, and state

**Embeddings & Retrieval**
- Primary: local llama.cpp server (intfloat/e5-mistral-7b-instruct Q5_K_M.gguf)
  - `--embedding --pooling mean -ngl 18` on port 8081
  - Managed by user systemd service (`systemd/user/llama-embedder.service`)
- Code-level fallback support for NIM embeddings in `memory/embeddings/cache.py`
- Dual retrieval (user + sage domains) with cosine + salience, library/people/relations boosts, threshold gating, and anti-attractor logic

**Search (with provenance & budget)**
- Providers: SearXNG (self-hosted) and DuckDuckGo
- Autonomous searches capped at 10/day + 1-hour cooldown
- Every Sage-initiated search carries full labeled provenance (initiator, reason, budget status) into context

**Library Network**
- Structured user knowledge (people / places / topics) with parsed relations and groups
- Feeds both retrieval scoring and the interactive force-directed People Network graph in the UI

**Frontend**
- Single vanilla HTML/JS file (`frontend/index.html`)
- Chat, Library drawer (tree + live editor), People Network (SVG force + drag), Sage "Inner" tab (threads + state), Admin metrics + live log tail

**Admin & Observability**
- `/api/admin/*`, `/api/threads`, `/api/people/network`, prompt fingerprints on all LLM calls, thread snapshots, daemon metrics, `scripts/watch_sage_logs.py` for live internal event streaming

The architecture keeps strict domain separation (user_memory vs sage_memory), read-only metadata injection, and bounded autonomy.

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
- NVIDIA NIM API (chat/reflection)
- Search providers
- Filesystem
- Reflection Daemon
- Embedding model (local llama-server)
- Thread caps & lifecycle

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
- NVIDIA NIM API key (for chat + reflection; embeddings are local by default)
- A built llama.cpp with `llama-server` (for the local embedder) or use the provided unit as reference
- (Optional) Docker for a self-hosted SearXNG instance if you prefer it over the DuckDuckGo provider

### Install

```bash
# Clone
git clone https://github.com/91nedlawnavi-svg/sage.git
cd sage

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set your NVIDIA API key (chat + reflection)
echo 'export NVIDIA_API_KEY="nvapi-..."' >> ~/.bashrc
source ~/.bashrc
```

### Start Sage

```bash
python launch.py
```

Open http://localhost:6969

### Embedder (required for local retrieval)

The hot-path embedder runs as a user systemd service:

```bash
# Copy the unit (already in repo)
mkdir -p ~/.config/systemd/user/
cp systemd/user/llama-embedder.service ~/.config/systemd/user/

# Reload, enable, and start
systemctl --user daemon-reload
systemctl --user enable --now llama-embedder.service

# Enable lingering so it starts on boot even without a login session
sudo loginctl enable-linger $(whoami)

# Check status
systemctl --user status llama-embedder.service
journalctl --user -u llama-embedder.service -f
```

The service runs the exact model used by the engine:
`/home/elliot/models/e5-mistral-7b-instruct-Q5_K_M.gguf` with `-ngl 18 --pooling mean`.

### Main server (24/7)

```bash
# Enable lingering (once)
sudo loginctl enable-linger $(whoami)

# Create a user service for launch.py (see BOOT_INSTRUCTIONS.md or create your own)
# Then: systemctl --user enable --now sage.service
```

See the `systemd/user/` directory in the repo for the embedder example.

---

## Configuration

All tunable values are in `config/settings.py`. Key settings:

```python
# Models
# Chat + reflection via NVIDIA NIM
CHAT_MODEL        = "meta/llama-3.3-70b-instruct"
REFLECTION_MODEL  = "meta/llama-3.3-70b-instruct"

# Embeddings: local llama.cpp recommended (see systemd/user/llama-embedder.service)
# cache.py handles the e5 asymmetric prefixes and has NIM fallback logic
EMBED_MODEL       = "e5-mistral-7b-instruct"  # local via llama.cpp; NIM fallback supported in cache.py

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
sage/
├── backend/api/           # API routes (chat, history, memory, search, admin, directive)
├── backend/monitoring/    # Admin metrics, thread snapshots
├── backend/orchestration/ # Job store, session, event bus
├── cognition/             # Reflection, emotional, threads (assignment + store), salience, synthesis, meta
├── config/                # settings.py, directive loader (hot-reload)
├── daemon/                # reflection_daemon.py (the Slow Mind)
├── frontend/              # Single-file vanilla app (chat + Library + People Network graph + Inner + Admin)
├── memory/                # embeddings/cache.py, retrieval (user + sage), user/ + sage/ domains, library
├── models/                # inference, prompts/templates (with fingerprints), routing
├── search/                # pipeline + autonomy (budget, trigger) + providers (searxng, duckduckgo) + summarizer
├── scripts/               # watch_sage_logs.py (live internal event observer)
├── systemd/user/          # llama-embedder.service (example user service)
├── utils/                 # bootstrap, logging, migrate_v1
├── validation/            # invariants.md
├── launch.py              # Server entrypoint
├── PHASE4_RETROSPECTIVE.md
├── PHASE5_SCOPING.md
├── README.md
└── requirements.txt

~/sage_data_v2/            # Runtime data (gitignored)
├── directive.txt          # Sage's personality/system prompt (immutable substrate)
├── chat_history.jsonl
├── sage_state.json
├── search_budget.json     # autonomous search counters
├── user_memory/           # Elliot only (episodic, emotional, reflections, library/people+places+topics)
├── sage_memory/           # Sage only (reflections, curiosity, worldview, search_log)
├── embeddings/            # model-namespaced cache
└── logs/                  # daily JSONL (structured, fingerprint-aware)
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
| Embedding | Local (llama.cpp e5-mistral-7b Q5_K_M, -ngl 18) or NIM fallback |
| Search | SearXNG (self-hosted) or DuckDuckGo provider (with autonomy budget + provenance) |
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

Chat + reflection run via NVIDIA NIM (large models; no local GPU required for them).
Embeddings run locally via llama.cpp (e5-mistral-7b Q5_K_M with -ngl 18 hybrid offload on the RX 6500 XT) for lowest latency on the retrieval hot path. NIM fallback supported in `memory/embeddings/cache.py`.
SearXNG (or DuckDuckGo provider) and the FastAPI server run comfortably on modest hardware.

---

## Status

**Phase 4 is complete and published.**

The 7 systematic upgrades were executed in 3 batches with reports, validation (0 invariant violations on benchmark), and full respect for existing invariants (dual memory domains, read-only thread metadata, bounded search autonomy, Phase 3B thread caps, provenance everywhere).

Key advances:
- Observability (prompt fingerprints on every LLM call, `/api/threads`, thread snapshots in metrics/daemon, live `scripts/watch_sage_logs.py`)
- "Different mind" (bounded proactive threads for Sage's own longitudinal narrative/curiosity/worldview, injected read-only into INNER CONTEXT only)
- Search (flawless provenance + budget visibility for autonomous runs; 10/day cap + cooldown; labeled context blocks)
- Library network (people + relations/groups parsed from notes; boosted in retrieval; interactive force+drag graph in UI)
- Retrieval quality (E5 prefix correctness, model-namespaced cache to prevent cross-embedder corruption, compounding people/relations boosts, noise removal)
- Thread lifecycle hygiene + richer structured context feeding reflection, state, APIs, and frontend

**Post-implementation audit fixes** (cache key namespacing + fail-safe cosine, correct asymmetric query/passage embeddings for the local e5 model, boost compounding, frontend graph/click robustness, docs reality alignment) were applied and included in the final snapshot.

**Phase 4 Closure**: See `PHASE4_RETROSPECTIVE.md` (in-repo) for the full story. Detailed batch evidence, deep dives, and tracker live in the separate `~/sage_analysis/` workspace (per project structure).

**Live observation**: `python scripts/watch_sage_logs.py` while the server runs — streams daemon cycles, thread state changes, autonomous search reasons (with budget), retrieval events, etc. This is the practical way to see the deeper truth of the bounded mind.

**Git Snapshot**: Tag `phase4-complete` points to the post-audit finished state.  
GitHub Release: https://github.com/91nedlawnavi-svg/sage/releases/tag/phase4-complete  
Only `main` branch (old phase branches cleaned).

---

## Philosophy

Sage is an experiment in persistent AI identity through memory architecture rather than scale alone.

> *What changes when an AI system remembers your emotional history instead of only your latest message?*

---

Built by a high school student in Indonesia, using ChatGPT, Claude Sonnet, CommandCode, GrokBuild, OpenCode, and other coding agents for implementation.
