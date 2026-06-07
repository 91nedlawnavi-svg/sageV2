# Sage V2 — Boot Instructions

## Prerequisites

- Python 3.11+
- NVIDIA NIM API key (used for all inference: chat, reflection, and embedding)

## Installation

```bash
# 1. Clone / copy the sage directory to your home
cd ~/sage

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Set your NVIDIA API key
echo 'export NVIDIA_API_KEY="nvapi-..."' >> ~/.bashrc
source ~/.bashrc

# 4. (First time only) Migrate V1 data if you have it
python utils/migrate_v1.py

# 5. Copy your directive
cp ~/sage/directive.txt ~/sage_data_v2/directive.txt
# or create a new one at ~/sage_data_v2/directive.txt

# 6. Start the server
python launch.py
```

Open: http://localhost:6969

---

## Configuration

All tunable values are in `config/settings.py`. Key settings:

```python
# Models
CHAT_MODEL        = "meta/llama-3.3-70b-instruct"
REFLECTION_MODEL  = "mistralai/mistral-small-4-119b-2603"

# Memory retrieval
TOP_K_USER_MEMORIES  = 4    # how many user memories injected per turn
TOP_K_SAGE_MEMORIES  = 2    # how many sage memories injected per turn
RETRIEVAL_THRESHOLD  = 0.35  # minimum similarity score

# Daemon
DAEMON_TURN_TRIGGER      = 6    # reflect every N assistant turns
DAEMON_COOLDOWN_SECONDS  = 300  # min seconds between daemon runs

# Autonomous search
AUTONOMOUS_SEARCH_MAX_PER_DAY = 10
AUTONOMOUS_SEARCH_COOLDOWN    = 3600  # 1 hour between searches
```

---

## Directory Structure After First Boot

```
~/sage_data_v2/
├── directive.txt                   ← Sage's personality/system prompt
├── chat_history.jsonl              ← JSONL conversation history
├── sage_state.json                 ← version + domain metadata
├── search_budget.json              ← daily autonomous search tracking
│
├── user_memory/                    ← Elliot's memory domain
│   ├── episodic/                   ← timestamped event summaries
│   ├── emotional/                  ← recurring emotional themes
│   ├── reflections/                ← synthesised pattern reflections
│   └── library/
│       ├── people/                 ← named individuals
│       ├── places/                 ← named locations
│       └── topics/                 ← recurring subjects
│
├── sage_memory/                    ← Sage's own memory domain
│   ├── reflections/                ← Sage's first-person inner reflections
│   ├── curiosity/                  ← topics she's drawn to investigate
│   ├── worldview/                  ← her evolving topic perspectives
│   └── search_log/                 ← record of autonomous searches
│
├── embeddings/                     ← shared embedding cache (*.json)
└── logs/
    └── sage.YYYY-MM-DD.jsonl       ← structured daily log
```

---

## Verifying the System

After booting, check http://localhost:6969 and click the **status** tab.

You should see:
- `server: ok`
- `daemon: running`
- `memory domains: user, sage`

If the daemon shows `stopped`, check the logs:
```bash
tail -f ~/sage_data_v2/logs/sage.$(date +%Y-%m-%d).jsonl | python3 -m json.tool
```

---

## Current Inference Architecture (as of post-Phase 4)

- **Chat & Reflection/Synthesis**: NVIDIA NIM (meta/llama-3.3-70b-instruct by default).
- **Embeddings (hot path, recommended)**: Local llama.cpp server running intfloat/e5-mistral-7b-instruct Q5_K_M.gguf.
  - Served via user systemd service (see `systemd/user/llama-embedder.service` in repo): `llama-server ... --embedding --pooling mean -ngl 18 ... --port 8081`.
  - Fast local retrieval with proper e5 asymmetric prefixes (query: / passage: ).
- **Search**: Providers include SearXNG (self-hosted) or DuckDuckGo fallback, with autonomous budget enforcement.

NIM is used for the large models (no local GPU needed for 70B). Local embedder gives low-latency, private retrieval. See README.md "Stack" and "Hardware" sections + the systemd unit for exact current setup.

If the embedder or NIM is unreachable, retrieval gracefully degrades.

---

## Changing the Chat Model

Edit `config/settings.py`:

```python
CHAT_MODEL = "meta/llama-3.1-70b-instruct"   # or any NIM model
```

Restart the server. No migration needed.

---

## Stopping the Server

`Ctrl+C` — the shutdown handler closes the httpx client and stops the daemon cleanly.
