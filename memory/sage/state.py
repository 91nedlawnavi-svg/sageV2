"""
memory/sage/state.py — Sage Internal State Persistence

Implements the sage_state.json continuity snapshot.

This file is the ONLY place that reads or writes sage_state.json.
All other modules import load_sage_state() / save_sage_state() from here.

The state object is a lightweight orientation summary — NOT a memory dump.
It survives across daemon cycles so Sage wakes with continuity, not cold.

Structure:
  last_updated          ISO timestamp of last write
  current_focus         list[str] — active topics/threads (max 3)
  active_questions      list[str] — unresolved questions (max 4)
  emotional_orientation str       — terse description of Sage's current register
  recent_synthesis      str       — 1-2 sentence summary of last daemon cycle
  worldview_tensions    list[str] — open conceptual tensions (max 3)
  active_curiosity_topics list[str] — deduplicated pending curiosity topics (max 5)
  self_summary          str       — stable but refreshable self-orientation sentence

Design constraints:
  - Summaries, not archives. Field values must stay SHORT.
  - State must STABILIZE — not recursively absorb itself.
  - Write path uses atomic temp-file rename to avoid partial writes.
  - Reads are always safe (returns defaults if file absent or corrupt).
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import SAGE_STATE_FILE
from utils.logger import log


# ── Default state — returned when file is absent or corrupt ──────────

def _default_state() -> dict:
    return {
        "last_updated":           "",
        "current_focus":          [],
        "active_questions":       [],
        "emotional_orientation":  "",
        "recent_synthesis":       "",
        "worldview_tensions":     [],
        "active_curiosity_topics": [],
        "self_summary":           "",
        # Phase 3B additions
        "active_threads":         [],
        "orientation_history":    [],
        "meta_warnings":          [],
    }


# ── Read ──────────────────────────────────────────────────────────────

def load_sage_state() -> dict:
    """
    Load sage_state.json. Returns defaults on any failure.
    This is intentionally synchronous — state reads are fast file ops
    and must not introduce async complexity into the prompt path.
    """
    path = Path(SAGE_STATE_FILE)
    if not path.exists():
        return _default_state()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        # Merge with defaults to handle schema evolution gracefully
        state = _default_state()
        state.update({k: v for k, v in data.items() if k in state})
        return state
    except Exception as e:
        log("state", "load_error", error=str(e))
        return _default_state()


# ── Write ─────────────────────────────────────────────────────────────

def save_sage_state(state: dict) -> bool:
    """
    Atomically write sage_state.json.
    Uses temp-file + rename to prevent partial-write corruption.
    Returns True on success.
    """
    path = Path(SAGE_STATE_FILE)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(state, indent=2, ensure_ascii=False)
        # Atomic write: write to temp then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=path.parent, prefix=".sage_state_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_path, path)
        except Exception:
            # Clean up orphaned temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        log("state", "saved")
        return True
    except Exception as e:
        log("state", "save_error", error=str(e))
        return False


# ── Synthesis helpers ─────────────────────────────────────────────────

def build_state_injection(state: dict) -> str:
    """
    Render sage_state into a compact text block for prompt injection.
    Returns empty string if state is effectively empty.

    This is the PRIMARY continuity anchor injected BEFORE retrieved reflections.
    Keep it terse — it is a orientation header, not a memory dump.

    Phase 3B: Includes active cognitive threads and meta-observation warnings.
    """
    parts = []

    if state.get("self_summary"):
        parts.append(f"Orientation: {state['self_summary']}")

    if state.get("emotional_orientation"):
        parts.append(f"Current register: {state['emotional_orientation']}")

    # Phase 3B: cognitive threads replace ad-hoc focus tracking
    threads = state.get("active_threads", [])
    if threads:
        parts.append("Cognitive threads: " + "; ".join(threads[:4]))
    else:
        focus = state.get("current_focus", [])
        if focus:
            parts.append("Active focus: " + "; ".join(focus[:3]))

    questions = state.get("active_questions", [])
    if questions:
        parts.append("Open questions: " + "; ".join(questions[:4]))

    tensions = state.get("worldview_tensions", [])
    if tensions:
        parts.append("Worldview tensions: " + "; ".join(tensions[:3]))

    curiosities = state.get("active_curiosity_topics", [])
    if curiosities:
        parts.append("Curiosity threads: " + "; ".join(curiosities[:5]))

    if state.get("recent_synthesis"):
        parts.append(f"Last cycle: {state['recent_synthesis']}")

    # Phase 3B: meta-observation warnings (read-only sensor output)
    warnings = state.get("meta_warnings", [])
    if warnings:
        parts.append("Meta-observations: " + " | ".join(warnings[:3]))

    if not parts:
        return ""

    header = "--- SAGE CONTINUITY STATE ---"
    footer = "--- END CONTINUITY STATE ---"
    return header + "\n" + "\n".join(parts) + "\n" + footer


def merge_curiosity_topics(
    existing: list[str],
    new_topics: list[str],
    max_topics: int = 5,
) -> list[str]:
    """
    Deduplicate curiosity topics by normalized comparison.
    New topics replace/extend existing; no infinite accumulation.

    Normalization: lowercase, strip, collapse whitespace.
    Similarity: substring match after normalization is enough —
    we don't need embeddings for deduplication at this level.
    """
    def _norm(s: str) -> str:
        return " ".join(s.lower().strip().split())

    existing_norm = {_norm(t): t for t in existing}
    result = dict(existing_norm)

    for topic in new_topics:
        n = _norm(topic)
        if not n:
            continue
        # Check if this topic is already represented (substring match)
        already = any(
            n in existing_key or existing_key in n
            for existing_key in result
        )
        if not already:
            result[n] = topic

    # Keep most recent max_topics (preserve insertion order)
    values = list(result.values())
    return values[-max_topics:]
