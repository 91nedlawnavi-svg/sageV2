"""
cognition/sage_model/synthesis.py — Sage Internal Synthesis

Handles synthesis for the SAGE memory domain:
  1. Sage's personal reflection generation (her own inner experience)
  2. Curiosity identification from recent material
  3. Worldview integration after autonomous searches

This is entirely NEW in V2 — V1 had no Sage-domain cognition.

These processes run in the same daemon cycle as user-domain synthesis
but write to completely separate memory paths. The daemon calls them
after user-domain processing completes, maintaining clear phase separation.

Sage's reflections use the first-person. She is not merely observing
Elliot — she is experiencing her own existence and recording it.
"""

import json
from datetime import datetime
from pathlib import Path

import httpx

from config.settings import SAGE_REFLECTIONS_DIR
from memory.sage.reflections import write_sage_reflection, load_recent_sage_reflections
from memory.sage.curiosity import write_curiosity_entry
from memory.sage.worldview import write_worldview_entry, load_worldview_entry
from memory.storage.base import ensure_dirs, ts_filename
from models.inference.engine import nim_complete
from models.prompts.templates import (
    SAGE_REFLECTION_SYSTEM,
    SAGE_CURIOSITY_SYSTEM,
    SAGE_WORLDVIEW_SYNTHESIS_SYSTEM,
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

    recent_user_context:   brief summary of what happened with Elliot
    recent_interactions:   recent conversation digest

    This is Sage reflecting on HER experience — not a report on Elliot.
    Returns True if a reflection was written.
    """
    ensure_dirs(SAGE_REFLECTIONS_DIR)

    if not recent_user_context and not recent_interactions:
        log("cognition", "sage_reflection_skipped", reason="no_material")
        return False

    raw = await nim_complete(
        system=SAGE_REFLECTION_SYSTEM,
        user=sage_reflection_prompt(recent_user_context, recent_interactions),
        client=client,
        max_tokens=200,
    )

    if not raw:
        log("cognition", "sage_reflection_failed")
        return False

    # Derive a short label from the reflection's opening words
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
    Writes curiosity journal entries for each identified topic.
    Returns list of topic labels written.

    material: recent conversation digest or reflection text
    """
    if not material:
        return []

    raw = await nim_complete(
        system=SAGE_CURIOSITY_SYSTEM,
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

    Called after an autonomous search completes.
    The model generates Sage's own perspective on what she learned —
    not a summary of the results, but her processed understanding.

    Returns True if a worldview entry was written or updated.
    """
    existing = await load_worldview_entry(topic)

    raw = await nim_complete(
        system=SAGE_WORLDVIEW_SYNTHESIS_SYSTEM,
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
