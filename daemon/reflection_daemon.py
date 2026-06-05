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

from backend.monitoring.metrics import AdminMetrics
from backend.orchestration.event_bus import publish, subscribe
from backend.orchestration.session import ConversationSession
from cognition.reflection.pipeline import run_reflection_cycle
from cognition.salience.tracker import decay_all
from cognition.synthesis.state_synthesis import synthesize_state_from_cycle
from config.settings import DAEMON_COOLDOWN_SECONDS
from utils.logger import log


class ReflectionDaemon:
    """
    Background daemon that drives dual-domain reflection.

    One instance per server process. Constructed in bootstrap.

    Phase 3A additions:
      - _cycle_lock: asyncio.Lock prevents overlapping reflection cycles.
        If a cycle is already running when a new trigger fires, the new
        trigger is silently skipped. No queue; no duplicate state writes.
      - synthesize_state_from_cycle() called after every successful cycle
        to persist the continuity snapshot to sage_state.json.
    """

    def __init__(
        self,
        session: ConversationSession,
        client: httpx.AsyncClient,
        metrics: AdminMetrics | None = None,
    ):
        self._session            = session
        self._client             = client
        self._metrics            = metrics
        self._last_run_ts: float = 0.0
        self._running: bool      = False
        self._task: Optional[asyncio.Task] = None
        # Phase 3A: mutex — one cycle at a time
        self._cycle_lock = asyncio.Lock()

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

        Phase 3A: If the mutex is already locked (a cycle is running),
        silently skip — do NOT queue a second cycle.
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

        # Phase 3A: mutex guard — skip if a cycle is already in progress
        if self._cycle_lock.locked():
            log("daemon", "cycle_skipped_locked")
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

        Phase 3A: The cycle runs under _cycle_lock to prevent overlaps.
        synthesize_state_from_cycle() is called after a successful cycle
        to persist the continuity snapshot.

        Phase 3B: Salience decay is applied at the START of every cycle.
        The cycle_id (timestamp) prevents double-decay and is passed through
        the pipeline for boost tracking.
        """
        async with self._cycle_lock:
            self._last_run_ts = time.time()
            cycle_id = str(int(self._last_run_ts))

            # Phase 3B: decay all salience scores once per cycle
            try:
                decay_all(cycle_id)
            except Exception as de:
                log("daemon", "salience_decay_error", error=str(de))

            digest       = self._session.get_digest()
            idle_seconds = payload.get("idle_seconds", 0.0)

            log("daemon", "cycle_start",
                session_turns=self._session.session_turns,
                digest_len=len(digest),
                cycle_id=cycle_id)

            # PHASE 4 #4: Prompt transparency - cycle fingerprint
            try:
                from models.prompts.templates import get_prompt_fingerprint
                from config.directive import get_directive
                directive = get_directive()
                cycle_fp = get_prompt_fingerprint(directive, digest[:300], f"daemon-cycle:{cycle_id}")
                log("prompt", "daemon_cycle_fingerprint", cycle_id=cycle_id, fp=cycle_fp)
            except Exception as e:
                log("prompt", "daemon_fp_error", error=str(e))

            await publish("daemon_triggered", {
                "digest":        digest,
                "session_turns": self._session.session_turns,
            })

            try:
                result = await run_reflection_cycle(
                    conversation_digest=digest,
                    client=self._client,
                    idle_seconds=idle_seconds,
                    cycle_id=cycle_id,
                )

                # Phase 3A: persist continuity snapshot after successful cycle
                try:
                    await synthesize_state_from_cycle(result)
                except Exception as se:
                    log("daemon", "state_synthesis_error", error=str(se))

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

                # Admin metrics: record successful cycle
                if self._metrics:
                    self._metrics.record_daemon_cycle({
                        "duration": result.duration_seconds,
                        "search_ran": result.search_ran,
                        "episode_written": result.episode_written,
                        "themes": len(result.emotional_themes),
                        "sage_reflection": result.sage_reflection,
                        "curiosities": result.curiosities_found,
                        "error": False,
                    })
                    # PHASE 4 #6 and #7: Record thread snapshot for observability and lifecycle
                    try:
                        from cognition.threads.store import get_active_threads, load_thread_index
                        self._metrics.record_thread_snapshot(
                            len(get_active_threads()),
                            len(load_thread_index())
                        )
                    except Exception:
                        pass

            except Exception as e:
                log("daemon", "cycle_error", error=str(e))
                if self._metrics:
                    # Don't call record_error here — the logger hook handles it
                    self._metrics.record_daemon_cycle({
                        "duration": round(time.time() - self._last_run_ts, 1),
                        "search_ran": False,
                        "episode_written": False,
                        "themes": 0,
                        "sage_reflection": False,
                        "curiosities": 0,
                        "error": True,
                    })

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
