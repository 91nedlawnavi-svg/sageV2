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
"""

from cognition.reflection.pipeline import ReflectionResult
from memory.sage.state import (
    load_sage_state,
    save_sage_state,
    merge_curiosity_topics,
)
from memory.sage.reflections import load_recent_sage_reflections
from memory.sage.curiosity import load_pending_curiosities, _parse_curiosity_entry
from utils.logger import log


async def synthesize_state_from_cycle(result: ReflectionResult) -> bool:
    """
    Update sage_state.json from a completed daemon cycle.

    Args:
        result: The ReflectionResult from run_reflection_cycle()

    Returns True on successful save.

    State fields updated:
      recent_synthesis        — what happened this cycle (factual)
      active_curiosity_topics — merged dedup from pending curiosities
      current_focus           — extracted from search topic if ran
      worldview_tensions      — cleared if worldview was updated (resolved)
      emotional_orientation   — extracted from emotional themes

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

    # 2. emotional_orientation — derive from themes (brief, not dramatic)
    if result.emotional_themes:
        # Take up to 2 themes as orientation
        state["emotional_orientation"] = ", ".join(result.emotional_themes[:2])

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
    # We don't add tensions here (no LLM), but we can remove resolved ones
    # by dropping the topic that was just searched/integrated
    if result.worldview_updated and result.search_topic:
        tensions = state.get("worldview_tensions", [])
        topic_lower = result.search_topic.lower()
        state["worldview_tensions"] = [
            t for t in tensions
            if result.search_topic.lower() not in t.lower()
        ]

    ok = save_sage_state(state)
    log("state", "synthesis_complete",
        recent_synthesis=state.get("recent_synthesis", ""),
        curiosity_topics=len(state.get("active_curiosity_topics", [])),
        ok=ok)
    return ok
