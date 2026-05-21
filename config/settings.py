"""
config/settings.py — Sage V2 System Configuration

Single source of truth for all constants, paths, and tunable parameters.
Separated from V1's flat config.py into a proper config module with
explicit domain grouping.

Edit this file to tune system behavior. Never import config from
deep inside cognition modules — always import from here.
"""

import os
from pathlib import Path


# ── Base directories ──────────────────────────────────────────────────

BASE_DIR = Path.home() / "sage_data_v2"

# Separate memory roots — the core V2 identity separation
USER_MEMORY_ROOT  = BASE_DIR / "user_memory"
SAGE_MEMORY_ROOT  = BASE_DIR / "sage_memory"

# Subdirectories within user memory
USER_EPISODIC_DIR    = USER_MEMORY_ROOT / "episodic"
USER_EMOTIONAL_DIR   = USER_MEMORY_ROOT / "emotional"
USER_REFLECTIONS_DIR = USER_MEMORY_ROOT / "reflections"
USER_LIBRARY_DIR     = USER_MEMORY_ROOT / "library"

# Subdirectories within sage memory
SAGE_REFLECTIONS_DIR  = SAGE_MEMORY_ROOT / "reflections"
SAGE_CURIOSITY_DIR    = SAGE_MEMORY_ROOT / "curiosity"
SAGE_WORLDVIEW_DIR    = SAGE_MEMORY_ROOT / "worldview"
SAGE_SEARCH_LOG_DIR   = SAGE_MEMORY_ROOT / "search_log"

# Shared data directories
SEARCHES_DIR    = BASE_DIR / "searches"
EMBEDDINGS_DIR  = BASE_DIR / "embeddings"
LOGS_DIR        = BASE_DIR / "logs"

# Runtime files
DIRECTIVE_FILE      = BASE_DIR / "directive.txt"
HISTORY_FILE        = BASE_DIR / "chat_history.jsonl"
SAGE_STATE_FILE     = BASE_DIR / "sage_state.json"
SEARCH_BUDGET_FILE  = BASE_DIR / "search_budget.json"

# Library categories (user-maintained knowledge about people, places, topics)
LIBRARY_CATS = ["people", "places", "topics"]


# ── NVIDIA NIM ────────────────────────────────────────────────────────

NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_API_URL  = "https://integrate.api.nvidia.com/v1/chat/completions"

# Primary chat model (streaming, user-facing)
CHAT_MODEL       = os.environ.get("SAGE_CHAT_MODEL", "meta/llama-3.3-70b-instruct")
CHAT_API_URL     = NVIDIA_API_URL
CHAT_TEMPERATURE = 0.75
CHAT_MAX_TOKENS  = 2048
CHAT_TOP_P       = 0.9

# Reflection / synthesis model (non-streaming, background)
REFLECTION_MODEL       = os.environ.get("SAGE_REFLECTION_MODEL", "mistralai/mistral-small-4-119b-2603")
REFLECTION_TEMPERATURE = 0.7
REFLECTION_MAX_TOKENS  = 220


# ── Local inference endpoints ─────────────────────────────────────────

# Local memory model (Qwen 3B via llama.cpp on 8081)
MEM_API_URL   = "http://localhost:8081/v1/chat/completions"
MEM_TEMPERATURE = 0.1
MEM_MAX_TOKENS  = 512
MEM_TOP_P       = 0.9

# Local embedding model (BGE-M3 via llama.cpp on 8082)
EMBED_API_URL   = "http://localhost:8082/v1/embeddings"
EMBED_PREFIX    = "Represent this sentence for searching relevant passages: "
EMBED_CACHE_MAX = 512


# ── Memory retrieval ──────────────────────────────────────────────────

# Maximum memory chunks injected into a single prompt
TOP_K_USER_MEMORIES = 4    # user-side memories per turn
TOP_K_SAGE_MEMORIES = 2    # sage-side memories per turn (search context, worldview)

RETRIEVAL_THRESHOLD = 0.35  # minimum cosine similarity to include a chunk

# Retrieval caps — prevents the candidate pool from growing unbounded
EPISODIC_RETRIEVAL_CAP   = 200
REFLECTION_RETRIEVAL_CAP = 90


# ── Conversation ──────────────────────────────────────────────────────

HISTORY_TURNS = 12  # recent turns to include in prompt window


# ── Daemon triggers ───────────────────────────────────────────────────

DAEMON_TURN_TRIGGER     = 6    # reflect after N assistant turns
DAEMON_EMOTION_TRIGGER  = 3    # reflect if emotional signal in last N turns
DAEMON_COOLDOWN_SECONDS = 300  # minimum seconds between daemon runs (5 min)

# Emotional signal keywords (bilingual: EN + ID)
EMOTIONAL_KEYWORDS = {
    "hate", "love", "scared", "afraid", "angry", "sad", "happy",
    "miss", "lonely", "tired", "exhausted", "excited", "hurt", "anxious",
    "benci", "takut", "marah", "sedih", "senang", "kangen", "lelah", "cemas",
    "rindu", "frustasi", "bahagia", "kecewa", "gelisah",
}


# ── Autonomous search budget ──────────────────────────────────────────

AUTONOMOUS_SEARCH_MAX_PER_DAY = 10   # Level 2 autonomy cap
AUTONOMOUS_SEARCH_COOLDOWN    = 3600  # minimum seconds between autonomous searches (1 hr)


# ── Server ────────────────────────────────────────────────────────────

PORT = 6969
