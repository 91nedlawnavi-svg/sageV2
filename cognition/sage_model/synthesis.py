"""
cognition/sage_model/synthesis.py — Sage Internal Synthesis

Handles synthesis for the SAGE memory domain:
  1. Sage's personal reflection generation (her own inner experience)
  2. Curiosity identification from recent material
  3. Worldview integration after autonomous searches

Phase 2A changes (Identity Spine Restoration):
  - All three synthesis functions now receive and inject the directive
  - Directive is passed as the cognitive anchor BEFORE any task instruction
  - Directive is NOT modified or stored by any synthesis function
  - Synthesis outputs (reflections, curiosities, worldview) remain in their
    own memory paths — they can evolve Sage's perspective but cannot write
    back to directive.txt
  - The directive is what Sage IS; synthesis is what Sage LEARNS

Cognitive hierarchy enforced in every nim_complete call:
  system = directive + "\n\n" + task-specific system prompt
  user   = task-specific data prompt

The directive acts as the stable interpretive lens. Task prompts operate
within that lens, not above it.

This is entirely new in V2 — V1 had no Sage-domain cognition.
These processes run in the same daemon cycle as user-domain synthesis
but write to completely separate memory paths (Phase 1 invariants preserved).
"""

import json
from pathlib import Path

import httpx

from config.directive import get_directive         # Phase 2A: identity spine
from config.settings import SAGE_REFLECTIONS_DIR
from memory.sage.reflections import write_sage_reflection, load_recent_sage_reflections
from memory.sage.curiosity import write_curiosity_entry
from memory.sage.worldview import write_worldview_entry, load_worldview_entry
from memory.storage.base import ensure_dirs
from models.inference.engine import nim_complete
from models.prompts.templates import (
    compose_reflection_system,
    compose_curiosity_system,
    compose_worldview_system,
    sage_reflection_prompt,
    sage_curiosity_prompt,
    sage_worldview_prompt,
)
from utils.logger import log


async def generate_sage_reflection(
    recent_user_context: str,
    recent_interactions: str,
    client: httpx.AsyncClient,
) -> bool:
    """
    Generate Sage's own internal reflection from recent activity.

    Phase 2A: The directive is loaded and prepended to the system prompt
    before the reflection task instruction. This means Sage's reflection
    is always grounded in who she IS, not just what happened.

    The reflection is written to Sage's memory path. It CANNOT write back
    to directive.txt — that boundary is enforced by the write path:
    write_sage_reflection() writes to SAGE_REFLECTIONS_DIR, never to
    directive.txt.

    Returns True if a reflection was written.
    """
    ensure_dirs(SAGE_REFLECTIONS_DIR)

    if not recent_user_context and not recent_interactions:
        log("cognition", "sage_reflection_skipped", reason="no_material")
        return False

    # Phase 2A: directive loaded fresh here (hot-reload semantics).
    # Each synthesis cycle uses the current directive, not a startup snapshot.
    directive = get_directive()

    raw = await nim_complete(
        system=compose_reflection_system(directive),
        user=sage_reflection_prompt(recent_user_context, recent_interactions),
        client=client,
        max_tokens=200,
    )

    if not raw:
        log("cognition", "sage_reflection_failed")
        return False

    words = raw.strip().split()[:4]
    label = "_".join(w.lower() for w in words if w.isalpha())[:28]

    await write_sage_reflection(raw.strip(), label=label)
    log("cognition", "sage_reflection_written", label=label)
    return True


async def identify_sage_curiosities(
    material: str,
    client: httpx.AsyncClient,
) -> list[str]:
    """
    Identify topics Sage has become curious about from recent activity.

    Phase 2A: The directive anchors what kinds of things Sage finds genuinely
    interesting — her curiosity is not generic topic extraction but emerges
    from her actual character. The directive lens prevents curiosity from
    drifting toward assistant-like 'helpful research' framing.

    Curiosity entries are written to their own memory path.
    The directive is never modified by curiosity synthesis.

    Returns list of topic labels written.
    """
    if not material:
        return []

    directive = get_directive()

    raw = await nim_complete(
        system=compose_curiosity_system(directive),
        user=sage_curiosity_prompt(material),
        client=client,
        max_tokens=400,
    )

    if not raw:
        return []

    topics = _parse_curiosity_list(raw)
    if not topics:
        return []

    written = []
    for item in topics:
        topic  = item.get("topic", "").strip()
        reason = item.get("reason", "").strip()
        query  = item.get("query", "").strip()

        if not topic or not query:
            continue

        await write_curiosity_entry(topic=topic, reason=reason, query=query)
        log("cognition", "sage_curiosity_recorded", topic=topic)
        written.append(topic)

    return written


async def integrate_search_into_worldview(
    topic: str,
    search_summary: str,
    client: httpx.AsyncClient,
) -> bool:
    """
    Synthesize a search result into Sage's evolving worldview for the topic.

    Phase 2A: The directive ensures worldview synthesis is genuinely Sage's
    processed understanding — not a neutral summarizer's output. The model
    integrates new knowledge through the lens of who Sage is: intellectually
    alive, honest about uncertainty, connecting to what she already knew.

    The worldview entry is written to Sage's worldview memory path.
    The directive is never modified by worldview synthesis.
    Existing worldview knowledge is passed as context, not as identity —
    Sage's identity comes from the directive, her knowledge from worldview.

    Returns True if a worldview entry was written or updated.
    """
    existing  = await load_worldview_entry(topic)
    directive = get_directive()

    raw = await nim_complete(
        system=compose_worldview_system(directive),
        user=sage_worldview_prompt(
            topic=topic,
            search_summary=search_summary,
            existing_knowledge=existing or "",
        ),
        client=client,
        max_tokens=250,
    )

    if not raw:
        log("cognition", "sage_worldview_synthesis_failed", topic=topic)
        return False

    await write_worldview_entry(topic=topic, perspective=raw.strip(), source="search")
    log("cognition", "sage_worldview_updated", topic=topic, had_existing=bool(existing))
    return True


def _parse_curiosity_list(raw: str) -> list[dict]:
    """Parse JSON array of curiosity dicts from model output."""
    try:
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception as e:
        log("cognition", "sage_curiosity_json_parse_failed", error=str(e))
    return []
