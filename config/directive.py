"""
config/directive.py — Persistent Identity Directive Loader

Phase 2A: Identity Spine Restoration

The directive is Sage's immutable core identity — a first-class persistent
prompt injected at the TOP of every response generation cycle, before memory
retrieval context, before user episodic memory, before Sage's inner memory,
before search context.

Hierarchy (top to bottom, highest to lowest authority):
  1. directive.txt          ← THIS — identity spine (immutable during runtime)
  2. time context           ← temporal grounding
  3. user memory            ← Elliot's episodic/emotional/library context
  4. sage memory            ← Sage's reflections and worldview
  5. search context         ← transient external information

This is NOT a modular personality fragment. It is the persistent self that
all other context assembles around.

Key invariants (Phase 2A additions):
  - Directive is loaded from disk on startup and cached in memory
  - Directive is re-read from disk on every call (hot-reload) so live edits
    take effect on the next message without a server restart
  - Directive is NEVER overwritten by reflection systems — only by direct
    file edit (by the user/operator, not by any automated cognition)
  - Empty directive is rejected — server will not start without a directive
  - Directive remains a plain text file, editable via the frontend panel
"""

import asyncio
from pathlib import Path
from typing import Optional

from utils.logger import log

# Canonical location — sits at project root, outside all module dirs
# so it is clearly not a module artifact and is obviously operator-owned
DIRECTIVE_PATH = Path(__file__).parent.parent / "directive.txt"

# Module-level cache: loaded at startup, refreshed on every read
# (cheap — file is small; correctness beats micro-optimisation here)
_cached_directive: Optional[str] = None


def load_directive() -> str:
    """
    Load directive from disk.

    Called at server startup and on every request (hot-reload semantics).
    If the file is missing or empty, raises RuntimeError — the server
    should not run without an identity spine.

    Returns the directive text, stripped of leading/trailing whitespace.
    Raises RuntimeError if the file is absent or empty.
    """
    global _cached_directive

    if not DIRECTIVE_PATH.exists():
        raise RuntimeError(
            f"directive.txt not found at {DIRECTIVE_PATH}. "
            "Sage cannot start without an identity directive. "
            "Create directive.txt in the project root."
        )

    text = DIRECTIVE_PATH.read_text(encoding="utf-8").strip()

    if not text:
        raise RuntimeError(
            "directive.txt is empty. "
            "Sage's identity spine must not be blank."
        )

    _cached_directive = text
    return text


def get_directive() -> str:
    """
    Return the current directive, loading from disk if not yet cached.

    This is the hot-reload path: every call reads from disk so that a
    live edit takes effect immediately on the next request without restart.

    This does NOT raise on empty cache — it will load if needed.
    """
    return load_directive()


async def save_directive(content: str) -> None:
    """
    Persist a new directive text to disk.

    Called by the backend /api/directive (POST) route when the user
    edits the directive in the frontend panel.

    Rules:
    - Content is stripped before saving
    - Empty content is rejected (cannot blank the identity spine)
    - Write is atomic: written to a temp file, then renamed

    This is the ONLY path that may modify directive.txt at runtime.
    Reflection systems must never call this.
    """
    content = content.strip()
    if not content:
        raise ValueError("Directive cannot be empty.")

    # Atomic write: temp → rename prevents partial reads during save
    tmp = DIRECTIVE_PATH.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.rename(DIRECTIVE_PATH)

    # Invalidate cache so next get_directive() picks up the new content
    global _cached_directive
    _cached_directive = content

    log("directive", "directive_saved", length=len(content))


def directive_path() -> Path:
    """Return the canonical path to directive.txt (for API routes)."""
    return DIRECTIVE_PATH
