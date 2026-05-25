"""
search/autonomy/trigger.py — Autonomous Search Trigger Evaluation

Determines whether Sage should initiate an autonomous search based on
her internal state, recent conversations, and curiosity journal.

This module evaluates potential triggers — it does NOT execute searches.
Execution lives in the daemon.

Phase 3B changes:
  - Thread-aware triggering: curiosities linked to active threads get priority boost
  - Salience-aware triggering: higher-salience curiosities are prioritized
  - Anti-fixation: triggers for topics that already have deep threads are deprioritized
  - Refined question detection: extracts proper clause boundaries instead of raw substrings

Trigger signals:
  - pending curiosity (from curiosity journal, strongest signal)
  - thread-linked curiosity (pending curiosity that belongs to an active thread)
  - open questions in reflections
  - repeated topic mentions (user keeps returning to something)
  - long idle period

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


# Phase 3B: depth at which a thread is "deep enough" that more searching
# is deprioritized (gives time for integration before more input)
_DEEP_THREAD_THRESHOLD = 6


async def evaluate_triggers(
    recent_digest: str,
    sage_reflections: list[str],
    pending_curiosities: list[str],
    idle_seconds: float = 0.0,
) -> list[SearchTrigger]:
    """
    Evaluate all trigger signals and return a sorted list of SearchTriggers.

    Phase 3B: Now thread-aware and salience-aware. Curiosities that belong
    to active threads get a priority boost. Curiosities linked to deep threads
    (high depth) get deprioritized to prevent fixation.
    """
    triggers: list[SearchTrigger] = []

    # Phase 3B: load thread context for priority modulation
    try:
        from cognition.threads.store import get_active_threads, get_thread_by_topic
        active_threads = get_active_threads()
        thread_topics = {t.topic: t for t in active_threads}
    except Exception:
        active_threads = []
        thread_topics = {}

    # Phase 3B: load salience for curiosity priority weighting
    try:
        from cognition.salience.tracker import get_salience_batch
        curiosity_keys = []
        for text in pending_curiosities:
            topic, _, _ = _parse_curiosity_entry(text)
            if topic:
                from memory.storage.base import safe_stem
                curiosity_keys.append(f"sage/curiosity/{safe_stem(topic)}")
        salience_map = get_salience_batch(curiosity_keys) if curiosity_keys else {}
    except Exception:
        salience_map = {}

    # ── Signal 1: Pending curiosity entries ──────────────────────────
    for curiosity_text in pending_curiosities:
        topic, reason, query = _parse_curiosity_entry(curiosity_text)
        if not topic or not query:
            continue

        base_priority = 0.75

        # Phase 3B: thread-aware priority modulation
        matching_thread = _find_matching_thread(topic, thread_topics)
        if matching_thread:
            if matching_thread.depth >= _DEEP_THREAD_THRESHOLD:
                # Deep thread — deprioritize to prevent fixation
                base_priority *= 0.5
            else:
                # Active thread but not deep — boost (thread validates interest)
                base_priority = min(0.95, base_priority + 0.15)

        # Phase 3B: salience-aware priority
        from memory.storage.base import safe_stem
        sal_key = f"sage/curiosity/{safe_stem(topic)}"
        salience = salience_map.get(sal_key, 1.0)
        # Scale priority by salience (low-salience = old/fading curiosity)
        final_priority = base_priority * max(0.3, salience)

        triggers.append(SearchTrigger(
            topic=topic,
            query=query,
            reason=reason or f"Unresolved curiosity about: {topic}",
            signal="pending_curiosity" if not matching_thread else "thread_curiosity",
            priority=round(final_priority, 3),
        ))

    # ── Signal 2: Open questions in sage reflections ──────────────────
    question_trigger = _detect_open_questions(sage_reflections)
    if question_trigger:
        triggers.append(question_trigger)

    # ── Signal 3: Repeated topic mentions in conversation ─────────────
    repeat_trigger = _detect_repeated_topics(recent_digest)
    if repeat_trigger:
        triggers.append(repeat_trigger)

    # ── Signal 4: Long idle period ────────────────────────────────────
    if idle_seconds > 7200 and pending_curiosities:
        first_query = _extract_first_query(pending_curiosities[0])
        if first_query:
            triggers.append(SearchTrigger(
                topic="idle_reflection",
                query=first_query,
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
            top_topic=triggers[0].topic,
            top_priority=triggers[0].priority)

    return triggers


def _find_matching_thread(topic: str, thread_topics: dict) -> Optional[object]:
    """Find a thread whose topic matches the curiosity topic."""
    topic_norm = " ".join(topic.lower().strip().split())
    for thread_topic, thread in thread_topics.items():
        thread_norm = " ".join(thread_topic.lower().strip().split())
        if topic_norm in thread_norm or thread_norm in topic_norm:
            return thread
    return None


def _extract_first_query(text: str) -> str:
    """Extract just the query from a curiosity entry text."""
    _, _, query = _parse_curiosity_entry(text)
    return query or ""


def _detect_open_questions(reflections: list[str]) -> Optional[SearchTrigger]:
    """
    Look for question markers or uncertainty language in Sage's reflections.

    Phase 3B: Improved extraction — finds the clause containing the marker
    rather than taking a raw character slice.
    """
    question_markers = [
        "i wonder", "i'm not sure", "i don't know", "what is",
        "why does", "why do", "how does", "what happened",
        "unclear", "uncertain", "curious about", "want to understand",
    ]
    combined = " ".join(reflections).lower()

    for marker in question_markers:
        if marker in combined:
            idx = combined.find(marker)
            # Extract the clause: from marker to next sentence boundary
            clause = _extract_clause(combined, idx)
            if len(clause) < 8:
                continue
            return SearchTrigger(
                topic="open_question",
                query=clause[:80],
                reason=f"An open question emerged from recent reflection: \"{clause[:60]}\"",
                signal="reflection_question",
                priority=0.55,
            )
    return None


def _extract_clause(text: str, start_idx: int) -> str:
    """Extract a meaningful clause from start_idx to next sentence boundary."""
    # Find end of clause (period, question mark, newline, or 100 chars)
    end_idx = start_idx
    max_end = min(len(text), start_idx + 100)
    for i in range(start_idx, max_end):
        if text[i] in ".?\n":
            end_idx = i
            break
    else:
        end_idx = max_end

    clause = text[start_idx:end_idx].strip()
    # Clean up
    clause = clause.strip(".,;:- ")
    return clause


def _detect_repeated_topics(digest: str) -> Optional[SearchTrigger]:
    """
    Detect if a topic has appeared multiple times in the recent digest.

    Phase 3B: Slightly raised threshold (4 instead of 3) to reduce noise.
    """
    if not digest:
        return None

    stopwords = {
        "the", "a", "an", "is", "it", "i", "you", "we", "he", "she",
        "they", "that", "this", "and", "or", "but", "in", "on", "at",
        "to", "of", "for", "with", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "did", "will", "would", "could",
        "should", "may", "might", "user", "assistant", "sage",
        "aku", "kamu", "dia", "itu", "ini", "dan", "atau", "tapi",
        "yang", "di", "ke", "dari", "dengan", "ada", "tidak",
        "about", "think", "really", "still", "thing", "things",
        "something", "someone", "every", "their", "there", "going",
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

    # Phase 3B: raised threshold to 4 (reduces noise triggers)
    repeated = [(w, c) for w, c in word_counts.items() if c >= 4]
    if not repeated:
        return None

    top_word, count = max(repeated, key=lambda x: x[1])

    return SearchTrigger(
        topic=top_word,
        query=top_word,
        reason=f"The topic \"{top_word}\" has appeared {count} times in recent conversation.",
        signal="repeated_mention",
        priority=0.45,
    )
