# Sage V1 → V2 Migration Notes

## What Changed

### The Core Structural Change: Dual Memory Domains

V1 had one undifferentiated memory pool. Every memory file — episodic events,
emotional themes, library entries, and reflections — lived in `~/sage/` with
no distinction between "Elliot's memories" and "Sage's own inner life."

V2 introduces two explicit, hard-separated domains:

| Domain | Root | Owner | What it holds |
|--------|------|-------|----------------|
| **user** | `~/sage_data_v2/user_memory/` | Elliot | Episodic events, emotional themes, library entries (people/places/topics), user-domain reflections |
| **sage** | `~/sage_data_v2/sage_memory/` | Sage | Her own reflections, curiosity journal, evolving worldview, search log |

**Why this matters:** In V1, there was a documented bug where the model could
read its own roleplay persona-descriptions as if they were biographical fact
about Elliot. V2's boundary prevents this contamination structurally —
Sage's self-cognition never mixes with Elliot's memory in the same retrieval pool.

---

## File Path Changes

### V1 → V2 Mapping

```
V1 ~/sage/episodic/         →  V2 ~/sage_data_v2/user_memory/episodic/
V1 ~/sage/emotional/        →  V2 ~/sage_data_v2/user_memory/emotional/
V1 ~/sage/library/          →  V2 ~/sage_data_v2/user_memory/library/
V1 ~/sage/reflections/      →  V2 ~/sage_data_v2/user_memory/reflections/
V1 ~/sage/embeddings/       →  V2 ~/sage_data_v2/embeddings/  (shared)
V1 ~/sage/directive.txt     →  V2 ~/sage_data_v2/directive.txt
V1 ~/sage/chat_history.jsonl→  V2 ~/sage_data_v2/chat_history.jsonl

NEW in V2:
~/sage_data_v2/sage_memory/reflections/   (Sage's inner life)
~/sage_data_v2/sage_memory/curiosity/     (curiosity journal)
~/sage_data_v2/sage_memory/worldview/     (synthesized topic knowledge)
~/sage_data_v2/sage_memory/search_log/    (autonomous search records)
~/sage_data_v2/search_budget.json         (daily search budget)
~/sage_data_v2/sage_state.json            (version + domain info)
```

---

## Migration Steps

### Automated (recommended)

```bash
cd ~/sage
python utils/migrate_v1.py
```

This copies all V1 `.txt` files into their V2 user-domain equivalents.
V1 source files are **never touched**. Run it multiple times safely — it skips
files that already exist at the destination.

Embedding cache files (`*.json`) are also copied — their hash keys are
identical between V1 and V2 so the embedding cache warms instantly.

### Manual step required

The migration script does not copy `directive.txt` automatically because
some users have separate directives for different contexts.

```bash
cp ~/sage/directive.txt ~/sage_data_v2/directive.txt
```

If you don't do this, V2 will create a minimal default directive and warn you.

### Chat history

V2 uses the same JSONL format as V1. You can copy it directly:

```bash
cp ~/sage/chat_history.jsonl ~/sage_data_v2/chat_history.jsonl
```

This is optional — the system works fine without prior history.

---

## Module Path Changes for Developers

### Removed in V2

These V1 modules do not exist in V2 — their responsibilities were split:

| V1 module | V2 replacement |
|-----------|----------------|
| `memory/storage.py` | `memory/storage/base.py` + `memory/storage/history.py` |
| `memory/episodic.py` | `memory/user/episodic.py` |
| `memory/emotional.py` | `memory/user/emotional.py` |
| `memory/retrieval.py` | `memory/retrieval/user_retrieval.py` + `memory/retrieval/sage_retrieval.py` |
| `memory/embeddings.py` | `memory/embeddings/cache.py` |
| `cognition/synthesis.py` | `cognition/user_model/synthesis.py` + `cognition/sage_model/synthesis.py` |
| `cognition/emotional_analysis.py` | `cognition/emotional/user_emotional.py` |
| `cognition/library_extraction.py` | `cognition/user_model/library_extraction.py` |
| `cognition/reflection.py` | `cognition/reflection/pipeline.py` |
| `models/prompts.py` | `models/prompts/templates.py` |
| `models/inference.py` | `models/inference/engine.py` |
| `daemon/reflection_daemon.py` | `daemon/reflection_daemon.py` (rewritten, same path) |

### V1 `launch.py` → V2 `launch.py`

V1's `launch.py` was ~500 lines containing: Flask routes, session state,
inference calls, prompt assembly, daemon startup, and embedding retrieval.

V2's `launch.py` is ~80 lines. It:
- Creates shared objects (JobStore, Session, AsyncClient)
- Injects them into their respective modules
- Registers routes
- Starts the daemon
- Starts uvicorn

Everything else is in the module that owns it.

---

## Behavioral Differences

### What is identical to V1
- Episodic memory extraction prompts (word-for-word preserved)
- Emotional theme extraction and merge prompts
- Library extraction and merge prompts
- User-domain reflection prompts
- Embedding model and cosine similarity logic
- Retrieval threshold and top-k values (tunable in `config/settings.py`)
- Chat model parameters
- Daemon trigger conditions (turn count + emotional keywords)

### What is new in V2
- **Sage's own reflections** — she generates first-person internal reflections
  about her experience after each daemon cycle
- **Curiosity journal** — Sage records topics she finds herself drawn to
- **Worldview synthesis** — after autonomous searches, Sage integrates findings
  into her own evolving perspective
- **Dual retrieval** — both user memories AND sage memories are independently
  searched and injected into the chat prompt, with clearly labeled provenance
- **Structured search context** — search results are summarised and wrapped in
  a labeled context block instead of being pasted raw (fixes the V1 identity
  drift bug)
- **Event bus** — subsystems communicate through `publish`/`subscribe` instead
  of direct function calls or module-level globals
- **Search budget** — autonomous searches are capped at 10/day with 1-hour
  cooldown, enforced via `search_budget.json`

### What is NOT in V2 Phase 1
- Autonomous execution beyond search (no file writes, no external actions)
- Multi-user sessions
- WebSocket push (still uses polling)
- Contradiction detection in memory
- Phase 2 curiosity-driven planning

---

## Dependency Changes

V1 used Flask. V2 uses FastAPI + uvicorn.

| V1 | V2 |
|----|----|
| `flask` | `fastapi`, `uvicorn[standard]` |
| `requests` | `httpx` (async) |
| `threading.Thread` (daemon) | `asyncio.Task` |
| *(no search)* | `duckduckgo-search` |

Install V2 dependencies:
```bash
pip install -r requirements.txt
```

The local model stack (llama.cpp on ports 8081/8082) is unchanged.
