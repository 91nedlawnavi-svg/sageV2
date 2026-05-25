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

Phase 3B changes:
  - Retrieval scoring incorporates salience: final = similarity * salience
  - Retrieved artifacts receive a salience boost (re-relevance signal)
  - Anti-attractor cap: no single artifact key prefix can occupy more than
    half the result slots (prevents topic monopolization)
"""

import asyncio
from pathlib import Path
from typing import Optional

import httpx

from cognition.salience.tracker import get_salience_batch, boost_retrieval
from config.settings import TOP_K_SAGE_MEMORIES, RETRIEVAL_THRESHOLD
from memory.embeddings.cache import get_embedding, cosine_similarity
from memory.sage.reflections import load_all_sage_reflections
from memory.sage.worldview import load_all_worldview_entries
from memory.sage.curiosity import load_all_curiosities
from memory.sage.state import load_sage_state, build_state_injection
from utils.logger import log


# Phase 3B: maximum slots any single topic/type can occupy in results
_ATTRACTOR_CAP_RATIO = 0.5


async def _score_chunk(
    query_vec: list[float],
    label: str,
    content: str,
    client: httpx.AsyncClient,
) -> Optional[tuple[float, str, str]]:
    """Embed one chunk and return (raw_similarity, label, content). None on failure."""
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
    cycle_id: str = "",
) -> str:
    """
    Search Sage's internal memory for context relevant to the query.
    Returns a formatted string ready for prompt injection.
    Returns '' if nothing relevant found.

    Phase 3A: The continuity state is prepended as the PRIMARY anchor
    before any retrieved episodic reflections.

    Phase 3B: Scoring is now similarity * salience. Retrieved artifacts
    get a salience boost. Anti-attractor cap prevents topic monopolization.
    """
    state = load_sage_state()
    state_block = build_state_injection(state)

    query_vec = await get_embedding(query, client)
    if query_vec is None:
        return state_block if state_block else ""

    candidates: list[tuple[str, str]] = []

    reflections = await load_all_sage_reflections()
    for path, content in reflections[-50:]:
        candidates.append((f"sage/reflection/{path.stem}", content))

    worldview = await load_all_worldview_entries()
    for slug, content in worldview:
        candidates.append((f"sage/worldview/{slug}", content))

    curiosities = await load_all_curiosities()
    for path, content in curiosities[-30:]:
        candidates.append((f"sage/curiosity/{path.stem}", content))

    retrieved_block = ""

    if candidates:
        tasks = [
            _score_chunk(query_vec, label, content, client)
            for label, content in candidates
        ]
        results = await asyncio.gather(*tasks)

        # Phase 3B: apply salience weighting to raw similarity scores
        valid_results = [r for r in results if r is not None]
        if valid_results:
            all_keys = [r[1] for r in valid_results]
            salience_map = get_salience_batch(all_keys)

            weighted = []
            for sim_score, label, content in valid_results:
                salience = salience_map.get(label, 1.0)
                final_score = sim_score * salience
                if final_score >= threshold:
                    weighted.append((final_score, sim_score, label, content))

            weighted.sort(key=lambda x: x[0], reverse=True)

            # Phase 3B: anti-attractor cap — no type prefix can monopolize results
            top = _apply_attractor_cap(weighted, top_k)

            if top:
                log("retrieval", "hit",
                    domain="sage",
                    candidates=len(candidates),
                    returned=len(top),
                    top_final=round(top[0][0], 3),
                    top_raw_sim=round(top[0][1], 3),
                )
                parts = []
                for final_score, sim_score, label, content in top:
                    parts.append(f"[{label}]\n{content.strip()}")
                    # Phase 3B: boost salience for retrieved artifacts
                    if cycle_id:
                        boost_retrieval(label, cycle_id)

                retrieved_block = "\n\n".join(parts)
            else:
                log("retrieval", "miss", domain="sage", candidates=len(candidates))

    combined_parts = []
    if state_block:
        combined_parts.append(state_block)
    if retrieved_block:
        combined_parts.append(retrieved_block)

    return "\n\n".join(combined_parts)


def _apply_attractor_cap(
    scored: list[tuple[float, float, str, str]],
    top_k: int,
) -> list[tuple[float, float, str, str]]:
    """
    Select top_k results while enforcing anti-attractor constraint.

    No single type prefix (e.g., "sage/worldview") can occupy more than
    _ATTRACTOR_CAP_RATIO of the result slots. If a prefix would exceed
    the cap, lower-ranked items from other prefixes fill the remaining slots.

    This prevents a single topic from monopolizing Sage's retrieved context.
    """
    max_per_prefix = max(1, int(top_k * _ATTRACTOR_CAP_RATIO))
    prefix_counts: dict[str, int] = {}
    selected: list[tuple[float, float, str, str]] = []

    for item in scored:
        if len(selected) >= top_k:
            break
        label = item[2]
        # Prefix is first two path segments: "sage/reflection", "sage/worldview", etc.
        parts = label.split("/")
        prefix = "/".join(parts[:2]) if len(parts) >= 2 else label

        count = prefix_counts.get(prefix, 0)
        if count >= max_per_prefix:
            continue

        selected.append(item)
        prefix_counts[prefix] = count + 1

    return selected
