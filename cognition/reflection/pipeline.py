"""
cognition/reflection/pipeline.py — Dual-Domain Reflection Pipeline

Orchestrates one complete daemon reflection cycle.
This is the Phase 1 replacement for V1's cognition/reflection.py.

V1 had a single flat reflection function that mixed user and sage
cognition in one blob. V2 runs them as explicit ordered phases:

  Phase A — User Domain (Elliot's memory, same as V1):
    A1. Extract episodic memory from digest
    A2. Extract and merge emotional themes
    A3. Extract and populate library entries
    A4. Generate user-domain reflection

  Phase B — Sage Domain (NEW in V2):
    B1. Generate Sage's internal reflection
    B2. Identify new curiosities
    B3. Autonomous search (if budget allows and triggers fire)
    B4. Integrate search results into worldview (if search ran)

  Phase C — Event bus notifications:
    C1. Publish reflection_written events for any downstream consumers

Phase A and B are always run sequentially — A before B.
This ensures Sage reflects on what has already been distilled about Elliot,
not on the raw digest, reducing noise in her own cognition.

Returns a ReflectionResult dataclass summarizing what ran.
"""

import asyncio
import time
from dataclasses import dataclass, field

import httpx

from backend.orchestration.event_bus import publish
from cognition.emotional.user_emotional import extract_and_persist_user_emotions
from cognition.salience.tracker import register_artifact, boost_reference
from cognition.user_model.synthesis import extract_user_episode, generate_user_reflection
from cognition.user_model.library_extraction import extract_and_populate_user_library
from cognition.sage_model.synthesis import (
    generate_sage_reflection,
    identify_sage_curiosities,
    integrate_search_into_worldview,
)
from memory.sage.curiosity import load_pending_curiosities, update_curiosity_status, _parse_curiosity_entry
from memory.sage.reflections import load_recent_sage_reflections
from search.autonomy.budget import can_autonomous_search, record_autonomous_search, get_budget_status
from search.autonomy.trigger import evaluate_triggers
from search.pipeline import run_search
from utils.logger import log
from models.prompts.templates import get_prompt_fingerprint
from config.directive import get_directive


@dataclass
class ReflectionResult:
    """Summarises what ran in one daemon cycle."""
    # Phase A
    episode_written:       bool = False
    emotional_themes:      list[str] = field(default_factory=list)
    library_entries:       list[str] = field(default_factory=list)
    user_reflection:       bool = False
    # Phase B
    sage_reflection:       bool = False
    curiosities_found:     list[str] = field(default_factory=list)
    search_ran:            bool = False
    search_topic:          str = ""
    worldview_updated:     bool = False
    # Timing
    duration_seconds:      float = 0.0


async def run_reflection_cycle(
    conversation_digest: str,
    client: httpx.AsyncClient,
    idle_seconds: float = 0.0,
    cycle_id: str = "",
) -> ReflectionResult:
    """
    Execute one complete dual-domain reflection cycle.

    conversation_digest: recent turns formatted as "ROLE: content" lines
    client:              shared httpx.AsyncClient
    idle_seconds:        seconds since last user message (for idle triggers)
    cycle_id:            unique cycle identifier for salience boost tracking (Phase 3B)
    """
    t0     = time.time()
    result = ReflectionResult()
    if not cycle_id:
        cycle_id = str(int(t0))

    log("cognition", "reflection_cycle_start",
        digest_len=len(conversation_digest),
        idle_seconds=round(idle_seconds))

    # ══ PHASE A — User Domain ════════════════════════════════════════

    # A1. Episodic extraction
    try:
        result.episode_written = await extract_user_episode(conversation_digest, client)
    except Exception as e:
        log("cognition", "a1_error", error=str(e))

    # A2. Emotional themes
    try:
        result.emotional_themes = await extract_and_persist_user_emotions(
            conversation_digest, client
        )
    except Exception as e:
        log("cognition", "a2_error", error=str(e))

    # A3. Library entries
    try:
        result.library_entries = await extract_and_populate_user_library(
            conversation_digest, client
        )
    except Exception as e:
        log("cognition", "a3_error", error=str(e))

    # A4. User reflection
    try:
        result.user_reflection = await generate_user_reflection(client)
    except Exception as e:
        log("cognition", "a4_error", error=str(e))

    # Notify: user-domain reflection complete
    await publish("reflection_written", {
        "domain": "user",
        "episode": result.episode_written,
        "themes": result.emotional_themes,
    })

    # ══ PHASE B — Sage Domain ════════════════════════════════════════

    # Phase 3B: load thread context for sage reflection awareness
    from cognition.threads.store import (
        build_thread_context_for_reflection,
        advance_lifecycle,
    )
    from cognition.threads.assignment import (
        assign_reflection_to_thread,
        assign_curiosity_to_thread,
    )
    thread_context = build_thread_context_for_reflection()

    # B1. Sage's internal reflection (now thread-aware)
    user_context_summary = _summarise_phase_a(result)
    try:
        result.sage_reflection = await generate_sage_reflection(
            recent_user_context=user_context_summary,
            recent_interactions=conversation_digest[-1200:],
            client=client,
            thread_context=thread_context,
        )
    except Exception as e:
        log("cognition", "b1_error", error=str(e))

    # Phase 3B: assign the reflection to a cognitive thread
    if result.sage_reflection:
        try:
            from memory.sage.reflections import load_recent_sage_reflections as _load_recent
            recent = await _load_recent(n=1)
            if recent:
                ref_text = recent[0]
                # Build artifact key from most recent reflection file
                from memory.sage.reflections import load_all_sage_reflections as _load_all
                all_refs = await _load_all()
                if all_refs:
                    latest_path = all_refs[-1][0]
                    artifact_key = f"sage/reflection/{latest_path.stem}"
                    assigned_thread = await assign_reflection_to_thread(
                        ref_text, artifact_key, client
                    )
                    if assigned_thread:
                        boost_reference(artifact_key, cycle_id)
        except Exception as e:
            log("cognition", "b1_thread_assign_error", error=str(e))

    # B2. Identify new curiosities from combined material
    curiosity_material = conversation_digest + "\n\n" + user_context_summary
    try:
        result.curiosities_found = await identify_sage_curiosities(
            curiosity_material, client
        )
    except Exception as e:
        log("cognition", "b2_error", error=str(e))

    # Phase 3B: assign curiosities to threads
    for cur_topic in result.curiosities_found:
        try:
            from memory.sage.curiosity import load_all_curiosities as _load_curiosities
            all_cur = await _load_curiosities()
            if all_cur:
                # Find the curiosity that matches this topic
                for path, content in reversed(all_cur):
                    from memory.sage.curiosity import _parse_curiosity_entry as _pce_inline
                    t, _, _ = _pce_inline(content)
                    if t and t.strip().lower() == cur_topic.strip().lower():
                        artifact_key = f"sage/curiosity/{path.stem}"
                        await assign_curiosity_to_thread(cur_topic, artifact_key, client)
                        break
        except Exception as e:
            log("cognition", "b2_thread_assign_error", error=str(e))

    # B3. Autonomous search — evaluate triggers and budget
    try:
        search_outcome = await _maybe_run_autonomous_search(
            conversation_digest=conversation_digest,
            idle_seconds=idle_seconds,
            client=client,
        )
        if search_outcome:
            result.search_ran   = True
            result.search_topic = search_outcome.get("topic", "")

            # B4. Integrate into worldview
            topic   = search_outcome["topic"]
            summary = search_outcome["summary"]
            try:
                result.worldview_updated = await integrate_search_into_worldview(
                    topic=topic, search_summary=summary, client=client
                )
            except Exception as e:
                log("cognition", "b4_error", error=str(e))

            # Phase 3B: link search to its thread if one exists
            try:
                from cognition.threads.store import get_thread_by_topic, engage_thread
                matching_thread = get_thread_by_topic(topic)
                if matching_thread:
                    engage_thread(matching_thread.thread_id, f"search/{topic}", "search")
            except Exception as e:
                log("cognition", "b4_thread_link_error", error=str(e))

            await publish("search_completed", {
                "query":     search_outcome.get("query", ""),
                "reason":    search_outcome.get("reason", ""),
                "summary":   summary,
                "initiator": "Sage",
            })
    except Exception as e:
        log("cognition", "b3_error", error=str(e))

    # ══ PHASE C — Thread Lifecycle (Phase 3B) ════════════════════════

    try:
        lifecycle_result = advance_lifecycle()
    except Exception as e:
        log("cognition", "lifecycle_error", error=str(e))

    # Notify: sage-domain reflection complete
    await publish("reflection_written", {
        "domain":      "sage",
        "reflection":  result.sage_reflection,
        "curiosities": result.curiosities_found,
        "search_ran":  result.search_ran,
        "lifecycle": lifecycle_result,  # PHASE 4 #7 for structured context and cleanup visibility
    })

    result.duration_seconds = round(time.time() - t0, 2)

    log("cognition", "reflection_cycle_complete",
        duration=result.duration_seconds,
        episode=result.episode_written,
        themes=len(result.emotional_themes),
        library=len(result.library_entries),
        sage_reflection=result.sage_reflection,
        curiosities=len(result.curiosities_found),
        search_ran=result.search_ran)

    return result


async def _maybe_run_autonomous_search(
    conversation_digest: str,
    idle_seconds: float,
    client: httpx.AsyncClient,
) -> dict | None:
    """
    Evaluate autonomous search triggers and run a search if budget allows.
    Returns a dict with {topic, query, reason, summary} or None if skipped.
    """
    allowed, reason = can_autonomous_search()
    if not allowed:
        log("search", "autonomous_budget_blocked", reason=reason)
        return None

    # Load Sage's recent reflections and pending curiosities for trigger eval
    sage_reflections = await load_recent_sage_reflections(n=3)
    pending_raw      = await load_pending_curiosities()
    pending_texts    = [content for _, content in pending_raw]

    triggers = await evaluate_triggers(
        recent_digest=conversation_digest,
        sage_reflections=sage_reflections,
        pending_curiosities=pending_texts,
        idle_seconds=idle_seconds,
    )

    if not triggers:
        return None

    # Take the highest-priority trigger
    top = triggers[0]

    if not top.query:
        return None

    log("search", "autonomous_trigger_selected",
        topic=top.topic, signal=top.signal, priority=top.priority)

    # PHASE 4 #1: Include budget status in autonomous search reason for flawless provenance
    budget = get_budget_status()
    enhanced_reason = f"{top.reason} [autonomous, budget: {budget['count']}/{budget['max']}, cooldown: {budget.get('cooldown_active', False)}]"

    outcome = await run_search(
        query=top.query,
        reason=enhanced_reason,
        initiator="Sage",
        client=client,
        persist_to_sage_memory=True,
    )

    record_autonomous_search()

    # Update curiosity entry status if this was a pending curiosity trigger
    if top.signal == "pending_curiosity":
        for path, content in pending_raw:
            t, _, _ = _parse_curiosity_entry(content)
            if t == top.topic:
                await update_curiosity_status(path, "searched", query=top.query)
                break

    return {
        "topic":   top.topic,
        "query":   top.query,
        "reason":  top.reason,
        "summary": outcome.summary,
    }


def _summarise_phase_a(result: ReflectionResult) -> str:
    """
    Produce a brief text summary of Phase A outcomes for Sage's reflection context.
    Keeps it factual and short — Sage's reflection model uses this as input.
    """
    parts = []
    if result.episode_written:
        parts.append("An episodic memory was distilled from the conversation.")
    if result.emotional_themes:
        themes_str = ", ".join(result.emotional_themes)
        parts.append(f"Emotional themes updated: {themes_str}.")
    if result.library_entries:
        entries_str = ", ".join(result.library_entries)
        parts.append(f"Library entries written: {entries_str}.")
    if result.user_reflection:
        parts.append("A reflective synthesis was generated about recent patterns.")
    if not parts:
        parts.append("No significant user memory was distilled this cycle.")
    return " ".join(parts)
