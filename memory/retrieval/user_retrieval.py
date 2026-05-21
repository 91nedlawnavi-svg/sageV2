"""
memory/retrieval/user_retrieval.py — User Memory Retrieval

Searches across Elliot's memory domains:
  - episodic memories
  - emotional themes
  - library entries (people, places, topics)
  - user-domain reflections

Returns ONLY user-domain memories. Never touches Sage's internal memory.
Sage's memories may be injected through a separate explicit call in
models/prompts/builder.py — not here.

Design mirrors V1's retrieval.py exactly, with these changes:
  1. Operates only on user-domain directories
  2. Uses user-specific loaders (memory/user/)
  3. Labels prefixed with "user/" for clarity in prompt injection
"""

import asyncio
from pathlib import Path
from typing import Optional

import httpx

from config.settings import (
    TOP_K_USER_MEMORIES,
    RETRIEVAL_THRESHOLD,
    EPISODIC_RETRIEVAL_CAP,
    REFLECTION_RETRIEVAL_CAP,
)
from memory.embeddings.cache import get_embedding, cosine_similarity
from memory.user.episodic import load_all_user_episodes, load_all_user_reflections
from memory.user.emotional import load_all_user_themes
from memory.user.library import load_all_library_entries
from utils.logger import log


async def _score_chunk(
    query_vec: list[float],
    label: str,
    content: str,
    client: httpx.AsyncClient,
) -> Optional[tuple[float, str, str]]:
    """Embed one memory chunk and return (score, label, content). None on failure."""
    try:
        vec = await get_embedding(content[:600], client)
        if vec is None:
            return None
        score = cosine_similarity(query_vec, vec)
        return (score, label, content)
    except Exception as e:
        log("retrieval", "score_error", domain="user", label=label, error=str(e))
        return None


async def retrieve_user_memories(
    query: str,
    client: httpx.AsyncClient,
    top_k: int = TOP_K_USER_MEMORIES,
    threshold: float = RETRIEVAL_THRESHOLD,
) -> str:
    """
    Search Elliot's memory layers for the query.
    Returns a formatted string ready for prompt injection.
    Returns '' if nothing relevant found.
    """
    query_vec = await get_embedding(query, client)
    if query_vec is None:
        return ""

    candidates: list[tuple[str, str]] = []

    # 1. Episodic memories (capped to most recent N for performance)
    episodes = await load_all_user_episodes()
    for path, content in episodes[-EPISODIC_RETRIEVAL_CAP:]:
        candidates.append((f"user/episodic/{path.stem}", content))

    # 2. Emotional themes
    themes = await load_all_user_themes()
    for name, content in themes:
        candidates.append((f"user/emotional/{name}", content))

    # 3. Library entries (people, places, topics)
    library = await load_all_library_entries()
    for label, content in library:
        candidates.append((label, content))

    # 4. User-domain reflections
    reflections = await load_all_user_reflections()
    for path, content in reflections[-REFLECTION_RETRIEVAL_CAP:]:
        candidates.append((f"user/reflection/{path.stem}", content))

    if not candidates:
        return ""

    # Score all candidates concurrently
    tasks = [
        _score_chunk(query_vec, label, content, client)
        for label, content in candidates
    ]
    results = await asyncio.gather(*tasks)

    scored = [r for r in results if r is not None and r[0] >= threshold]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    if not top:
        log("retrieval", "miss", domain="user", candidates=len(candidates))
        return ""

    log("retrieval", "hit",
        domain="user",
        candidates=len(candidates),
        above_threshold=len(scored),
        returned=len(top),
        top_score=round(top[0][0], 3),
    )

    parts = []
    for score, label, content in top:
        parts.append(f"[{label}]\n{content.strip()}")

    return "\n\n".join(parts)
