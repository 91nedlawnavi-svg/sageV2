"""
daemon/reflection_daemon.py — Sage V2 Background Reflection Daemon

An async background task that monitors the session and triggers the
dual-domain reflection cycle when conditions are met.

V1's daemon was a threading.Thread that polled globals in launch.py.
V2's daemon is a proper asyncio.Task — no threads, no shared mutable globals,
communicates with the rest of the system entirely through the event bus.

Daemon lifecycle:
  1. Daemon task is started at server boot by bootstrap.py
  2. It subscribes to "assistant_response_done" on the event bus
  3. On each subscription event it checks session state via the session object
  4. If trigger conditions are met (and cooldown has elapsed) it runs a cycle
  5. Results are published back as "daemon_cycle_complete"

The daemon does NOT own the httpx client — it receives one at construction.
This avoids the V1 pattern of creating new clients inside the daemon.

Cooldown is enforced here (not inside the pipeline) so the pipeline
stays pure and testable. The daemon is the gatekeeper.
"""

import asyncio
import time
from typing import Optional

import httpx

from backend.orchestration.event_bus import publish, subscribe
from backend.orchestration.session import ConversationSession
from cognition.reflection.pipeline import run_reflection_cycle
from config.settings import DAEMON_COOLDOWN_SECONDS
from utils.logger import log


class ReflectionDaemon:
    """
    Background daemon that drives dual-domain reflection.

    One instance per server process. Constructed in bootstrap.
    """

    def __init__(
        self,
        session: ConversationSession,
        client: httpx.AsyncClient,
    ):
        self._session           = session
        self._client            = client
        self._last_run_ts: float = 0.0
        self._running: bool      = False
        self._task: Optional[asyncio.Task] = None

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the daemon — subscribe to events and begin listening."""
        if self._running:
            return
        self._running = True
        await subscribe("assistant_response_done", self._on_response_done)
        log("daemon", "started")

    async def stop(self) -> None:
        """Signal the daemon to stop accepting new cycles."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        log("daemon", "stopped")

    # ── Event handler ─────────────────────────────────────────────────

    async def _on_response_done(self, payload: dict) -> None:
        """
        Called via event bus every time the assistant finishes a response.
        Evaluates whether a reflection cycle should run now.
        """
        if not self._running:
            return

        if not self._session.should_trigger_daemon():
            return

        if not self._cooldown_elapsed():
            log("daemon", "cooldown_active",
                elapsed=round(time.time() - self._last_run_ts),
                required=DAEMON_COOLDOWN_SECONDS)
            return

        # Launch as a detached task — the response handler must not block
        self._task = asyncio.create_task(
            self._run_cycle(payload),
            name="daemon.reflection_cycle",
        )

    # ── Cycle execution ───────────────────────────────────────────────

    async def _run_cycle(self, payload: dict) -> None:
        """
        Execute one full dual-domain reflection cycle.
        Updates last-run timestamp and publishes results.
        """
        self._last_run_ts = time.time()

        digest       = self._session.get_digest()
        idle_seconds = payload.get("idle_seconds", 0.0)

        log("daemon", "cycle_start",
            session_turns=self._session.session_turns,
            digest_len=len(digest))

        await publish("daemon_triggered", {
            "digest":        digest,
            "session_turns": self._session.session_turns,
        })

        try:
            result = await run_reflection_cycle(
                conversation_digest=digest,
                client=self._client,
                idle_seconds=idle_seconds,
            )

            await publish("daemon_cycle_complete", {
                "episode_written":   result.episode_written,
                "emotional_themes":  result.emotional_themes,
                "library_entries":   result.library_entries,
                "user_reflection":   result.user_reflection,
                "sage_reflection":   result.sage_reflection,
                "curiosities_found": result.curiosities_found,
                "search_ran":        result.search_ran,
                "search_topic":      result.search_topic,
                "duration_seconds":  result.duration_seconds,
            })

            log("daemon", "cycle_complete",
                duration=result.duration_seconds,
                search_ran=result.search_ran)

        except Exception as e:
            log("daemon", "cycle_error", error=str(e))

    # ── Helpers ───────────────────────────────────────────────────────

    def _cooldown_elapsed(self) -> bool:
        """True if enough time has passed since the last daemon run."""
        return (time.time() - self._last_run_ts) >= DAEMON_COOLDOWN_SECONDS

    @property
    def last_run_ts(self) -> float:
        return self._last_run_ts

    @property
    def is_running(self) -> bool:
        return self._running
