"""
search/autonomy/trigger.py — Autonomous Search Trigger Evaluation

Determines whether Sage should initiate an autonomous search based on
her internal state, recent conversations, and curiosity journal.

This module evaluates potential triggers — it does NOT execute searches.
Execution lives in the daemon.

Trigger signals (from spec):
  - recurring curiosity (same topic appearing in multiple recent entries)
  - emotional uncertainty (confusion, unresolved tension in sage reflections)
  - unresolved reflections (pending curiosity journal entries)
  - contradictory memories (detected topic conflict — Phase 2)
  - repeated mention patterns (user keeps returning to a topic)
  - internal philosophical questioning (open questions in sage reflections)
  - long idle periods (no conversation but memory indicates lingering interest)
  - evolving interests (sage worldview entries with open questions noted)

Triggers should NOT feel robotic. Each one has a reason string that
feeds into Sage's search context so she understands why she's looking.
"""

import time
from dataclasses import dataclass
from typing import Optional

from memory.sage.curiosity import _parse_curiosity_entry
from utils.logger import log


@dataclass
class SearchTrigger:
    """A recognized trigger for an autonomous search."""
    topic:     str    # what to search
    query:     str    # suggested search query
    reason:    str    # human-readable reason (used in search context injection)
    signal:    str    # machine-readable trigger type
    priority:  float  # 0.0–1.0, higher = more urgent


async def evaluate_triggers(
    recent_digest: str,
    sage_reflections: list[str],
    pending_curiosities: list[str],
    idle_seconds: float = 0.0,
) -> list[SearchTrigger]:
    """
    Evaluate all trigger signals and return a sorted list of SearchTriggers.

    Called by the daemon's autonomous curiosity cycle.
    Returns empty list if no triggers fire.

    recent_digest:       recent conversation turns as formatted text
    sage_reflections:    Sage's most recent internal reflections
    pending_curiosities: topics from curiosity journal with status=pending
    idle_seconds:        how long since last conversation turn
    """
    triggers: list[SearchTrigger] = []

    # ── Signal 1: Pending curiosity entries ──────────────────────────
    # Most direct trigger — Sage already identified something she wants to know.
    for curiosity_text in pending_curiosities:
        topic, reason, query = _parse_curiosity_entry(curiosity_text)
        if topic and query:
            triggers.append(SearchTrigger(
                topic=topic,
                query=query,
                reason=reason or f"Unresolved curiosity about: {topic}",
                signal="pending_curiosity",
                priority=0.85,
            ))

    # ── Signal 2: Open questions in sage reflections ──────────────────
    # Sage's recent reflections contain explicit questions or uncertainty markers.
    question_trigger = _detect_open_questions(sage_reflections)
    if question_trigger:
        triggers.append(question_trigger)

    # ── Signal 3: Repeated topic mentions in conversation ─────────────
    # The user keeps bringing up a topic — Sage becomes curious about it.
    repeat_trigger = _detect_repeated_topics(recent_digest)
    if repeat_trigger:
        triggers.append(repeat_trigger)

    # ── Signal 4: Long idle period ────────────────────────────────────
    # Sage has been quiet for a while. Old curiosities can resurface.
    if idle_seconds > 7200 and pending_curiosities:  # 2+ hours idle
        triggers.append(SearchTrigger(
            topic="idle_reflection",
            query=_extract_first_query(pending_curiosities[0]),
            reason="Long quiet period — revisiting lingering curiosity.",
            signal="idle_curiosity",
            priority=0.4,
        ))

    # Sort by priority descending
    triggers.sort(key=lambda t: t.priority, reverse=True)

    if triggers:
        log("search", "triggers_evaluated",
            count=len(triggers),
            top_signal=triggers[0].signal,
            top_topic=triggers[0].topic)

    return triggers


def _extract_first_query(text: str) -> str:
    """Extract just the query from a curiosity entry text."""
    _, _, query = _parse_curiosity_entry(text)
    return query or ""


def _detect_open_questions(reflections: list[str]) -> Optional[SearchTrigger]:
    """
    Look for question markers or uncertainty language in Sage's reflections.
    Returns a trigger if found, None otherwise.
    """
    question_markers = [
        "i wonder", "i'm not sure", "i don't know", "what is",
        "why does", "why do", "how does", "what happened",
        "unclear", "uncertain", "curious about", "want to understand",
    ]
    combined = " ".join(reflections).lower()

    for marker in question_markers:
        if marker in combined:
            # Extract a short topic context near the marker
            idx = combined.find(marker)
            snippet = combined[idx:idx + 80].strip()
            return SearchTrigger(
                topic="open_question",
                query=snippet[:60],
                reason=f"An open question emerged from recent reflection: \"{snippet[:60]}...\"",
                signal="reflection_question",
                priority=0.6,
            )
    return None


def _detect_repeated_topics(digest: str) -> Optional[SearchTrigger]:
    """
    Detect if a topic has appeared multiple times in the recent digest.
    Returns a trigger for the most-repeated meaningful term, or None.
    """
    if not digest:
        return None

    # Simple word-frequency approach for repeated substantive topics.
    # Exclude common stopwords and conversational filler.
    stopwords = {
        "the", "a", "an", "is", "it", "i", "you", "we", "he", "she",
        "they", "that", "this", "and", "or", "but", "in", "on", "at",
        "to", "of", "for", "with", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "did", "will", "would", "could",
        "should", "may", "might", "user", "assistant", "sage",
        "aku", "kamu", "dia", "itu", "ini", "dan", "atau", "tapi",
        "yang", "di", "ke", "dari", "dengan", "ada", "tidak",
    }

    words = [
        w.strip(".,?!\"'():;")
        for w in digest.lower().split()
        if len(w) > 4
    ]
    word_counts: dict[str, int] = {}
    for w in words:
        if w not in stopwords:
            word_counts[w] = word_counts.get(w, 0) + 1

    # A topic worth searching appears 3+ times in recent digest
    repeated = [(w, c) for w, c in word_counts.items() if c >= 3]
    if not repeated:
        return None

    top_word, count = max(repeated, key=lambda x: x[1])

    return SearchTrigger(
        topic=top_word,
        query=top_word,
        reason=f"The topic \"{top_word}\" has appeared {count} times in recent conversation.",
        signal="repeated_mention",
        priority=0.5,
    )
