"""
backend/api/chat.py — Chat API Routes

Handles the user-facing conversation endpoints:
  POST /api/chat       — start a streaming inference job
  GET  /api/poll/<jid> — poll a job for new tokens
  POST /api/retry      — retry the last assistant turn

Phase 2A changes (Identity Spine Restoration):
  - `_directive` module-level string REMOVED
  - `directive` parameter REMOVED from init_routes()
  - get_directive() called inside _run_chat() on every request
    -> hot-reload: live edits to directive.txt take effect immediately
  - Directive injected FIRST in build_chat_messages, above all memory
  - Callers of init_routes() must drop the `directive=` argument
"""

import asyncio
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.orchestration.event_bus import publish
from backend.orchestration.job_store import JobStore
from backend.orchestration.session import ConversationSession
from config.directive import get_directive          # Phase 2A: persistent identity spine
from config.settings import HISTORY_TURNS, HISTORY_FILE
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
from utils.logger import log


router = APIRouter()

_job_store: Optional[JobStore] = None
_session:   Optional[ConversationSession] = None
_client:    Optional[httpx.AsyncClient] = None

# Phase 2A: _directive intentionally NOT stored here.
# Directive ownership lives in config/directive.py.
# get_directive() is called per-request for hot-reload semantics.
# API routes for directive read/write: backend/api/directive.py

MAX_SEARCH_CONTEXT_LEN = 4000


def init_routes(
    job_store: JobStore,
    session: ConversationSession,
    client: httpx.AsyncClient,
) -> None:
    """
    Inject runtime dependencies.

    Phase 2A: `directive: str` parameter removed.
    Directive is loaded fresh on every request via get_directive().
    Callers (launch.py) must remove the `directive=` argument.
    """
    global _job_store, _session, _client
    _job_store = job_store
    _session   = session
    _client    = client


# ── Request models ────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    search_context: Optional[str] = ""


# ── Routes ────────────────────────────────────────────────────────────

@router.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Start a streaming inference job for one user message.
    Returns {jid} immediately; client polls /api/poll/<jid> for tokens.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message.")
    if len(req.search_context or "") > MAX_SEARCH_CONTEXT_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"search_context exceeds maximum length ({MAX_SEARCH_CONTEXT_LEN} chars).",
        )

    jid = await _job_store.create()
    await publish("user_message_received", {"user_input": req.message, "jid": jid})

    asyncio.create_task(
        _run_chat(jid=jid, user_input=req.message, search_context=req.search_context or ""),
        name=f"chat.{jid}",
    )
    return JSONResponse({"jid": jid})


@router.get("/api/poll/{jid}")
async def poll(jid: str, frm: int = 0):
    """Poll a streaming job for new tokens since offset `frm`."""
    data = await _job_store.read(jid, frm=frm)
    if not data.get("found"):
        raise HTTPException(status_code=404, detail="Job not found.")
    return JSONResponse(data)


@router.post("/api/retry")
async def retry():
    """Re-run the last assistant response from the last user message."""
    history = await load_history(HISTORY_FILE)

    last_user = None
    for turn in reversed(history):
        if turn.get("role") == "user":
            last_user = turn.get("content", "")
            break

    if not last_user:
        raise HTTPException(status_code=400, detail="No prior user message to retry.")

    await strip_last_assistant(HISTORY_FILE)

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
    Background task: build prompt, stream response, record history, publish events.

    Phase 2A — Directive injection order:
      get_directive() is called HERE, immediately before prompt assembly.
      This guarantees:
        1. The directive is always current (hot-reload: reads from disk).
        2. The directive is injected FIRST, structurally above all memory context.
        3. No code path reaches build_chat_messages() without a live directive.
        4. Reflection/cognition systems cannot affect what directive is used here —
           they write to their own memory paths and never touch directive.txt.
    """
    await _job_store.set_status(jid, "thinking")

    _session.record_turn("user", user_input)
    await append_history(HISTORY_FILE, "user", user_input)

    # Phase 2A: directive loaded first, before memory retrieval.
    # It is structurally above all retrieved context in the prompt.
    directive = get_directive()

    # Memory retrieval runs in parallel after directive load.
    # Directive is independent of memory — it must never be derived from it.
    user_mem, sage_mem = await asyncio.gather(
        retrieve_user_memories(user_input, _client),
        retrieve_sage_memories(user_input, _client),
    )

    history      = await load_history(HISTORY_FILE)
    history_msgs = history_for_prompt(history[:-1], HISTORY_TURNS)

    # Prompt assembly — directive sits structurally first in build_chat_messages
    messages = build_chat_messages(
        directive=directive,
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

    _session.record_turn("assistant", response_text)
    await append_history(HISTORY_FILE, "assistant", response_text)

    await _job_store.finish(jid)
    await _job_store.purge_done()

    await publish("assistant_response_done", {
        "response":     response_text,
        "jid":          jid,
        "digest":       _session.get_digest(),
        "idle_seconds": 0.0,
    })

    log("api", "chat_complete", jid=jid, response_len=len(response_text))
