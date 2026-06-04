"""
cognition/emotional/user_emotional.py — User Emotional Pattern Extraction

Extracts and persists emotional themes from conversation digests.
Operates ONLY on the USER memory domain — Elliot's emotional patterns.

Logic preserved exactly from V1's cognition/emotional_analysis.py.
Changes:
  1. Uses memory/user/emotional.py instead of memory/emotional.py
  2. Module path reflects V2 domain separation
  3. No behavioral changes — same prompts, same merge logic
"""

import json
from typing import Optional

import httpx

from memory.user.emotional import load_user_theme, write_user_emotional_theme
from models.inference.engine import nim_complete
from models.prompts.templates import (
    EMOTIONAL_EXTRACT_SYSTEM,
    EMOTIONAL_MERGE_SYSTEM,
    emotional_extract_prompt,
    emotional_merge_prompt,
)
from utils.logger import log


def _parse_themes(raw: str) -> list[dict]:
    """Parse JSON array of theme dicts from model output."""
    try:
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception as e:
        log("cognition", "user_emotional_json_parse_failed", error=str(e))
    return []


async def extract_and_persist_user_emotions(
    conversation_digest: str,
    client: httpx.AsyncClient,
) -> list[str]:
    """
    Extract emotional themes from a conversation digest and persist them
    to the USER memory domain.

    Returns list of theme names that were updated.
    """
    raw = await nim_complete(
        system=EMOTIONAL_EXTRACT_SYSTEM,
        user=emotional_extract_prompt(conversation_digest),
        client=client,
        max_tokens=600,
    )
    if not raw:
        return []

    themes = _parse_themes(raw)
    if not themes:
        log("cognition", "user_emotional_parse_failed")
        return []

    updated = []

    for item in themes:
        theme_name     = item.get("theme", "").strip()
        interpretation = item.get("interpretation", "").strip()

        if not theme_name or not interpretation:
            continue

        existing = await load_user_theme(theme_name)

        if existing:
            merged = await nim_complete(
                system=EMOTIONAL_MERGE_SYSTEM,
                user=emotional_merge_prompt(existing, interpretation),
                client=client,
                max_tokens=300,
            )
            if not merged:
                log("cognition", "user_emotional_merge_failed_preserved",
                    theme=theme_name, reason="merge_returned_empty")
                continue
            final_text = merged
        else:
            final_text = interpretation

        await write_user_emotional_theme(theme_name, final_text)
        log("cognition", "user_emotional_theme_updated",
            theme=theme_name, merged=bool(existing))
        updated.append(theme_name)

    return updated
