"""
backend/orchestration/event_bus.py — Sage V2 Internal Event Bus

A lightweight async pub/sub mechanism that decouples subsystems.
Replaces V1's direct function call chains between launch.py, daemon,
and cognition modules.

Design principles:
  - No external dependencies (pure asyncio)
  - Fire-and-forget subscriptions — subscribers are async tasks
  - Events are typed string names with optional payload dicts
  - Dead subscribers don't crash the bus
  - Single bus instance per process (module-level singleton)

Event catalog (document new events here):
  "user_message_received"    payload: {user_input, session_id}
  "assistant_response_done"  payload: {response, session_id, digest}
  "daemon_triggered"         payload: {digest, session_turns}
  "daemon_cycle_complete"    payload: {steps_completed}
  "search_completed"         payload: {query, reason, summary, initiator}
  "sage_curiosity_fired"     payload: {topic, reason}
  "reflection_written"       payload: {domain, stem}
  "memory_updated"           payload: {domain, memory_type, label}
"""

import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine

from utils.logger import log

# Type alias for a subscriber coroutine
Subscriber = Callable[[dict], Coroutine[Any, Any, None]]

# Module-level singleton bus
_subscriptions: dict[str, list[Subscriber]] = defaultdict(list)
_lock = asyncio.Lock()


async def subscribe(event: str, handler: Subscriber) -> None:
    """Register an async handler for a named event."""
    async with _lock:
        _subscriptions[event].append(handler)
    log("event_bus", "subscribed", event=event, handler=handler.__qualname__)


async def publish(event: str, payload: dict | None = None) -> None:
    """
    Publish an event to all registered subscribers.

    Each subscriber is launched as a fire-and-forget task.
    A failing subscriber is logged but does not prevent others from running.
    """
    payload = payload or {}

    async with _lock:
        handlers = list(_subscriptions.get(event, []))

    if not handlers:
        return

    log("event_bus", "published", event=event, subscriber_count=len(handlers))

    for handler in handlers:
        asyncio.create_task(
            _safe_call(handler, event, payload),
            name=f"event_bus.{event}.{handler.__name__}",
        )


async def _safe_call(handler: Subscriber, event: str, payload: dict) -> None:
    """Wrap a subscriber call in error protection."""
    try:
        await handler(payload)
    except Exception as e:
        log("event_bus", "subscriber_error",
            event=event,
            handler=handler.__qualname__,
            error=str(e))


def clear_subscriptions() -> None:
    """Remove all subscriptions. Useful for clean test teardown."""
    _subscriptions.clear()
