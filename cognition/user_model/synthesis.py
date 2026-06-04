"""
cognition/user_model/synthesis.py — User Memory Synthesis

Handles synthesis for the USER memory domain:
  1. Episodic extraction from conversation digests (Elliot's events)
  2. User-domain reflection generation (about Elliot's patterns)
  3. Library entity extraction and population

The user-domain reflection is a reflection ON Elliot — observing his
patterns from Sage's perspective, but stored as Elliot's cognitive arc,
not as Sage's inner experience.

Preserved from V1's cognition/synthesis.py with domain separation applied.
"""

import json
from datetime import datetime
from pathlib import Path

import httpx

from config.settings import USER_REFLECTIONS_DIR
from memory.user.episodic import load_recent_user_episodes, write_user_episode
from memory.user.emotional import retrieve_relevant_user_themes
from memory.storage.base import ensure_dirs, ts_filename, write_memory_entry
from models.inference.engine import nim_complete
from models.prompts.templates import (
    EPISODIC_SYSTEM,
    USER_REFLECTION_SYSTEM,
    episodic_prompt,
    user_reflection_prompt,
)
from utils.logger import log


async def extract_user_episode(
    conversation_digest: str,
    client: httpx.AsyncClient,
) -> bool:
    """
    Generate and persist one episodic memory for the user from a conversation digest.
    Returns True if an episode was written, False if skipped.
    """
    raw = await nim_complete(
        system=EPISODIC_SYSTEM,
        user=episodic_prompt(conversation_digest),
        client=client,
        max_tokens=300,
    )

    if not raw or raw.strip().upper() == "SKIP":
        log("cognition", "user_episodic_skipped")
        return False

    words = raw.strip().split()[:4]
    label = "_".join(w.lower() for w in words if w.isalpha())[:32]

    await write_user_episode(summary=raw.strip(), label=label)
    log("cognition", "user_episode_written", label=label)
    return True


async def generate_user_reflection(client: httpx.AsyncClient) -> bool:
    """
    Generate a reflection about Elliot's patterns from accumulated memory.
    Persists to USER_REFLECTIONS_DIR.
    Returns True if a reflection was written.
    """
    ensure_dirs(USER_REFLECTIONS_DIR)

    recent_episodes = await load_recent_user_episodes(n=5)
    episodic_text   = "\n\n".join(recent_episodes) if recent_episodes else ""

    if episodic_text:
        themes = await retrieve_relevant_user_themes(episodic_text, client, top_k=3)
    else:
        themes = []
    emotional_text = "\n\n".join(content for _, content in themes) if themes else ""

    if not episodic_text and not emotional_text:
        log("cognition", "user_reflection_skipped", reason="no_material")
        return False

    raw = await nim_complete(
        system=USER_REFLECTION_SYSTEM,
        user=user_reflection_prompt(episodic_text, emotional_text),
        client=client,
        max_tokens=200,
    )

    if not raw:
        log("cognition", "user_reflection_failed")
        return False

    ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
    stem = ts_filename("user_reflection_")
    content = f"[domain: user] [{ts}]\n{raw}\n"
    await write_memory_entry(USER_REFLECTIONS_DIR, stem, content)
    log("cognition", "user_reflection_written", stem=stem)
    return True
