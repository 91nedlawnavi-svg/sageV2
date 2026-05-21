"""
backend/orchestration/job_store.py — Async Job Store

Manages background streaming jobs. The frontend polls /api/poll/<jid>
for tokens while the inference runs in a background task.

This was buried inside V1's launch.py. Extracted here so it can be
tested, inspected, and replaced (e.g., with WebSocket push) independently.
"""

import asyncio
import uuid
from typing import Optional


class JobStore:
    """
    In-memory store for streaming inference jobs.

    Each job tracks:
      - accumulated token chunks
      - current status (thinking → streaming → done)
      - error state
    """

    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def create(self, jid: Optional[str] = None) -> str:
        """Create a new job. Returns the job ID."""
        jid = jid or str(uuid.uuid4())
        async with self._lock:
            self._jobs[jid] = {
                "chunks": [],
                "done": False,
                "error": None,
                "status": "thinking",
            }
        return jid

    async def append_chunk(self, jid: str, token: str) -> None:
        """Append a streamed token to the job buffer."""
        async with self._lock:
            if jid in self._jobs:
                self._jobs[jid]["chunks"].append(token)

    async def set_status(self, jid: str, status: str) -> None:
        """Update job status label."""
        async with self._lock:
            if jid in self._jobs:
                self._jobs[jid]["status"] = status

    async def finish(self, jid: str, error: Optional[str] = None) -> None:
        """Mark job complete, with optional error message."""
        async with self._lock:
            if jid in self._jobs:
                self._jobs[jid].update({
                    "done": True,
                    "error": error,
                    "status": "done",
                })

    # ── Polling ───────────────────────────────────────────────────────

    async def read(self, jid: str, frm: int = 0) -> dict:
        """
        Read job state from chunk offset frm.
        Returns dict with: found, text, new_count, total, done, error, status.
        """
        async with self._lock:
            j = self._jobs.get(jid)
            if not j:
                return {"found": False}
            chunks = j["chunks"][frm:]
            return {
                "found": True,
                "text": "".join(chunks),
                "new_count": len(chunks),
                "total": len(j["chunks"]),
                "done": j["done"],
                "error": j["error"],
                "status": j.get("status", "thinking"),
            }

    # ── Cleanup ───────────────────────────────────────────────────────

    async def purge_done(self, max_keep: int = 50) -> int:
        """
        Remove old completed jobs to prevent unbounded memory growth.
        Keeps the most recent max_keep completed jobs.
        Returns count removed.
        """
        async with self._lock:
            done_ids = [
                jid for jid, j in self._jobs.items() if j["done"]
            ]
            to_remove = done_ids[:-max_keep] if len(done_ids) > max_keep else []
            for jid in to_remove:
                del self._jobs[jid]
            return len(to_remove)
