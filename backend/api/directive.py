"""
backend/api/directive.py — Directive API Routes

Phase 2A: Identity Spine Restoration

Provides the two endpoints needed for live-editable directive persistence:

  GET  /api/directive       — return current directive content
  POST /api/directive       — save new directive content to disk

These are the ONLY routes allowed to touch directive.txt.
No other system (reflection, curiosity, worldview synthesis) may write
to the directive through these routes or any other path.

Kept intentionally thin — validation and file I/O live in config/directive.py.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config.directive import get_directive, save_directive
from utils.logger import log

router = APIRouter()


class DirectiveSaveRequest(BaseModel):
    content: str


@router.get("/api/directive")
async def read_directive():
    """
    Return the current directive.txt content for display in the frontend panel.
    """
    try:
        content = get_directive()
        return JSONResponse({"content": content})
    except RuntimeError as e:
        log("directive", "read_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/directive")
async def write_directive(req: DirectiveSaveRequest):
    """
    Persist new directive content to disk.

    The frontend directive editor POSTs here when the user saves.
    Content is validated and atomically written by config/directive.py.

    Returns {ok: true} on success.
    Raises 400 on empty content, 500 on write failure.
    """
    try:
        await save_directive(req.content)
        return JSONResponse({"ok": True})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log("directive", "save_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to save directive.")
