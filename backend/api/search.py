"""
backend/api/search.py — Search API Routes

Handles user-triggered search requests from the frontend.

POST /api/search  — execute a search and return the context block

User-triggered searches:
  - bypass the autonomous budget (they are explicit user intent)
  - are NOT persisted to Sage's search log (they are Elliot's lookups)
  - return the structured context block for the frontend to inject
    into the next /api/chat call via the search_context field

This separation ensures user searches and Sage's autonomous searches
remain distinguishable in memory provenance.
"""

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from search.pipeline import run_search
from utils.logger import log

router = APIRouter()

_client: Optional[httpx.AsyncClient] = None


def init_search_routes(client: httpx.AsyncClient) -> None:
    """Inject shared httpx client."""
    global _client
    _client = client


class SearchRequest(BaseModel):
    query:  str
    reason: Optional[str] = "User requested search."


@router.post("/api/search")
async def search(req: SearchRequest):
    """
    Execute a user-triggered web search.

    Returns the structured context_block string for injection into
    the next chat request's search_context field.

    Does NOT count against the autonomous search budget.
    Does NOT write to Sage's search log.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Empty query.")

    outcome = await run_search(
        query=req.query.strip(),
        reason=req.reason or "User requested search.",
        initiator="user",
        client=_client,
        persist_to_sage_memory=False,   # user search — not Sage's memory
    )

    log("api", "user_search_complete",
        query=req.query,
        result_count=outcome.result_count,
        success=outcome.success)

    return JSONResponse({
        "query":         outcome.query,
        "summary":       outcome.summary,
        "context_block": outcome.context_block,
        "result_count":  outcome.result_count,
        "success":       outcome.success,
    })
