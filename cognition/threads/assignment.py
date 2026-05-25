"""
cognition/threads/assignment.py — Thread Assignment (Deterministic)

After a sage reflection is generated, this module determines which
cognitive thread (if any) the reflection belongs to.

Assignment is done by embedding similarity between the reflection text
and each active thread's topic. This is NOT an LLM call — it reuses the
existing embedding infrastructure.

Rules:
  - If similarity to an existing thread > ASSIGNMENT_THRESHOLD, assign to it
  - If no thread matches and active count < MAX_ACTIVE_THREADS, create a new one
  - If no thread matches and cap is reached, the reflection remains unthreaded
  - A reflection can only belong to ONE thread (no multi-assignment)
  - Thread engagement is recorded on assignment

This module also handles curiosity-to-thread assignment (same logic,
different input text).
"""

from typing import Optional

import httpx

from cognition.threads.store import (
    CognitiveThread,
    create_thread,
    engage_thread,
    get_active_threads,
    get_thread_by_topic,
)
from memory.embeddings.cache import get_embedding, cosine_similarity
from utils.logger import log


# Minimum similarity between a reflection and a thread topic for assignment
ASSIGNMENT_THRESHOLD = 0.45


async def assign_reflection_to_thread(
    reflection_text: str,
    artifact_key: str,
    client: httpx.AsyncClient,
) -> Optional[str]:
    """
    Assign a sage reflection to the best-matching cognitive thread.

    Returns the thread_id if assigned, None if unthreaded.

    Process:
      1. Embed the reflection text
      2. Embed each active thread's topic
      3. Find the highest-similarity thread above threshold
      4. If found: engage that thread with this reflection
      5. If not found: attempt to create a new thread from the reflection

    Thread creation from reflection:
      - Extract a short topic label (first meaningful sentence fragment)
      - Only create if active cap not exceeded
    """
    active_threads = get_active_threads()

    # If no threads exist, always try to create one
    if not active_threads:
        topic = _extract_topic_from_text(reflection_text)
        if topic:
            thread = create_thread(topic, summary=reflection_text[:120])
            if thread:
                engage_thread(thread.thread_id, artifact_key, "reflection")
                return thread.thread_id
        return None

    # Embed the reflection
    ref_vec = await get_embedding(reflection_text[:400], client)
    if ref_vec is None:
        return None

    # Score against each active thread's topic
    best_thread: Optional[CognitiveThread] = None
    best_score = 0.0

    for thread in active_threads:
        topic_vec = await get_embedding(thread.topic, client)
        if topic_vec is None:
            continue
        score = cosine_similarity(ref_vec, topic_vec)
        if score > best_score:
            best_score = score
            best_thread = thread

    # Assign if above threshold
    if best_thread and best_score >= ASSIGNMENT_THRESHOLD:
        engage_thread(best_thread.thread_id, artifact_key, "reflection")
        log("threads", "reflection_assigned",
            thread_id=best_thread.thread_id,
            topic=best_thread.topic,
            score=round(best_score, 3))
        return best_thread.thread_id

    # No match — attempt to create a new thread
    topic = _extract_topic_from_text(reflection_text)
    if topic:
        thread = create_thread(topic, summary=reflection_text[:120])
        if thread:
            engage_thread(thread.thread_id, artifact_key, "reflection")
            log("threads", "thread_created_from_reflection",
                thread_id=thread.thread_id, topic=topic)
            return thread.thread_id

    log("threads", "reflection_unthreaded",
        reason="no_match_and_cap_or_no_topic",
        best_score=round(best_score, 3))
    return None


async def assign_curiosity_to_thread(
    curiosity_topic: str,
    artifact_key: str,
    client: httpx.AsyncClient,
) -> Optional[str]:
    """
    Assign a curiosity entry to a matching thread or create a new one.

    Curiosities are strong thread-creation signals — they represent
    explicit interest that Sage identified. If no matching thread exists
    and the cap allows, a new thread is created.
    """
    # First check by normalized topic match (fast, no embedding needed)
    existing = get_thread_by_topic(curiosity_topic)
    if existing:
        engage_thread(existing.thread_id, artifact_key, "curiosity")
        log("threads", "curiosity_assigned_by_topic",
            thread_id=existing.thread_id, topic=existing.topic)
        return existing.thread_id

    # Fall back to embedding similarity
    active_threads = get_active_threads()
    if active_threads:
        cur_vec = await get_embedding(curiosity_topic, client)
        if cur_vec:
            best_thread = None
            best_score = 0.0
            for thread in active_threads:
                topic_vec = await get_embedding(thread.topic, client)
                if topic_vec is None:
                    continue
                score = cosine_similarity(cur_vec, topic_vec)
                if score > best_score:
                    best_score = score
                    best_thread = thread

            if best_thread and best_score >= ASSIGNMENT_THRESHOLD:
                engage_thread(best_thread.thread_id, artifact_key, "curiosity")
                return best_thread.thread_id

    # No match — create thread (curiosities are strong creation signals)
    thread = create_thread(curiosity_topic, summary=f"Curiosity: {curiosity_topic}")
    if thread:
        engage_thread(thread.thread_id, artifact_key, "curiosity")
        return thread.thread_id

    return None


def _extract_topic_from_text(text: str) -> str:
    """
    Extract a short topic label from reflection text.

    Heuristic: take the first clause (up to first comma, period, or em-dash)
    that is at least 10 characters. Strip first-person starters.

    This is deliberately crude — topics are refined by thread engagement
    over time, not by this initial extraction.
    """
    text = text.strip()

    # Remove common first-person starters
    starters = [
        "i find myself ", "i notice ", "i'm ", "i am ",
        "something in me ", "there's something ", "there is ",
    ]
    lower = text.lower()
    for s in starters:
        if lower.startswith(s):
            text = text[len(s):]
            break

    # Take first clause
    for sep in [".", ",", "—", " - ", ";", "\n"]:
        idx = text.find(sep)
        if idx > 10:
            text = text[:idx]
            break

    # Cap length
    words = text.split()[:8]
    result = " ".join(words).strip(" .,;:-")

    if len(result) < 5:
        return ""

    return result
