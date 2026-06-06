"""
memory/user/emotional.py — User Emotional Memory Layer

Stores interpretations of Elliot's emotional patterns:
  - recurring emotional themes
  - motivational undercurrents
  - how Elliot relates to people / situations over time

Each file represents one ongoing emotional theme.
Files are updated (merged), not duplicated.

Format per file:
  [theme_name]
  [last_updated]
  [interpretation text]

This is a USER domain memory — Elliot's emotional landscape.
Sage's own emotional interpretations go in memory/sage/reflections.py.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from config.settings import USER_EMOTIONAL_DIR, RETRIEVAL_THRESHOLD
from memory.embeddings.cache import cosine_similarity, get_embedding
from memory.storage.base import (
    ensure_dirs,
    list_memory_files,
    read_memory_entry,
    safe_stem,
    write_text,
)


def _theme_path(theme_name: str) -> Path:
    """Derive the file path for a named emotional theme."""
    return USER_EMOTIONAL_DIR / f"{safe_stem(theme_name)}.txt"


async def write_user_emotional_theme(theme_name: str, interpretation: str) -> Path:
    """
    Write or overwrite an emotional theme file for the user.
    Called by emotional_analysis after producing a new interpretation.
    """
    ensure_dirs(USER_EMOTIONAL_DIR)
    path = _theme_path(theme_name)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"[{theme_name}]\n[updated: {ts}]\n{interpretation.strip()}\n"
    await write_text(path, content)
    return path


async def load_all_user_themes() -> list[tuple[str, str]]:
    """Load all emotional themes as (name, content) pairs."""
    files = await list_memory_files(USER_EMOTIONAL_DIR)
    result = []
    for f in files:
        content = await read_memory_entry(f)
        if content:
            result.append((f.stem, content))
    return result


async def retrieve_relevant_user_themes(
    query: str,
    client: httpx.AsyncClient,
    top_k: int = 3,
    threshold: float = RETRIEVAL_THRESHOLD,
) -> list[tuple[str, str]]:
    """
    Return the top_k emotional themes most relevant to query.
    Falls back to [] if embedding service is unavailable.
    """
    themes = await load_all_user_themes()
    if not themes:
        return []

    query_vec = await get_embedding(query, client, doc_type="query")
    if query_vec is None:
        return []

    async def _score(name: str, content: str):
        vec = await get_embedding(content[:600], client, doc_type="passage")
        if vec is None:
            return None
        return (cosine_similarity(query_vec, vec), name, content)

    results = await asyncio.gather(*[_score(n, c) for n, c in themes])
    scored = [r for r in results if r is not None and r[0] >= threshold]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(name, content) for _, name, content in scored[:top_k]]


async def load_user_theme(theme_name: str) -> Optional[str]:
    """Load a single theme by name."""
    path = _theme_path(theme_name)
    if not path.exists():
        return None
    return await read_memory_entry(path)


async def list_user_theme_names() -> list[str]:
    """Return the stem names of all emotional theme files."""
    files = await list_memory_files(USER_EMOTIONAL_DIR)
    return [f.stem for f in files]
