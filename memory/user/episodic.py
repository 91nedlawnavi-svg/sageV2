"""
memory/user/episodic.py — User Episodic Memory Layer

Stores distilled summaries of concrete events in Elliot's life:
  - timestamped
  - named for retrieval
  - written by the memory model from conversation digests

Format per file:
  [YYYY-MM-DD HH:MM]
  [summary text]

This is a USER domain memory — it belongs to Elliot's narrative, not Sage's.
It must NEVER be written to by Sage's autonomous cognition.

Preserved from V1's memory/episodic.py with path updates.
"""

import re
from datetime import datetime
from pathlib import Path

from config.settings import USER_EPISODIC_DIR, USER_REFLECTIONS_DIR
from memory.storage.base import (
    ensure_dirs,
    list_memory_files,
    read_memory_entry,
    write_memory_entry,
)


def _episode_stem(label: str = "") -> str:
    """Generate episodic filename: YYYYMMDD_HHMMSS_label."""
    date_part = datetime.now().strftime("%Y%m%d_%H%M%S")
    if label:
        safe = re.sub(r"[^a-z0-9_-]", "_", label.lower())[:32]
        return f"{date_part}_{safe}"
    return date_part


async def write_user_episode(summary: str, label: str = "") -> Path:
    """
    Persist one episodic memory entry for the user.
    summary: distilled interpretation (not raw log)
    """
    ensure_dirs(USER_EPISODIC_DIR)
    stem = _episode_stem(label)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"[{ts}]\n{summary.strip()}\n"
    return await write_memory_entry(USER_EPISODIC_DIR, stem, content)


async def load_recent_user_episodes(n: int = 10) -> list[str]:
    """Load the n most recent episodic memory entries (newest first)."""
    files = await list_memory_files(USER_EPISODIC_DIR)
    recent = files[-n:]
    entries = []
    for f in reversed(recent):
        content = await read_memory_entry(f)
        if content:
            entries.append(content.strip())
    return entries


async def load_all_user_episodes() -> list[tuple[Path, str]]:
    """Load all episodes as (path, content) pairs. Used by retrieval."""
    files = await list_memory_files(USER_EPISODIC_DIR)
    result = []
    for f in files:
        content = await read_memory_entry(f)
        if content:
            result.append((f, content))
    return result


async def load_all_user_reflections() -> list[tuple[Path, str]]:
    """Load all user-domain reflection files as (path, content) pairs."""
    files = await list_memory_files(USER_REFLECTIONS_DIR)
    result = []
    for f in files:
        content = await read_memory_entry(f)
        if content:
            result.append((f, content))
    return result
