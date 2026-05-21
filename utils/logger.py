"""
utils/logger.py — Sage V2 Structured Runtime Logger

JSONL log file: ~/sage_data_v2/logs/sage.YYYY-MM-DD.jsonl  (daily rotation)
Each line is a self-contained JSON event.

Usage:
    from utils.logger import log

    log("daemon", "cycle_start")
    log("retrieval", "scored", domain="user", candidates=12, returned=3)
    log("search", "autonomous_triggered", reason="unresolved_curiosity")

Fields always present:
    ts        ISO-8601 timestamp
    subsystem one of: daemon, retrieval, cognition, memory, inference,
                      search, bootstrap, websocket, event_bus
    event     short snake_case label
    ...rest   optional keyword args
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_log_dir: Path | None = None


def _get_log_path() -> Path:
    global _log_dir
    if _log_dir is None:
        from config.settings import LOGS_DIR
        _log_dir = LOGS_DIR
        _log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _log_dir / f"sage.{date_str}.jsonl"


def log(subsystem: str, event: str, **kwargs) -> None:
    """
    Write one structured log event.
    Never raises — logging failures are printed to stderr and swallowed.
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "subsystem": subsystem,
        "event": event,
        **kwargs,
    }
    try:
        with _get_log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[logger] Failed to write log: {exc}", file=sys.stderr)
