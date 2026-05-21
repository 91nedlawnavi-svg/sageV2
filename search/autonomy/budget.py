"""
search/autonomy/budget.py — Autonomous Search Budget Tracker

Enforces the Level 2 autonomy constraints defined in the spec:
  - Maximum 10 autonomous searches per day
  - Minimum 1-hour cooldown between autonomous searches
  - No external actions beyond search

The budget is persisted to disk so it survives server restarts.
This is intentional — the daily cap is calendar-day based.

Level 2 autonomy means Sage has moderate freedom but is bounded.
She can be curious, but not frantic.
"""

import json
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from config.settings import (
    SEARCH_BUDGET_FILE,
    AUTONOMOUS_SEARCH_MAX_PER_DAY,
    AUTONOMOUS_SEARCH_COOLDOWN,
)
from utils.logger import log


def _load_budget() -> dict:
    """Load budget state from disk. Returns default if missing or corrupt."""
    try:
        if SEARCH_BUDGET_FILE.exists():
            data = json.loads(SEARCH_BUDGET_FILE.read_text(encoding="utf-8"))
            return data
    except Exception:
        pass
    return {
        "date": str(date.today()),
        "count": 0,
        "last_search_ts": 0.0,
    }


def _save_budget(state: dict) -> None:
    """Persist budget state to disk."""
    try:
        SEARCH_BUDGET_FILE.write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )
    except Exception as e:
        log("search", "budget_save_error", error=str(e))


def _reset_if_new_day(state: dict) -> dict:
    """Reset count if we're on a new calendar day."""
    today = str(date.today())
    if state.get("date") != today:
        state["date"]  = today
        state["count"] = 0
    return state


def can_autonomous_search() -> tuple[bool, str]:
    """
    Check whether Sage is allowed to perform an autonomous search right now.

    Returns (allowed: bool, reason: str).
    reason explains the decision for logging and self-awareness.
    """
    state = _load_budget()
    state = _reset_if_new_day(state)

    # Check daily cap
    if state["count"] >= AUTONOMOUS_SEARCH_MAX_PER_DAY:
        reason = (
            f"Daily search limit reached ({state['count']}/{AUTONOMOUS_SEARCH_MAX_PER_DAY}). "
            f"Resets tomorrow."
        )
        return False, reason

    # Check cooldown
    elapsed = time.time() - state.get("last_search_ts", 0.0)
    if elapsed < AUTONOMOUS_SEARCH_COOLDOWN:
        remaining = int(AUTONOMOUS_SEARCH_COOLDOWN - elapsed)
        reason = f"Cooldown active. {remaining // 60}m {remaining % 60}s remaining."
        return False, reason

    return True, "Search allowed."


def record_autonomous_search() -> int:
    """
    Record that an autonomous search was performed.
    Returns the new count for today.
    """
    state = _load_budget()
    state = _reset_if_new_day(state)
    state["count"] += 1
    state["last_search_ts"] = time.time()
    _save_budget(state)
    log("search", "budget_updated",
        count=state["count"],
        max=AUTONOMOUS_SEARCH_MAX_PER_DAY,
        date=state["date"])
    return state["count"]


def get_budget_status() -> dict:
    """Return current budget state for status endpoint."""
    state = _load_budget()
    state = _reset_if_new_day(state)
    return {
        "date":       state["date"],
        "count":      state["count"],
        "max":        AUTONOMOUS_SEARCH_MAX_PER_DAY,
        "remaining":  AUTONOMOUS_SEARCH_MAX_PER_DAY - state["count"],
        "cooldown_active": (time.time() - state.get("last_search_ts", 0.0)) < AUTONOMOUS_SEARCH_COOLDOWN,
    }
