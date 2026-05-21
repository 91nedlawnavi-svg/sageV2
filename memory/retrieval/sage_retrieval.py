"""
memory/retrieval/sage_retrieval.py — Sage Internal Memory Retrieval

Searches across Sage's own memory domains:
  - Sage's reflections (her inner experience)
  - Sage's worldview entries (knowledge she's synthesized)
  - Sage's curiosity journal (what she's been wondering about)

Returns ONLY Sage-domain memories. This is her sense of self —
her continuity as an entity with her own inner life.

These memories are injected into prompts with controlled labeling so
the model understands this context comes from Sage's own perspective,
not from Elliot's narrative.
"""

import asyncio
from pathlib import Path
from typing import Optional

import httpx

from config.settings import TOP_K_SAGE_MEMORIES, RETRIEVAL_THRESHOLD
from memory.embeddings.cache import get_embedding, cosine_similarity
from memory.sage.reflections import load_all_sage_reflections
from memory.sage.worldview import load_all_worldview_entries
from memory.sage.curiosity import load_all_curiosities
from utils.logger import log


async def _score_chunk(
    query_vec: list[float],
    label: str,
    content: str,
    client: httpx.AsyncClient,
) -> Optional[tuple[float, str, str]]:
    """Embed one chunk and return (score, label, content). None on failure."""
    try:
        vec = await get_embedding(content[:600], client)
        if vec is None:
            return None
        score = cosine_similarity(query_vec, vec)
        return (score, label, content)
    except Exception as e:
        log("retrieval", "score_error", domain="sage", label=label, error=str(e))
        return None


async def retrieve_sage_memories(
    query: str,
    client: httpx.AsyncClient,
    top_k: int = TOP_K_SAGE_MEMORIES,
    threshold: float = RETRIEVAL_THRESHOLD,
) -> str:
    """
    Search Sage's internal memory for context relevant to the query.
    Returns a formatted string ready for prompt injection.
    Returns '' if nothing relevant found.
    """
    query_vec = await get_embedding(query, client)
    if query_vec is None:
        return ""

    candidates: list[tuple[str, str]] = []

    # 1. Sage's own reflections
    reflections = await load_all_sage_reflections()
    for path, content in reflections[-50:]:  # cap at 50 for performance
        candidates.append((f"sage/reflection/{path.stem}", content))

    # 2. Sage's worldview (synthesized topic knowledge)
    worldview = await load_all_worldview_entries()
    for slug, content in worldview:
        candidates.append((f"sage/worldview/{slug}", content))

    # 3. Sage's curiosity journal (for conversational self-awareness)
    curiosities = await load_all_curiosities()
    for path, content in curiosities[-30:]:
        candidates.append((f"sage/curiosity/{path.stem}", content))

    if not candidates:
        return ""

    tasks = [
        _score_chunk(query_vec, label, content, client)
        for label, content in candidates
    ]
    results = await asyncio.gather(*tasks)

    scored = [r for r in results if r is not None and r[0] >= threshold]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    if not top:
        log("retrieval", "miss", domain="sage", candidates=len(candidates))
        return ""

    log("retrieval", "hit",
        domain="sage",
        candidates=len(candidates),
        returned=len(top),
        top_score=round(top[0][0], 3),
    )

    parts = []
    for score, label, content in top:
        parts.append(f"[{label}]\n{content.strip()}")

    return "\n\n".join(parts)
