"""
backend/api/history.py — Persistent Conversation History Endpoint

Exposes GET /api/history so the frontend can reload conversation state
on page refresh without relying on localStorage or sessionStorage.

Architecture:
  - History is authoritative on the server (~/sage_data_v2/chat_history.jsonl)
  - Frontend is a stateless viewport: it fetches this on startup and renders
  - No new storage system is added; this reuses the existing JSONL history
    already written by _run_chat() via append_history()

Phase 2A compliance:
  - Directive spine untouched
  - Session object untouched
  - Only adds a read endpoint; does not write or mutate any state
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config.settings import HISTORY_FILE
from memory.storage.history import load_history

router = APIRouter()


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
