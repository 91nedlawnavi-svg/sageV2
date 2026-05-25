"""
cognition/synthesis/state_synthesis.py — State Synthesis

Called at the END of every successful daemon reflection cycle.

Takes the ReflectionResult and synthesizes it into an updated
sage_state.json. This is NOT a reflection — it is a compression
step that stabilizes and orients the next cycle.

Design constraints:
  - Must NOT recursively absorb the previous state into itself.
    The state is recomputed from cycle outputs, NOT from old state + outputs.
    This prevents state → reflection → state amplification loops.
  - Fields are overwritten, not appended. Continuity comes from stability,
    not accumulation.
  - If the cycle produced nothing, the state is only minimally updated
    (last_updated timestamp and any curiosity merges).
  - No LLM calls here — this is purely deterministic extraction.

Phase 3B additions:
  - active_threads field populated from thread store (replaces ad-hoc curiosity list)
  - meta_warnings field populated from observer (read-only sensor output)
  - emotional_orientation uses rolling window instead of last-write-wins
  - orientation_history tracked for oscillation detection
"""

from cognition.meta.observer import observe as meta_observe
from cognition.reflection.pipeline import ReflectionResult
from cognition.threads.store import build_thread_summary_for_state
from memory.sage.state import (
    load_sage_state,
    save_sage_state,
    merge_curiosity_topics,
)
from memory.sage.reflections import load_recent_sage_reflections
from memory.sage.curiosity import load_pending_curiosities, _parse_curiosity_entry
from utils.logger import log

# Phase 3B: rolling window size for emotional orientation smoothing
_ORIENTATION_WINDOW = 4


async def synthesize_state_from_cycle(result: ReflectionResult) -> bool:
    """
    Update sage_state.json from a completed daemon cycle.

    Args:
        result: The ReflectionResult from run_reflection_cycle()

    Returns True on successful save.

    Phase 3B state model:
      recent_synthesis        — what happened this cycle (factual)
      active_threads          — from thread store (deterministic, not accumulated)
      active_curiosity_topics — merged dedup from pending curiosities
      current_focus           — extracted from search topic if ran
      emotional_orientation   — smoothed from rolling window
      orientation_history     — last N orientations for oscillation detection
      meta_warnings           — deterministic flags from observer
      worldview_tensions      — cleared if worldview was updated

    Fields NOT touched here (they persist across cycles):
      self_summary            — updated only explicitly via directive ops
      active_questions        — user or external update
    """
    state = load_sage_state()

    # 1. recent_synthesis — terse summary of this cycle
    parts = []
    if result.episode_written:
        parts.append("episodic memory distilled")
    if result.emotional_themes:
        parts.append(f"emotional themes: {', '.join(result.emotional_themes[:2])}")
    if result.sage_reflection:
        parts.append("internal reflection written")
    if result.search_ran and result.search_topic:
        parts.append(f"searched: {result.search_topic}")
    if result.worldview_updated:
        parts.append("worldview updated")

    if parts:
        state["recent_synthesis"] = "; ".join(parts)

    # 2. emotional_orientation — Phase 3B: rolling window smoothing
    #    Instead of overwriting with latest themes, maintain a history
    #    and compute orientation from the most frequent recent themes.
    if result.emotional_themes:
        orientation_history = state.get("orientation_history", [])
        current_themes = ", ".join(result.emotional_themes[:2])
        orientation_history.append(current_themes)
        orientation_history = orientation_history[-_ORIENTATION_WINDOW:]
        state["orientation_history"] = orientation_history

        # Compute smoothed orientation: most common theme words across window
        state["emotional_orientation"] = _smooth_orientation(orientation_history)

    # 3. current_focus — update if a search ran (it was a focus topic)
    if result.search_ran and result.search_topic:
        focus = state.get("current_focus", [])
        topic = result.search_topic
        if topic not in focus:
            focus = ([topic] + focus)[:3]
        state["current_focus"] = focus

    # 4. active_curiosity_topics — merge from pending curiosities
    try:
        pending = await load_pending_curiosities()
        new_topics = []
        for _, content in pending:
            topic, _, _ = _parse_curiosity_entry(content)
            if topic:
                new_topics.append(topic)
        if new_topics or result.curiosities_found:
            combined_new = result.curiosities_found + new_topics
            state["active_curiosity_topics"] = merge_curiosity_topics(
                state.get("active_curiosity_topics", []),
                combined_new,
                max_topics=5,
            )
    except Exception as e:
        log("state", "curiosity_merge_error", error=str(e))

    # 5. worldview_tensions — if worldview was updated, tension may be resolved
    if result.worldview_updated and result.search_topic:
        tensions = state.get("worldview_tensions", [])
        state["worldview_tensions"] = [
            t for t in tensions
            if result.search_topic.lower() not in t.lower()
        ]

    # 6. Phase 3B: active_threads — sourced directly from thread store
    #    NOT accumulated from previous state — avoids recursive self-reference
    try:
        state["active_threads"] = build_thread_summary_for_state()
    except Exception as e:
        log("state", "thread_summary_error", error=str(e))

    # 7. Phase 3B: meta-observation — run deterministic sensor
    try:
        prev_orientations = state.get("orientation_history", [])
        meta_result = meta_observe(prev_orientations=prev_orientations)
        if meta_result.has_warnings:
            state["meta_warnings"] = meta_result.as_state_flags()
        else:
            state["meta_warnings"] = []
    except Exception as e:
        log("state", "meta_observe_error", error=str(e))

    ok = save_sage_state(state)
    log("state", "synthesis_complete",
        recent_synthesis=state.get("recent_synthesis", ""),
        curiosity_topics=len(state.get("active_curiosity_topics", [])),
        threads=len(state.get("active_threads", [])),
        warnings=len(state.get("meta_warnings", [])),
        ok=ok)
    return ok


def _smooth_orientation(history: list[str]) -> str:
    """
    Compute smoothed emotional orientation from a rolling window.

    Instead of last-write-wins, count theme word frequency across
    the window and return the most stable/frequent terms.

    This prevents single-cycle emotional events from flipping
    the entire orientation — stability requires persistence.
    """
    if not history:
        return ""

    # Count word frequency across all entries in the window
    word_counts: dict[str, int] = {}
    for entry in history:
        words = [w.strip().lower() for w in entry.replace(",", " ").split() if len(w) > 2]
        for w in words:
            word_counts[w] = word_counts.get(w, 0) + 1

    if not word_counts:
        return history[-1] if history else ""

    # Return the top themes that appeared in at least half the window
    min_count = max(1, len(history) // 2)
    stable_words = [w for w, c in word_counts.items() if c >= min_count]

    if stable_words:
        # Sort by frequency descending, take top 3
        stable_words.sort(key=lambda w: word_counts[w], reverse=True)
        return ", ".join(stable_words[:3])

    # Fallback: most recent entry
    return history[-1]
