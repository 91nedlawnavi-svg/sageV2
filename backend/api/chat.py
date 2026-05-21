"""
backend/api/chat.py — Chat API Routes

Handles the user-facing conversation endpoints:
  POST /api/chat          — start a streaming inference job
  GET  /api/poll/<jid>    — poll a job for new tokens
  POST /api/retry         — retry the last assistant turn

This replaces the flask routes in V1's launch.py, extracted here so
the route logic is separate from the server boot in launch.py.

The route handlers are intentionally thin: they validate input, dispatch
to the orchestrator, and return. All cognition happens in other modules.
"""

import asyncio
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.orchestration.event_bus import publish
from backend.orchestration.job_store import JobStore
from backend.orchestration.session import ConversationSession
from config.settings import HISTORY_TURNS
from memory.retrieval.user_retrieval import retrieve_user_memories
from memory.retrieval.sage_retrieval import retrieve_sage_memories
from memory.storage.history import (
    append_history,
    history_for_prompt,
    load_history,
    strip_last_assistant,
)
from models.inference.engine import chat_stream
from models.prompts.templates import build_chat_messages
from config.settings import HISTORY_FILE
from utils.logger import log


router = APIRouter()

# These are set by the server at startup via `init_routes()`
_job_store: Optional[JobStore] = None
_session:   Optional[ConversationSession] = None
_client:    Optional[httpx.AsyncClient] = None
_directive: str = ""

# Maximum accepted length for the search_context field.
# Enforces the architecture's intent that this carries structured context,
# not arbitrary text. 4000 chars accommodates any well-formed format_search_context()
# output while blocking obvious oversized injection attempts.
MAX_SEARCH_CONTEXT_LEN = 4000


def init_routes(
    job_store: JobStore,
    session: ConversationSession,
    client: httpx.AsyncClient,
    directive: str,
) -> None:
    """Inject dependencies from the server into this module."""
    global _job_store, _session, _client, _directive
    _job_store = job_store
    _session   = session
    _client    = client
    _directive = directive


# ── Request / Response models ─────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    search_context: Optional[str] = ""


# ── Routes ────────────────────────────────────────────────────────────

@router.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Start a streaming inference job for one user message.
    Returns {jid} immediately. Client polls /api/poll/<jid> for tokens.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message.")

    if len(req.search_context or "") > MAX_SEARCH_CONTEXT_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"search_context exceeds maximum length ({MAX_SEARCH_CONTEXT_LEN} chars).",
        )

    jid = await _job_store.create()
    await publish("user_message_received", {
        "user_input": req.message,
        "jid":        jid,
    })

    asyncio.create_task(
        _run_chat(
            jid=jid,
            user_input=req.message,
            search_context=req.search_context or "",
        ),
        name=f"chat.{jid}",
    )

    return JSONResponse({"jid": jid})


@router.get("/api/poll/{jid}")
async def poll(jid: str, frm: int = 0):
    """
    Poll a streaming job for new tokens since offset `frm`.
    Returns {found, text, total, done, error, status}.
    """
    data = await _job_store.read(jid, frm=frm)
    if not data.get("found"):
        raise HTTPException(status_code=404, detail="Job not found.")
    return JSONResponse(data)


@router.post("/api/retry")
async def retry():
    """
    Re-run the last assistant response.
    Strips the last assistant history entry, then re-runs the last user message.
    """
    history = await load_history(HISTORY_FILE)

    # Find the last user message
    last_user = None
    for turn in reversed(history):
        if turn.get("role") == "user":
            last_user = turn.get("content", "")
            break

    if not last_user:
        raise HTTPException(status_code=400, detail="No prior user message to retry.")

    await strip_last_assistant(HISTORY_FILE)

    # Remove the last assistant and user turns from the session digest so that
    # _run_chat()'s unconditional record_turn("user", ...) does not double-record
    # the user message, which would inflate word frequency and episodic extraction.
    digest = _session._recent_digest
    if digest and digest[-1].startswith("ASSISTANT:"):
        digest.pop()
    if digest and digest[-1].startswith("USER:"):
        digest.pop()

    jid = await _job_store.create()
    asyncio.create_task(
        _run_chat(jid=jid, user_input=last_user, search_context=""),
        name=f"retry.{jid}",
    )

    return JSONResponse({"jid": jid})


# ── Core streaming task ───────────────────────────────────────────────

async def _run_chat(jid: str, user_input: str, search_context: str) -> None:
    """
    Background task: build prompt, stream response, record history,
    update session, publish events.
    """
    await _job_store.set_status(jid, "thinking")

    # Record user turn in session and history
    _session.record_turn("user", user_input)
    await append_history(HISTORY_FILE, "user", user_input)

    # Retrieve memories in parallel
    user_mem, sage_mem = await asyncio.gather(
        retrieve_user_memories(user_input, _client),
        retrieve_sage_memories(user_input, _client),
    )

    history = await load_history(HISTORY_FILE)
    history_msgs = history_for_prompt(history[:-1], HISTORY_TURNS)

    messages = build_chat_messages(
        directive=_directive,
        user_input=user_input,
        history=history_msgs,
        user_memory=user_mem,
        sage_memory=sage_mem,
        search_context=search_context,
    )

    await _job_store.set_status(jid, "streaming")

    full_response = []
    try:
        async for token in chat_stream(messages, _client):
            full_response.append(token)
            await _job_store.append_chunk(jid, token)
    except Exception as e:
        err = f"\n\n⚠️ Streaming error: {e}"
        await _job_store.append_chunk(jid, err)
        await _job_store.finish(jid, error=str(e))
        log("api", "chat_stream_error", jid=jid, error=str(e))
        return

    response_text = "".join(full_response)

    # Record assistant turn
    _session.record_turn("assistant", response_text)
    await append_history(HISTORY_FILE, "assistant", response_text)

    await _job_store.finish(jid)
    await _job_store.purge_done()

    # Notify the system that a response completed (daemon listens here)
    await publish("assistant_response_done", {
        "response":    response_text,
        "jid":         jid,
        "digest":      _session.get_digest(),
        "idle_seconds": 0.0,
    })

    log("api", "chat_complete", jid=jid, response_len=len(response_text))
