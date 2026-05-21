"""
memory/sage/curiosity.py — Sage's Curiosity Journal

Records Sage's autonomous curiosity:
  - topics she became curious about
  - questions she found herself wanting to investigate
  - intellectual fascinations that emerged
  - unresolved tensions in her understanding

These are NEVER user memories. They are Sage's own intellectual life.
When Sage searches autonomously, a curiosity entry is written BEFORE
the search to capture the "why" — separating motivation from result.

Format per file:
  [YYYY-MM-DD HH:MM]
  [topic: short_label]
  [reason: why Sage became curious]
  [status: pending|searched|integrated]
  [query: the search query used, if any]
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import json

from config.settings import SAGE_CURIOSITY_DIR
from memory.storage.base import (
    ensure_dirs,
    list_memory_files,
    read_memory_entry,
    ts_filename,
    write_memory_entry,
    write_text,
    safe_stem,
)


async def write_curiosity_entry(
    topic: str,
    reason: str,
    status: str = "pending",
    query: str = "",
) -> Path:
    """
    Record a new curiosity entry.
    Called when Sage identifies something she wants to investigate.
    """
    ensure_dirs(SAGE_CURIOSITY_DIR)
    stem = ts_filename(f"curiosity_{safe_stem(topic)[:20]}_")
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = (
        f"[{ts}]\n"
        f"[topic: {topic}]\n"
        f"[reason: {reason}]\n"
        f"[status: {status}]\n"
        f"[query: {query}]\n"
    )
    return await write_memory_entry(SAGE_CURIOSITY_DIR, stem, content)


async def update_curiosity_status(path: Path, status: str, query: str = "") -> None:
    """Update the status of an existing curiosity entry after search."""
    content = await read_memory_entry(path)
    if not content:
        return

    lines = content.splitlines()
    updated = []
    for line in lines:
        if line.startswith("[status:"):
            updated.append(f"[status: {status}]")
        elif line.startswith("[query:") and query:
            updated.append(f"[query: {query}]")
        else:
            updated.append(line)

    await write_text(path, "\n".join(updated) + "\n")


async def load_pending_curiosities() -> list[tuple[Path, str]]:
    """Load curiosity entries with status=pending."""
    files = await list_memory_files(SAGE_CURIOSITY_DIR)
    result = []
    for f in files:
        content = await read_memory_entry(f)
        if content and "[status: pending]" in content:
            result.append((f, content))
    return result


async def load_all_curiosities() -> list[tuple[Path, str]]:
    """Load all curiosity entries. Used for retrieval."""
    files = await list_memory_files(SAGE_CURIOSITY_DIR)
    result = []
    for f in files:
        content = await read_memory_entry(f)
        if content:
            result.append((f, content))
    return result


def _parse_curiosity_entry(text: str) -> tuple[str, str, str]:
    """
    Extract topic, reason, and query from a curiosity journal entry.

    Single source of truth for curiosity entry parsing.
    Previously duplicated in search/autonomy/trigger.py — that copy
    now imports from here.
    """
    topic = reason = query = ""
    for line in text.splitlines():
        if line.startswith("[topic:"):
            topic = line[7:].strip().rstrip("]")
        elif line.startswith("[reason:"):
            reason = line[8:].strip().rstrip("]")
        elif line.startswith("[query:"):
            query = line[7:].strip().rstrip("]")
    return topic, reason, query
