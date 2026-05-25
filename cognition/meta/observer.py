"""
cognition/meta/observer.py — Deterministic Meta-Observation Layer

A READ-ONLY sensor that detects pathological cognitive patterns.
Runs once per daemon cycle, AFTER the reflection pipeline completes.

This layer:
  - Detects convergence (same topic dominating recent cycles)
  - Detects oscillation (emotional orientation flipping rapidly)
  - Detects fixation (single thread consuming all engagement)
  - Detects narrowing (active threads collapsing toward one topic)

This layer DOES NOT:
  - Generate reflections
  - Modify thread metadata
  - Trigger searches
  - Call any LLM
  - Create new artifacts
  - Modify salience scores

It produces WARNING FLAGS that are injected into the state synthesis.
The reflection model may notice these flags in subsequent cycles and
naturally adjust its output — but the flags themselves take no action.

This is the only recursive safety valve in the architecture.
If this layer detects runaway amplification, it surfaces the signal
but never acts on it. Action remains with the human operator.

All detection is purely deterministic: string comparison, counts, thresholds.
"""

from dataclasses import dataclass, field
from typing import Optional

from cognition.threads.store import get_active_threads, load_thread_index, ACTIVE_STATES
from memory.sage.state import load_sage_state
from utils.logger import log


# ── Thresholds ───────────────────────────────────────────────────────

# Convergence: if a single thread has depth > this, warn
CONVERGENCE_DEPTH_THRESHOLD = 8

# Fixation: if a single thread's salience is > this fraction of total active salience
FIXATION_SALIENCE_RATIO = 0.65

# Oscillation: detect from state history (recent_synthesis field changes)
# We track via a simple heuristic: if emotional_orientation has no words in common
# with what it was 2 cycles ago, flag oscillation. Stored in state as
# _prev_orientations (last 3).

# Narrowing: if all active threads share a normalized substring, cognition is narrowing
NARROWING_WORD_OVERLAP_THRESHOLD = 0.5


# ── Output ───────────────────────────────────────────────────────────

@dataclass
class MetaObservation:
    """Immutable observation result. Injected into state synthesis."""
    convergence_warning: bool = False
    convergence_detail: str = ""
    fixation_warning: bool = False
    fixation_detail: str = ""
    oscillation_warning: bool = False
    oscillation_detail: str = ""
    narrowing_warning: bool = False
    narrowing_detail: str = ""

    @property
    def has_warnings(self) -> bool:
        return any([
            self.convergence_warning,
            self.fixation_warning,
            self.oscillation_warning,
            self.narrowing_warning,
        ])

    def as_state_flags(self) -> list[str]:
        """Produce compact flag strings for state injection."""
        flags = []
        if self.convergence_warning:
            flags.append(f"⚠ convergence: {self.convergence_detail}")
        if self.fixation_warning:
            flags.append(f"⚠ fixation: {self.fixation_detail}")
        if self.oscillation_warning:
            flags.append(f"⚠ oscillation: {self.oscillation_detail}")
        if self.narrowing_warning:
            flags.append(f"⚠ narrowing: {self.narrowing_detail}")
        return flags


# ── Public API ───────────────────────────────────────────────────────

def observe(prev_orientations: list[str] | None = None) -> MetaObservation:
    """
    Run all meta-observation checks. Purely deterministic.
    Returns an immutable MetaObservation.

    prev_orientations: the last 3 emotional_orientation values from state history.
    If not provided, oscillation detection is skipped.
    """
    obs = MetaObservation()

    active_threads = get_active_threads()

    # 1. Convergence detection
    _check_convergence(active_threads, obs)

    # 2. Fixation detection
    _check_fixation(active_threads, obs)

    # 3. Oscillation detection
    if prev_orientations:
        _check_oscillation(prev_orientations, obs)

    # 4. Narrowing detection
    _check_narrowing(active_threads, obs)

    if obs.has_warnings:
        log("meta", "warnings_detected",
            convergence=obs.convergence_warning,
            fixation=obs.fixation_warning,
            oscillation=obs.oscillation_warning,
            narrowing=obs.narrowing_warning)

    return obs


# ── Detection functions ──────────────────────────────────────────────

def _check_convergence(threads: list, obs: MetaObservation) -> None:
    """A single thread has accumulated excessive depth."""
    for t in threads:
        if t.depth >= CONVERGENCE_DEPTH_THRESHOLD:
            obs.convergence_warning = True
            obs.convergence_detail = (
                f"\"{t.topic}\" has reached depth {t.depth} — "
                f"cognitive resources may be over-concentrated here"
            )
            return


def _check_fixation(threads: list, obs: MetaObservation) -> None:
    """A single thread dominates total active salience."""
    if len(threads) < 2:
        return

    total_salience = sum(t.salience for t in threads)
    if total_salience <= 0:
        return

    for t in threads:
        ratio = t.salience / total_salience
        if ratio >= FIXATION_SALIENCE_RATIO:
            obs.fixation_warning = True
            obs.fixation_detail = (
                f"\"{t.topic}\" holds {ratio:.0%} of total active salience — "
                f"other threads may be starved"
            )
            return


def _check_oscillation(prev_orientations: list[str], obs: MetaObservation) -> None:
    """
    Emotional orientation is changing too rapidly between cycles.
    Detected by checking word overlap between consecutive orientations.
    If no two consecutive orientations share any words, flag it.
    """
    if len(prev_orientations) < 3:
        return

    # Check if each consecutive pair shares at least one content word
    flips = 0
    for i in range(len(prev_orientations) - 1):
        words_a = _content_words(prev_orientations[i])
        words_b = _content_words(prev_orientations[i + 1])
        if words_a and words_b and not words_a.intersection(words_b):
            flips += 1

    if flips >= 2:
        obs.oscillation_warning = True
        obs.oscillation_detail = (
            f"emotional orientation has flipped {flips} times in last "
            f"{len(prev_orientations)} cycles — register may be unstable"
        )


def _check_narrowing(threads: list, obs: MetaObservation) -> None:
    """
    All active threads converge toward the same topic space.
    Detected by high word overlap across thread topic strings.
    """
    if len(threads) < 2:
        return

    # Collect content words from all thread topics
    all_word_sets = [_content_words(t.topic) for t in threads]
    all_word_sets = [ws for ws in all_word_sets if ws]

    if len(all_word_sets) < 2:
        return

    # Check pairwise overlap
    overlapping_pairs = 0
    total_pairs = 0
    for i in range(len(all_word_sets)):
        for j in range(i + 1, len(all_word_sets)):
            total_pairs += 1
            set_a = all_word_sets[i]
            set_b = all_word_sets[j]
            union = set_a | set_b
            intersection = set_a & set_b
            if union and len(intersection) / len(union) >= NARROWING_WORD_OVERLAP_THRESHOLD:
                overlapping_pairs += 1

    if total_pairs > 0 and overlapping_pairs / total_pairs >= 0.5:
        obs.narrowing_warning = True
        obs.narrowing_detail = (
            f"{overlapping_pairs}/{total_pairs} thread pairs share significant "
            f"topic overlap — cognitive diversity may be decreasing"
        )


# ── Helpers ──────────────────────────────────────────────────────────

def _content_words(text: str) -> set[str]:
    """Extract meaningful words (>3 chars, not stopwords) from text."""
    if not text:
        return set()
    stopwords = {
        "the", "and", "for", "that", "this", "with", "from", "about",
        "what", "how", "why", "when", "where", "which", "there",
    }
    words = text.lower().split()
    return {w.strip(".,;:-\"'()") for w in words if len(w) > 3 and w not in stopwords}
