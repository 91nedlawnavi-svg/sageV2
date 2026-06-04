"""
backend/api/history.py — Persistent Conversation History Endpoint

Exposes GET /api/history so the frontend can reload conversation state
on page refresh without relying on localStorage or sessionStorage.

Archive endpoint (POST /api/history/archive) rolls the current chat history
into a timestamped archive file and starts fresh. Memory is unaffected —
only the visible chat UI is cleared.

Architecture:
  - History is authoritative on the server (~/sage_data_v2/chat_history.jsonl)
  - Frontend is a stateless viewport: it fetches this on startup and renders
  - Archives live at ~/sage_data_v2/history_archive/ with timestamps
  - Archived history remains accessible to retrieval (future feature)

Phase 2A compliance:
  - Directive spine untouched
  - Session object untouched
"""

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config.settings import HISTORY_FILE, BASE_DIR
from memory.storage.history import load_history
from utils.logger import log

router = APIRouter()

# Archive directory
ARCHIVE_DIR = BASE_DIR / "history_archive"


@router.get("/api/history")
async def get_history():
    """
    Return the full conversation history as a list of {role, content} objects.

    The frontend calls this on page load to reconstruct the message list.
    Streaming fragments are never written to history (only completed turns are),
    so no partial messages will appear on reload.

    Returns:
        {"messages": [{"role": "user"|"assistant", "content": "..."}]}
    """
    history = await load_history(HISTORY_FILE)
    # Strip timestamps — frontend only needs role + content
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return JSONResponse({"messages": messages})


@router.post("/api/history/archive")
async def archive_history():
    """
    Archive the current chat history and start fresh.

    - Moves chat_history.jsonl to history_archive/chat_YYYYMMDD_HHMMSS.jsonl
    - Creates empty chat_history.jsonl
    - Memory is NOT affected — episodic/emotional/library memories remain intact
    - Only the visible chat UI is cleared

    Returns:
        {"ok": true, "archived_to": "filename", "message_count": N}
    """
    if not HISTORY_FILE.exists():
        return JSONResponse({"ok": True, "archived_to": None, "message_count": 0})

    # Load current history to count messages
    history = await load_history(HISTORY_FILE)
    message_count = len(history)

    if message_count == 0:
        return JSONResponse({"ok": True, "archived_to": None, "message_count": 0})

    # Create archive directory if needed
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Generate timestamped archive filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"chat_{timestamp}.jsonl"
    archive_path = ARCHIVE_DIR / archive_name

    # Move current history to archive
    shutil.move(str(HISTORY_FILE), str(archive_path))

    # Create empty history file
    HISTORY_FILE.touch()

    log("history", "archived",
        archive_path=str(archive_path),
        message_count=message_count)

    return JSONResponse({
        "ok": True,
        "archived_to": archive_name,
        "message_count": message_count,
    })
