"""
memory/sage/reflections.py — Sage's Internal Reflection Memory

Stores Sage's own reflective output — her internal experience as she
processes conversations and the world:
  - private reflections on her interactions with Elliot
  - observations about patterns she notices in herself
  - emotional interpretations from Sage's perspective

These are NEVER user memories. They represent Sage's emerging inner life.
They feed back into Sage's synthesis when she generates responses —
giving her genuine autobiographical continuity, not just Elliot's history.

Format per file:
  [YYYY-MM-DD HH:MM]
  [sage_reflection_text]
"""

import re
from datetime import datetime
from pathlib import Path

from config.settings import SAGE_REFLECTIONS_DIR
from memory.storage.base import (
    ensure_dirs,
    list_memory_files,
    read_memory_entry,
    write_memory_entry,
)


def _reflection_stem(label: str = "") -> str:
    """Generate reflection filename: YYYYMMDD_HHMMSS_label."""
    date_part = datetime.now().strftime("%Y%m%d_%H%M%S")
    if label:
        safe = re.sub(r"[^a-z0-9_-]", "_", label.lower())[:32]
        return f"{date_part}_{safe}"
    return date_part


async def write_sage_reflection(content: str, label: str = "") -> Path:
    """
    Persist one of Sage's internal reflections.
    content: Sage's own synthesized reflection text
    label: short topic hint for filename (optional)
    """
    ensure_dirs(SAGE_REFLECTIONS_DIR)
    stem = _reflection_stem(label)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
    full = f"[{ts}]\n{content.strip()}\n"
    return await write_memory_entry(SAGE_REFLECTIONS_DIR, stem, full)


async def load_recent_sage_reflections(n: int = 5) -> list[str]:
    """Load Sage's n most recent reflections (newest first)."""
    files = await list_memory_files(SAGE_REFLECTIONS_DIR)
    recent = files[-n:]
    result = []
    for f in reversed(recent):
        content = await read_memory_entry(f)
        if content:
            result.append(content.strip())
    return result


async def load_all_sage_reflections() -> list[tuple[Path, str]]:
    """Load all sage reflections as (path, content) pairs. Used by retrieval."""
    files = await list_memory_files(SAGE_REFLECTIONS_DIR)
    result = []
    for f in files:
        content = await read_memory_entry(f)
        if content:
            result.append((f, content))
    return result
