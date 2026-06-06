"""
backend/api/memory.py — Memory & Status API Routes

Endpoints for:
  GET  /api/status           — server health + session info + budget
  GET  /api/library          — list all library entries by category
  GET  /api/library/<cat>/<name> — read one library entry
  POST /api/library/<cat>/<name> — write/overwrite a library entry
  DELETE /api/library/<cat>/<name> — delete a library entry
  GET  /api/memories/user    — recent user episodic memories (for UI display)
  GET  /api/memories/sage    — recent sage reflections (for UI display)
  GET  /api/search/budget    — autonomous search budget status

All write endpoints operate ONLY on user-domain memory (library).
Sage-domain memory is written exclusively by the daemon — never via API.
This enforces the dual-domain boundary at the network layer.
"""

from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config.settings import LIBRARY_CATS, HISTORY_FILE
from memory.user.library import (
    delete_library_entry,
    list_library_tree,
    load_library_entry,
    write_library_entry,
    load_people_with_relations,  # PHASE 4 #3
)
from memory.user.episodic import load_recent_user_episodes
from memory.sage.reflections import load_recent_sage_reflections
from memory.storage.history import load_history
from cognition.threads.store import get_active_threads, load_thread_index
from search.autonomy.budget import get_budget_status
from utils.logger import log

router = APIRouter()

_session   = None
_daemon    = None
_directive = ""


def init_memory_routes(session, daemon) -> None:
    """Inject dependencies from server."""
    global _session, _daemon, _directive
    _session   = session
    _daemon    = daemon


# ── Status ────────────────────────────────────────────────────────────

@router.get("/api/status")
async def status():
    """Server health, session state, daemon state, search budget."""
    budget = get_budget_status()
    history = await load_history(HISTORY_FILE)

    return JSONResponse({
        "status":         "ok",
        "session_turns":  _session.session_turns if _session else 0,
        "history_turns":  len(history),
        "daemon_running": _daemon.is_running if _daemon else False,
        "daemon_last_run": _daemon.last_run_ts if _daemon else 0.0,
        "search_budget":  budget,
        "memory_domains": ["user", "sage"],
    })


# ── Library ───────────────────────────────────────────────────────────

@router.get("/api/library")
async def library_tree():
    """Return {category: [name_stems]} for all library categories."""
    tree = await list_library_tree()
    return JSONResponse({"library": tree})

@router.get("/api/people/network")
async def library_people_network():
    """PHASE 4 #3: Return people with parsed relations for network view / cognition tie-in.
    (Path chosen to avoid collision with dynamic /api/library/{cat}/{name} catch-all.)
    """
    people = await load_people_with_relations()
    return JSONResponse({"people_network": people})

# Compat alias (old path may have been used in early Phase 4 work)
@router.get("/api/library/people/network")
async def library_people_network_compat():
    people = await load_people_with_relations()
    return JSONResponse({"people_network": people})


@router.get("/api/library/{category}/{name}")
async def library_get(category: str, name: str):
    """Read one library entry."""
    if category not in LIBRARY_CATS:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}")
    content = await load_library_entry(category, name)
    if content is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return JSONResponse({"category": category, "name": name, "content": content})


class LibraryWriteRequest(BaseModel):
    content: str


@router.post("/api/library/{category}/{name}")
async def library_write(category: str, name: str, req: LibraryWriteRequest):
    """Write or overwrite a library entry (user domain only)."""
    if category not in LIBRARY_CATS:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}")
    # Allow empty content for new entries / clearing notes
    await write_library_entry(category, name, req.content or "")
    log("api", "library_written", category=category, name=name)
    return JSONResponse({"ok": True, "category": category, "name": name})


@router.delete("/api/library/{category}/{name}")
async def library_delete(category: str, name: str):
    """Delete a library entry."""
    if category not in LIBRARY_CATS:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}")
    deleted = await delete_library_entry(category, name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entry not found.")
    log("api", "library_deleted", category=category, name=name)
    return JSONResponse({"ok": True})


# ── Memory display ────────────────────────────────────────────────────

@router.get("/api/memories/user")
async def user_memories(n: int = 8):
    """Return recent user episodic memories for the UI panel."""
    episodes = await load_recent_user_episodes(n=min(n, 20))
    return JSONResponse({"episodes": episodes})


@router.get("/api/memories/sage")
async def sage_memories(n: int = 5):
    """
    Return Sage's recent internal reflections.
    Read-only — never writable via API.
    PHASE 4 #7: Include active threads for structured context.
    """
    reflections = await load_recent_sage_reflections(n=min(n, 10))
    try:
        from cognition.threads.store import get_active_threads
        threads = [{"topic": t.topic, "depth": t.depth, "salience": round(t.salience,2)} for t in get_active_threads()[:3]]
    except:
        threads = []
    return JSONResponse({"reflections": reflections, "active_threads": threads})


@router.get("/api/threads")
async def active_threads():
    """
    PHASE 4 UPGRADE: Thread observability.
    Return active cognitive threads (Sage's narrative mind).
    Read-only. Includes priority, depth, linkages for continuity insight.
    """
    threads = get_active_threads()
    # Return lightweight view (full index available via load_thread_index if needed)
    data = [
        {
            "thread_id": t.thread_id,
            "topic": t.topic,
            "status": t.status,
            "salience": round(t.salience, 3),
            "depth": t.depth,
            "priority": round(t.priority, 3),
            "last_touched": t.last_touched,
            "linked_reflections": len(t.linked_reflections),
            "linked_curiosities": len(t.linked_curiosities),
            "linked_searches": len(t.linked_searches),
            "summary": t.summary[:120] if t.summary else "",
        }
        for t in threads
    ]
    return JSONResponse({"active_threads": data, "total_threads": len(load_thread_index())})


# ── Search budget ─────────────────────────────────────────────────────

@router.get("/api/search/budget")
async def search_budget():
    """Return the current autonomous search budget state."""
    return JSONResponse(get_budget_status())
