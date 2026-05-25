"""
cognition/salience/tracker.py — Salience Tracking System

Every cognitive artifact in Sage's memory carries a salience score.
Salience determines retrieval weight and cognitive resource allocation.

Salience is:
  - A float in [0.05, 1.0]
  - Initialized at 1.0 on creation
  - Decayed deterministically each daemon cycle
  - Boosted when retrieved (re-relevance signal)
  - Boosted when referenced by a new reflection or thread

Salience is NOT:
  - LLM-generated
  - Stochastic
  - Self-reinforcing without external signal

Persistence:
  Salience data is stored in a single JSON file per domain:
    ~/sage_data_v2/sage_memory/salience.json

  Structure: { "artifact_key": { "score": float, "last_decay": iso_ts, "last_boost": iso_ts, "boost_count": int } }

  artifact_key format: "domain/type/stem"
    e.g. "sage/reflection/20260525_143000_something"
         "sage/worldview/grief_psychology"
         "sage/curiosity/20260520_curiosity_indonesian_politics_"

Design constraints:
  - Decay is applied ONCE per daemon cycle, not per retrieval
  - Boost is applied at most ONCE per daemon cycle per artifact (prevents multi-hit amplification)
  - Score never drops below SALIENCE_FLOOR (0.05) — artifacts fade but never fully vanish
  - Score never exceeds SALIENCE_CEILING (1.0)
  - Missing artifacts get default score of 1.0 (backward compatible with pre-3B memory)
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import SAGE_MEMORY_ROOT
from utils.logger import log


# ── Constants ────────────────────────────────────────────────────────

SALIENCE_FLOOR   = 0.05
SALIENCE_CEILING = 1.0
SALIENCE_DEFAULT = 1.0

# Decay factor per daemon cycle: score *= DECAY_RATE
# At 0.92, an unboosted artifact reaches 0.5 after ~8 cycles, 0.2 after ~18 cycles
DECAY_RATE = 0.92

# Boost amount when an artifact is retrieved during a conversation turn
RETRIEVAL_BOOST = 0.15

# Boost amount when an artifact is explicitly referenced by a reflection or thread
REFERENCE_BOOST = 0.25

# Maximum boosts applicable in a single daemon cycle (prevents amplification)
MAX_BOOSTS_PER_CYCLE = 1

# Path to salience persistence file
SALIENCE_FILE = SAGE_MEMORY_ROOT / "salience.json"


# ── Data model ───────────────────────────────────────────────────────

def _default_entry() -> dict:
    return {
        "score": SALIENCE_DEFAULT,
        "last_decay": "",
        "last_boost": "",
        "boost_count": 0,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ── Persistence ──────────────────────────────────────────────────────

def _load_salience_db() -> dict:
    """Load the salience database from disk. Returns empty dict on failure."""
    if not SALIENCE_FILE.exists():
        return {}
    try:
        raw = SALIENCE_FILE.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception as e:
        log("salience", "load_error", error=str(e))
        return {}


def _save_salience_db(db: dict) -> bool:
    """Atomically save the salience database."""
    try:
        SALIENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SALIENCE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(SALIENCE_FILE)
        return True
    except Exception as e:
        log("salience", "save_error", error=str(e))
        return False


# ── Public API ───────────────────────────────────────────────────────

def get_salience(artifact_key: str) -> float:
    """
    Return the current salience score for an artifact.
    Returns SALIENCE_DEFAULT for unknown artifacts (backward compatible).
    """
    db = _load_salience_db()
    entry = db.get(artifact_key)
    if entry is None:
        return SALIENCE_DEFAULT
    return _clamp(entry.get("score", SALIENCE_DEFAULT))


def get_salience_batch(keys: list[str]) -> dict[str, float]:
    """
    Return salience scores for multiple artifacts in one disk read.
    Unknown keys get SALIENCE_DEFAULT.
    """
    db = _load_salience_db()
    result = {}
    for key in keys:
        entry = db.get(key)
        if entry is None:
            result[key] = SALIENCE_DEFAULT
        else:
            result[key] = _clamp(entry.get("score", SALIENCE_DEFAULT))
    return result


def register_artifact(artifact_key: str) -> None:
    """
    Register a new cognitive artifact in the salience system.
    Called when a reflection, curiosity, or worldview entry is first written.
    No-op if the artifact already exists.
    """
    db = _load_salience_db()
    if artifact_key in db:
        return
    db[artifact_key] = _default_entry()
    _save_salience_db(db)
    log("salience", "registered", key=artifact_key)


def boost_retrieval(artifact_key: str, cycle_id: str) -> float:
    """
    Boost an artifact's salience because it was retrieved.
    Returns the new score.

    cycle_id prevents multiple boosts in the same daemon cycle.
    The cycle_id is typically the daemon cycle timestamp.
    """
    return _apply_boost(artifact_key, RETRIEVAL_BOOST, cycle_id)


def boost_reference(artifact_key: str, cycle_id: str) -> float:
    """
    Boost an artifact's salience because it was referenced by a new reflection or thread.
    Returns the new score.
    """
    return _apply_boost(artifact_key, REFERENCE_BOOST, cycle_id)


def decay_all(cycle_id: str) -> dict:
    """
    Apply decay to ALL tracked artifacts. Called once per daemon cycle.

    Returns summary: {decayed: int, floor_clamped: int, total: int}

    cycle_id is stored to prevent double-decay if the daemon fires twice
    in rapid succession (should not happen due to mutex, but defense in depth).
    """
    db = _load_salience_db()
    decayed = 0
    floor_clamped = 0

    for key, entry in db.items():
        if entry.get("last_decay") == cycle_id:
            continue

        old_score = entry.get("score", SALIENCE_DEFAULT)
        new_score = old_score * DECAY_RATE
        new_score = _clamp(new_score)

        if new_score <= SALIENCE_FLOOR:
            floor_clamped += 1

        entry["score"] = new_score
        entry["last_decay"] = cycle_id
        decayed += 1

    _save_salience_db(db)

    summary = {"decayed": decayed, "floor_clamped": floor_clamped, "total": len(db)}
    log("salience", "decay_applied", cycle_id=cycle_id, **summary)
    return summary


def remove_artifact(artifact_key: str) -> None:
    """Remove an artifact from salience tracking. Called when memory is archived."""
    db = _load_salience_db()
    if artifact_key in db:
        del db[artifact_key]
        _save_salience_db(db)
        log("salience", "removed", key=artifact_key)


def get_stats() -> dict:
    """Return summary statistics for monitoring."""
    db = _load_salience_db()
    if not db:
        return {"total": 0, "avg_score": 0.0, "floor_count": 0, "high_count": 0}
    scores = [e.get("score", SALIENCE_DEFAULT) for e in db.values()]
    return {
        "total": len(scores),
        "avg_score": round(sum(scores) / len(scores), 3),
        "floor_count": sum(1 for s in scores if s <= SALIENCE_FLOOR + 0.01),
        "high_count": sum(1 for s in scores if s >= 0.8),
    }


# ── Internal helpers ─────────────────────────────────────────────────

def _apply_boost(artifact_key: str, amount: float, cycle_id: str) -> float:
    """Apply a boost to an artifact, respecting per-cycle limits."""
    db = _load_salience_db()
    entry = db.get(artifact_key)

    if entry is None:
        entry = _default_entry()
        db[artifact_key] = entry

    # Enforce max boosts per cycle
    if entry.get("last_boost") == cycle_id:
        if entry.get("boost_count", 0) >= MAX_BOOSTS_PER_CYCLE:
            return _clamp(entry["score"])

    old_score = entry["score"]
    new_score = _clamp(old_score + amount)
    entry["score"] = new_score
    entry["last_boost"] = cycle_id

    if entry.get("last_boost") == cycle_id:
        entry["boost_count"] = entry.get("boost_count", 0) + 1
    else:
        entry["boost_count"] = 1

    _save_salience_db(db)
    return new_score


def _clamp(score: float) -> float:
    """Clamp salience to valid bounds."""
    if score < SALIENCE_FLOOR:
        return SALIENCE_FLOOR
    if score > SALIENCE_CEILING:
        return SALIENCE_CEILING
    return round(score, 4)
