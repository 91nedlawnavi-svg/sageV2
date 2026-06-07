"""
cognition/user_model/library_extraction.py — Automatic Library Population

Reads a conversation digest, identifies notable entities in Elliot's world,
then writes or merges entries into the user library.

Logic preserved from V1's cognition/library_extraction.py.
Changes:
  1. Uses memory/user/library.py instead of inline file ops
  2. Imports point to module paths (post-V1)
  3. No behavioral changes
"""

import json
from typing import Optional

import httpx

from config.settings import LIBRARY_CATS
from memory.user.library import load_library_entry, write_library_entry
from models.inference.engine import nim_complete
from models.prompts.templates import (
    LIBRARY_EXTRACT_SYSTEM,
    LIBRARY_MERGE_SYSTEM,
    library_extract_prompt,
    library_merge_prompt,
)
from memory.storage.base import safe_stem
from utils.logger import log


def _parse_entities(raw: str) -> list[dict]:
    """Parse JSON array from model output. Returns [] on failure."""
    try:
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception as e:
        log("cognition", "library_json_parse_failed", error=str(e))
    return []


async def extract_and_populate_user_library(
    conversation_digest: str,
    client: httpx.AsyncClient,
) -> list[str]:
    """
    Extract notable entities from a conversation digest and write or merge
    them into the user library.

    Returns a list of written entry paths (for logging).
    """
    raw = await nim_complete(
        system=LIBRARY_EXTRACT_SYSTEM,
        user=library_extract_prompt(conversation_digest),
        client=client,
        max_tokens=600,
    )
    if not raw:
        return []

    entities = _parse_entities(raw)
    if not entities:
        return []

    written = []

    for item in entities:
        category = item.get("category", "").strip()
        name     = item.get("name", "").strip()
        note     = item.get("note", "").strip()

        if not category or not name or not note:
            continue

        if category not in LIBRARY_CATS:
            continue

        existing = await load_library_entry(category, name)

        if existing:
            merged = await nim_complete(
                system=LIBRARY_MERGE_SYSTEM,
                user=library_merge_prompt(existing, note),
                client=client,
                max_tokens=300,
            )
            if not merged:
                # Merge model unavailable — preserve existing entry unchanged.
                # Raw concatenation would corrupt the entry; skip this cycle instead.
                log("cognition", "user_library_merge_failed_skipped",
                    category=category, name=name)
                continue
            final = merged
        else:
            final = note

        await write_library_entry(category, name, final)
        log("cognition", "user_library_entry_written",
            category=category, name=name, merged=bool(existing))
        written.append(f"{category}/{safe_stem(name)}")

    return written
