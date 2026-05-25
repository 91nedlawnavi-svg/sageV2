"""
cognition/threads/store.py — Cognitive Thread Persistence

A cognitive thread represents a persistent line of thought that spans
multiple daemon cycles. It is the structural unit of longitudinal cognition.

Threads are NOT:
  - LLM-generated (their metadata is deterministically maintained)
  - Self-modifying (they cannot rewrite their own priorities)
  - Unbounded (hard cap on active count)
  - Autonomous (they are containers, not actors)

Threads ARE:
  - Persistent named containers for related cognitive artifacts
  - Lifecycle-managed (nascent → active → dormant → resolved)
  - Salience-bearing (threads carry their own salience score)
  - Depth-tracked (how many cycles have engaged with them)
  - Linkage-tracked (which reflections, curiosities, searches belong to them)

Filesystem layout:
  ~/sage_data_v2/sage_memory/threads/
  ├── thread_index.json          ← all thread metadata (single source of truth)
  └── entries/
      ├── thread_001_entries.jsonl  ← linked artifact references for thread 001
      ├── thread_002_entries.jsonl
      └── ...

Design constraints:
  - Thread creation is GATED by MAX_ACTIVE_THREADS
  - Thread metadata is JSON — no LLM in the storage path
  - Thread priority is computed deterministically from salience + depth + recency
  - Thread index is the ONLY file that determines thread existence
  - Entry logs are append-only (audit trail of what was linked)
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import (
    SAGE_MEMORY_ROOT,
    MAX_ACTIVE_THREADS,
    MAX_TOTAL_THREADS,
    THREAD_DORMANCY_CYCLES,
    THREAD_RESOLVE_SALIENCE,
)
from cognition.salience.tracker import (
    SALIENCE_DEFAULT,
    SALIENCE_FLOOR,
    DECAY_RATE,
    _clamp,
)
from utils.logger import log


# ── Paths ────────────────────────────────────────────────────────────

THREADS_DIR = SAGE_MEMORY_ROOT / "threads"
THREAD_INDEX_FILE = THREADS_DIR / "thread_index.json"
THREAD_ENTRIES_DIR = THREADS_DIR / "entries"


# ── Thread lifecycle states ──────────────────────────────────────────

LIFECYCLE_NASCENT  = "nascent"    # just created, not yet confirmed by second engagement
LIFECYCLE_ACTIVE   = "active"    # receiving regular engagement
LIFECYCLE_DORMANT  = "dormant"   # no engagement for THREAD_DORMANCY_CYCLES
LIFECYCLE_RESOLVED = "resolved"  # explicitly or implicitly concluded

ACTIVE_STATES = {LIFECYCLE_NASCENT, LIFECYCLE_ACTIVE}
ALL_STATES    = {LIFECYCLE_NASCENT, LIFECYCLE_ACTIVE, LIFECYCLE_DORMANT, LIFECYCLE_RESOLVED}


# ── Data model ───────────────────────────────────────────────────────

@dataclass
class CognitiveThread:
    """In-memory representation of a cognitive thread."""
    thread_id: str
    topic: str
    status: str                      # lifecycle state
    salience: float                  # current salience score
    depth: int                       # how many cycles have engaged
    created: str                     # ISO timestamp
    last_touched: str                # ISO timestamp of last engagement
    cycles_since_touch: int          # incremented each cycle, reset on engagement
    linked_reflections: list[str] = field(default_factory=list)
    linked_curiosities: list[str] = field(default_factory=list)
    linked_searches: list[str] = field(default_factory=list)
    summary: str = ""                # brief description (set at creation, may be updated)

    def to_dict(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "topic": self.topic,
            "status": self.status,
            "salience": self.salience,
            "depth": self.depth,
            "created": self.created,
            "last_touched": self.last_touched,
            "cycles_since_touch": self.cycles_since_touch,
            "linked_reflections": self.linked_reflections,
            "linked_curiosities": self.linked_curiosities,
            "linked_searches": self.linked_searches,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CognitiveThread":
        return cls(
            thread_id=d["thread_id"],
            topic=d["topic"],
            status=d.get("status", LIFECYCLE_NASCENT),
            salience=d.get("salience", SALIENCE_DEFAULT),
            depth=d.get("depth", 0),
            created=d.get("created", ""),
            last_touched=d.get("last_touched", ""),
            cycles_since_touch=d.get("cycles_since_touch", 0),
            linked_reflections=d.get("linked_reflections", []),
            linked_curiosities=d.get("linked_curiosities", []),
            linked_searches=d.get("linked_searches", []),
            summary=d.get("summary", ""),
        )

    @property
    def priority(self) -> float:
        """
        Deterministic priority score for ordering.
        Higher = more cognitively important right now.

        Formula: salience * (1 + log_depth_bonus) * recency_factor

        - salience: the raw decay-aware weight
        - log_depth_bonus: deeper threads get slight persistence bonus (capped)
        - recency_factor: recently-touched threads get recency boost
        """
        import math
        depth_bonus = min(0.3, 0.1 * math.log1p(self.depth))
        recency = max(0.5, 1.0 - (self.cycles_since_touch * 0.08))
        return self.salience * (1.0 + depth_bonus) * recency


# ── Index persistence ────────────────────────────────────────────────

def _ensure_dirs() -> None:
    THREADS_DIR.mkdir(parents=True, exist_ok=True)
    THREAD_ENTRIES_DIR.mkdir(parents=True, exist_ok=True)


def load_thread_index() -> list[CognitiveThread]:
    """Load all threads from the index file."""
    if not THREAD_INDEX_FILE.exists():
        return []
    try:
        raw = THREAD_INDEX_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        return [CognitiveThread.from_dict(d) for d in data]
    except Exception as e:
        log("threads", "index_load_error", error=str(e))
        return []


def save_thread_index(threads: list[CognitiveThread]) -> bool:
    """Atomically persist the thread index."""
    _ensure_dirs()
    try:
        payload = json.dumps(
            [t.to_dict() for t in threads],
            indent=2,
            ensure_ascii=False,
        )
        tmp = THREAD_INDEX_FILE.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(THREAD_INDEX_FILE)
        return True
    except Exception as e:
        log("threads", "index_save_error", error=str(e))
        return False


# ── Query helpers ────────────────────────────────────────────────────

def get_active_threads() -> list[CognitiveThread]:
    """Return threads in nascent or active state, sorted by priority."""
    threads = load_thread_index()
    active = [t for t in threads if t.status in ACTIVE_STATES]
    active.sort(key=lambda t: t.priority, reverse=True)
    return active


def get_thread_by_id(thread_id: str) -> Optional[CognitiveThread]:
    """Find a thread by ID. Returns None if not found."""
    threads = load_thread_index()
    for t in threads:
        if t.thread_id == thread_id:
            return t
    return None


def get_thread_by_topic(topic: str) -> Optional[CognitiveThread]:
    """Find a thread by topic similarity (normalized substring match)."""
    threads = load_thread_index()
    topic_norm = _normalize(topic)
    for t in threads:
        t_norm = _normalize(t.topic)
        if topic_norm in t_norm or t_norm in topic_norm:
            return t
    return None


def active_thread_count() -> int:
    """Count threads currently in active states."""
    threads = load_thread_index()
    return sum(1 for t in threads if t.status in ACTIVE_STATES)


# ── Thread creation ──────────────────────────────────────────────────

def create_thread(topic: str, summary: str = "") -> Optional[CognitiveThread]:
    """
    Create a new cognitive thread.

    Returns the thread if created, None if creation was blocked
    (cap exceeded or duplicate topic detected).

    Creation is GATED:
      1. If a thread with a matching topic already exists, return it instead
      2. If MAX_ACTIVE_THREADS is reached, creation is blocked
      3. If MAX_TOTAL_THREADS is reached, resolve the lowest-salience dormant thread
    """
    threads = load_thread_index()

    # Check for duplicate topic
    topic_norm = _normalize(topic)
    for t in threads:
        if _normalize(t.topic) == topic_norm or topic_norm in _normalize(t.topic):
            # Existing thread matches — reactivate if dormant
            if t.status == LIFECYCLE_DORMANT:
                t.status = LIFECYCLE_ACTIVE
                t.cycles_since_touch = 0
                t.last_touched = _now()
                save_thread_index(threads)
                log("threads", "reactivated", thread_id=t.thread_id, topic=t.topic)
            return t

    # Check active cap
    active_count = sum(1 for t in threads if t.status in ACTIVE_STATES)
    if active_count >= MAX_ACTIVE_THREADS:
        log("threads", "creation_blocked_cap",
            topic=topic, active_count=active_count, cap=MAX_ACTIVE_THREADS)
        return None

    # Check total cap — evict lowest-salience resolved thread if needed
    if len(threads) >= MAX_TOTAL_THREADS:
        resolved = [t for t in threads if t.status == LIFECYCLE_RESOLVED]
        if resolved:
            resolved.sort(key=lambda t: t.salience)
            victim = resolved[0]
            threads.remove(victim)
            log("threads", "evicted_for_space", thread_id=victim.thread_id, topic=victim.topic)
        else:
            # All slots occupied by non-resolved threads — hard block
            log("threads", "creation_blocked_total", topic=topic, total=len(threads))
            return None

    # Create the thread
    thread_id = f"thread_{int(time.time())}_{_safe_slug(topic)[:20]}"
    now = _now()
    thread = CognitiveThread(
        thread_id=thread_id,
        topic=topic,
        status=LIFECYCLE_NASCENT,
        salience=SALIENCE_DEFAULT,
        depth=0,
        created=now,
        last_touched=now,
        cycles_since_touch=0,
        summary=summary or topic,
    )

    threads.append(thread)
    save_thread_index(threads)
    log("threads", "created", thread_id=thread_id, topic=topic)
    return thread


# ── Thread engagement (called when a cycle touches a thread) ─────────

def engage_thread(thread_id: str, artifact_key: str, artifact_type: str) -> bool:
    """
    Record that a daemon cycle engaged with this thread.

    - Increments depth
    - Resets cycles_since_touch
    - Promotes nascent → active if depth >= 2
    - Links the artifact
    - Boosts salience

    artifact_type: "reflection" | "curiosity" | "search"

    Returns True if engagement was recorded.
    """
    threads = load_thread_index()
    thread = None
    for t in threads:
        if t.thread_id == thread_id:
            thread = t
            break

    if thread is None:
        return False

    if thread.status == LIFECYCLE_RESOLVED:
        return False

    thread.depth += 1
    thread.cycles_since_touch = 0
    thread.last_touched = _now()
    thread.salience = _clamp(thread.salience + 0.10)

    # Lifecycle promotion: nascent → active after second engagement
    if thread.status == LIFECYCLE_NASCENT and thread.depth >= 2:
        thread.status = LIFECYCLE_ACTIVE
        log("threads", "promoted_to_active", thread_id=thread_id)

    # Dormant reactivation
    if thread.status == LIFECYCLE_DORMANT:
        thread.status = LIFECYCLE_ACTIVE
        log("threads", "reactivated_by_engagement", thread_id=thread_id)

    # Link the artifact
    if artifact_type == "reflection" and artifact_key not in thread.linked_reflections:
        thread.linked_reflections.append(artifact_key)
        thread.linked_reflections = thread.linked_reflections[-20:]  # cap linkage list
    elif artifact_type == "curiosity" and artifact_key not in thread.linked_curiosities:
        thread.linked_curiosities.append(artifact_key)
        thread.linked_curiosities = thread.linked_curiosities[-10:]
    elif artifact_type == "search" and artifact_key not in thread.linked_searches:
        thread.linked_searches.append(artifact_key)
        thread.linked_searches = thread.linked_searches[-10:]

    save_thread_index(threads)
    log("threads", "engaged",
        thread_id=thread_id, depth=thread.depth,
        artifact_type=artifact_type, artifact_key=artifact_key)
    return True


# ── Lifecycle transitions (called by lifecycle manager each cycle) ───

def advance_lifecycle() -> dict:
    """
    Run deterministic lifecycle transitions on all threads.
    Called once per daemon cycle AFTER reflection pipeline completes.

    Transitions:
      - Active/Nascent → Dormant: if cycles_since_touch >= THREAD_DORMANCY_CYCLES
      - Dormant → Resolved: if salience <= THREAD_RESOLVE_SALIENCE
      - All: increment cycles_since_touch
      - All: decay salience

    Returns summary: {dormanted: int, resolved: int, decayed: int}
    """
    threads = load_thread_index()
    dormanted = 0
    resolved = 0
    decayed = 0

    for t in threads:
        if t.status in (LIFECYCLE_NASCENT, LIFECYCLE_ACTIVE):
            t.cycles_since_touch += 1
            t.salience = _clamp(t.salience * DECAY_RATE)
            decayed += 1

            if t.cycles_since_touch >= THREAD_DORMANCY_CYCLES:
                t.status = LIFECYCLE_DORMANT
                dormanted += 1
                log("threads", "dormanted",
                    thread_id=t.thread_id, topic=t.topic,
                    cycles=t.cycles_since_touch)

        elif t.status == LIFECYCLE_DORMANT:
            t.salience = _clamp(t.salience * DECAY_RATE)
            decayed += 1

            if t.salience <= THREAD_RESOLVE_SALIENCE:
                t.status = LIFECYCLE_RESOLVED
                resolved += 1
                log("threads", "resolved_by_salience",
                    thread_id=t.thread_id, topic=t.topic,
                    salience=t.salience)

    save_thread_index(threads)

    summary = {"dormanted": dormanted, "resolved": resolved, "decayed": decayed}
    if dormanted or resolved:
        log("threads", "lifecycle_advanced", **summary)
    return summary


# ── Thread context injection ─────────────────────────────────────────

def build_thread_context_for_reflection() -> str:
    """
    Build a compact text block describing active threads for injection
    into the sage reflection prompt.

    This gives the reflection model awareness of ongoing cognitive threads
    without allowing it to modify thread metadata directly.
    """
    active = get_active_threads()
    if not active:
        return ""

    lines = []
    for t in active[:MAX_ACTIVE_THREADS]:
        depth_label = f"depth {t.depth}" if t.depth > 0 else "new"
        lines.append(f"- \"{t.topic}\" ({depth_label}, salience {t.salience:.2f})")

    return "ACTIVE COGNITIVE THREADS:\n" + "\n".join(lines)


def build_thread_summary_for_state() -> list[str]:
    """
    Return a list of active thread topic strings for state injection.
    Used by state_synthesis to populate the state snapshot.
    """
    active = get_active_threads()
    return [t.topic for t in active[:MAX_ACTIVE_THREADS]]


# ── Internals ────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Normalize a string for comparison."""
    return " ".join(s.lower().strip().split())


def _safe_slug(s: str) -> str:
    """Convert to filesystem-safe slug."""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in s.lower()).strip("_")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
