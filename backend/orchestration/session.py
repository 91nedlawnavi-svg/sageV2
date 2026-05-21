"""
backend/orchestration/session.py — Sage V2 Session State

Manages per-session conversational state. This was tangled into V1's
launch.py as module-level globals. In V2 it is a proper class so
multiple sessions can coexist (future-proofing) and the state is
inspectable / testable.

Responsibilities:
  - Track turn count
  - Maintain rolling recent digest for daemon triggers
  - Evaluate whether daemon should fire
  - Evaluate emotional signal from recent turns
"""

from config.settings import (
    DAEMON_EMOTION_TRIGGER,
    DAEMON_TURN_TRIGGER,
    EMOTIONAL_KEYWORDS,
)


class ConversationSession:
    """
    Holds state for one active conversation session.
    One instance lives for the lifetime of the server process.
    """

    def __init__(self, max_digest: int = 20):
        self._session_turns = 0
        self._recent_digest: list[str] = []
        self._max_digest = max_digest

    # ── Public interface ──────────────────────────────────────────────

    def record_turn(self, role: str, content: str) -> None:
        """Record a conversation turn and update session counters."""
        self._recent_digest.append(f"{role.upper()}: {content}")
        if len(self._recent_digest) > self._max_digest:
            self._recent_digest.pop(0)
        if role == "assistant":
            self._session_turns += 1

    def should_trigger_daemon(self) -> bool:
        """
        True if either turn-count or emotional-signal threshold is met.
        Mirrors V1 logic exactly — no behavior change.
        """
        if self._session_turns > 0 and self._session_turns % DAEMON_TURN_TRIGGER == 0:
            return True

        recent_text = " ".join(
            self._recent_digest[-DAEMON_EMOTION_TRIGGER * 2:]
        ).lower()
        if any(kw in recent_text for kw in EMOTIONAL_KEYWORDS):
            return True

        return False

    def get_digest(self) -> str:
        """Return the current rolling digest as a single formatted string."""
        return "\n".join(self._recent_digest)

    @property
    def session_turns(self) -> int:
        return self._session_turns

    def reset(self) -> None:
        """Reset session state (useful for testing)."""
        self._session_turns = 0
        self._recent_digest.clear()
