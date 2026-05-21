"""
memory/sage/worldview.py — Sage's Evolving Worldview

Stores Sage's accumulated understanding of topics she has researched:
  - synthesized knowledge from autonomous searches
  - evolving interpretations of recurring topics
  - her own perspective on subjects she finds fascinating

These are NOT search result dumps. They are Sage's processed understanding —
what she made of what she found, filtered through her own cognition.

Each entry is one topic. Entries are updated (merged), not duplicated.

Format per file:
  [topic_name]
  [last_updated: YYYY-MM-DD HH:MM]
  [source: search|reflection|synthesis]
  [perspective text]
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import SAGE_WORLDVIEW_DIR
from memory.storage.base import (
    ensure_dirs,
    list_memory_files,
    read_memory_entry,
    safe_stem,
    write_text,
)


def _worldview_path(topic: str) -> Path:
    """Derive the file path for a worldview topic entry."""
    return SAGE_WORLDVIEW_DIR / f"{safe_stem(topic)}.txt"


async def write_worldview_entry(
    topic: str,
    perspective: str,
    source: str = "synthesis",
) -> Path:
    """
    Write or overwrite a worldview entry for a topic.
    Called after Sage integrates search results into her understanding.
    """
    ensure_dirs(SAGE_WORLDVIEW_DIR)
    path = _worldview_path(topic)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = (
        f"[{topic}]\n"
        f"[last_updated: {ts}]\n"
        f"[source: {source}]\n"
        f"{perspective.strip()}\n"
    )
    await write_text(path, content)
    return path


async def load_worldview_entry(topic: str) -> Optional[str]:
    """Load Sage's perspective on a specific topic."""
    path = _worldview_path(topic)
    if not path.exists():
        return None
    return await read_memory_entry(path)


async def load_all_worldview_entries() -> list[tuple[str, str]]:
    """Load all worldview entries as (topic_slug, content) pairs. Used by retrieval."""
    files = await list_memory_files(SAGE_WORLDVIEW_DIR)
    result = []
    for f in files:
        content = await read_memory_entry(f)
        if content:
            result.append((f.stem, content))
    return result


async def list_worldview_topics() -> list[str]:
    """Return the stem names of all worldview topic files."""
    files = await list_memory_files(SAGE_WORLDVIEW_DIR)
    return [f.stem for f in files]
