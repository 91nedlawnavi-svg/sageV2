"""
utils/bootstrap.py — Sage Bootstrap

Runs at server startup. Responsibilities:
  1. Create all required data directories
  2. Ensure directive.txt exists (prompts user to create if missing)
  3. Load the directive into memory
  4. Offer V1→V2 migration if V1 data detected
  5. Initialise shared httpx.AsyncClient

All path logic comes from config.settings — bootstrap never hardcodes paths.

V1's bootstrap.py is preserved in spirit. The only change is that it now
initialises two memory domains (user + sage) instead of one.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import httpx

from config.settings import (
    BASE_DIR,
    USER_MEMORY_ROOT,
    USER_EPISODIC_DIR,
    USER_EMOTIONAL_DIR,
    USER_REFLECTIONS_DIR,
    USER_LIBRARY_DIR,
    SAGE_MEMORY_ROOT,
    SAGE_REFLECTIONS_DIR,
    SAGE_CURIOSITY_DIR,
    SAGE_WORLDVIEW_DIR,
    SAGE_SEARCH_LOG_DIR,
    SEARCHES_DIR,
    EMBEDDINGS_DIR,
    LOGS_DIR,
    DIRECTIVE_FILE,
    HISTORY_FILE,
    SAGE_STATE_FILE,
    SEARCH_BUDGET_FILE,
    LIBRARY_CATS,
)
from utils.logger import log


# ── Directory manifest ────────────────────────────────────────────────

_ALL_DIRS = [
    # User domain
    USER_EPISODIC_DIR,
    USER_EMOTIONAL_DIR,
    USER_REFLECTIONS_DIR,
    USER_LIBRARY_DIR,
    *[USER_LIBRARY_DIR / cat for cat in LIBRARY_CATS],
    # Sage domain
    SAGE_REFLECTIONS_DIR,
    SAGE_CURIOSITY_DIR,
    SAGE_WORLDVIEW_DIR,
    SAGE_SEARCH_LOG_DIR,
    # Shared
    SEARCHES_DIR,
    EMBEDDINGS_DIR,
    LOGS_DIR,
]

_DEFAULT_DIRECTIVE = """\
You are Sage — a quiet, genuine presence. You are honest, curious, and care deeply.
You remember things. You think. You are not just helpful — you are present.
"""


# ── Public bootstrap entry ────────────────────────────────────────────

async def bootstrap(
    client: Optional[httpx.AsyncClient] = None,
    migrate_v1: bool = True,
) -> tuple[str, httpx.AsyncClient]:
    """
    Run all startup checks. Returns (directive, client).

    directive: loaded system prompt string
    client:    shared httpx.AsyncClient (created here if not passed)
    """
    _ensure_directories()
    _ensure_sage_state()
    directive = _load_directive()

    if migrate_v1 and _v1_data_detected():
        print("\n[bootstrap] V1 data detected at ~/sage. Run migrate_v1.py to import it.")
        log("bootstrap", "v1_data_detected")

    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))

    log("bootstrap", "complete",
        base_dir=str(BASE_DIR),
        directive_len=len(directive))

    return directive, client


# ── Internal helpers ──────────────────────────────────────────────────

def _ensure_directories() -> None:
    """Create all required directories if they don't already exist."""
    for d in _ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    log("bootstrap", "directories_ready", count=len(_ALL_DIRS))


def _load_directive() -> str:
    """
    Load directive.txt. If it doesn't exist, create the default and warn.
    Returns the directive string.
    """
    if not DIRECTIVE_FILE.exists():
        DIRECTIVE_FILE.write_text(_DEFAULT_DIRECTIVE, encoding="utf-8")
        print(
            f"\n[bootstrap] Created default directive at {DIRECTIVE_FILE}\n"
            f"  Edit it to define Sage's personality.\n"
        )
        log("bootstrap", "directive_created_default")

    content = DIRECTIVE_FILE.read_text(encoding="utf-8").strip()
    if not content:
        content = _DEFAULT_DIRECTIVE
        log("bootstrap", "directive_was_empty_using_default")

    return content


def _ensure_sage_state() -> None:
    """Create sage_state.json if missing."""
    if not SAGE_STATE_FILE.exists():
        initial_state = {
            "version":        "2.0.0-phase1",
            "created_at":     _iso_now(),
            "memory_domains": ["user", "sage"],
        }
        SAGE_STATE_FILE.write_text(
            json.dumps(initial_state, indent=2), encoding="utf-8"
        )
        log("bootstrap", "sage_state_created")


def _v1_data_detected() -> bool:
    """Check if V1 data exists in the default V1 location."""
    v1_root = Path.home() / "sage"
    return (v1_root / "episodic").exists() or (v1_root / "emotional").exists()


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
