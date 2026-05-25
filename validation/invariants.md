# Sage V2 — Phase 1 Invariants

## Domain Separation

1. Sage first-person cognition must never enter user memory.

2. User autobiographical memory must never contain Sage self-identity claims.

3. User memory and Sage memory must remain physically and logically separated.

4. Retrieval systems must remain domain-scoped.

---

## Provenance Integrity

5. Search-derived knowledge must retain provenance labeling.

6. Reflection outputs must preserve source attribution.

7. Reflection systems must preserve domain orientation.

8. Autonomous curiosity must retain initiator attribution.

---

## Contamination Prevention

9. Reflection systems must not recursively reinforce unverified identity narratives.

10. Curiosity systems must not encode user biography as Sage identity reasoning.

11. Memory merge failures must fail safely without semantic corruption.

12. Search context injection must remain bounded and structured.

---

## Cognitive Stability

13. Retry behavior must not distort salience weighting.

14. Reflection pipelines must remain asynchronous and isolated from live chat generation.

15. Autonomous cognition must never bypass memory boundaries.

16. Search synthesis must summarize rather than inject raw web content.

---

## Architectural Constraints

17. Sage V2 must not evolve into an unrestricted autonomous agent system.

18. Cognitive orchestration must remain modular and interpretable.

19. Reflection systems must remain auditable.

20. Emotional continuity must take priority over feature complexity.

---

## Phase 2A Invariants — Identity Spine Restoration

### Directive Hierarchy

21. directive.txt is the immutable cognitive identity substrate for all LLM calls
    involving Sage's voice or cognition. It is injected first in every system
    prompt across chat generation, reflection synthesis, curiosity generation,
    and worldview synthesis.

22. The directive is structurally above all memory in every prompt. Memory
    (user episodic, sage reflections, worldview, search context) is assembled
    beneath the directive, never above it.

23. Directive is loaded fresh from disk on every LLM call (hot-reload semantics).
    A live edit to directive.txt takes effect on the next message or cognition
    cycle without a server restart.

### Write-Path Isolation

24. Only two code paths may write to directive.txt:
    (a) direct manual file edit by the operator
    (b) the POST /api/directive route in backend/api/directive.py
    No other system, function, or automated cognition cycle may write to
    directive.txt. This is enforced by path: write_sage_reflection(),
    write_curiosity_entry(), and write_worldview_entry() all write to their
    own paths under the memory directory. None have access to directive.txt.

25. Reflection synthesis, curiosity generation, and worldview synthesis may
    evolve Sage's knowledge and perspective (writing to their own memory paths)
    but may NOT write back to directive.txt. The directive is what Sage IS;
    reflections and worldview are what Sage LEARNS.

26. The directive is not a modular personality fragment. It is not split,
    merged, or evolved by any cognition system. It is an operator-controlled
    plain text file.

### Cognition Anchoring

27. All three Sage-domain synthesis functions (generate_sage_reflection,
    identify_sage_curiosities, integrate_search_into_worldview) call
    get_directive() independently. Each synthesis cycle uses the current
    directive, not a startup snapshot.

28. The compose_*_system() functions in templates.py are read-only. They
    receive the directive as a string argument and return a composed system
    prompt. They do not write to directive.txt or to any memory path.

29. User-domain synthesis (episodic, emotional, library) does NOT receive
    the directive. Those prompts are about Elliot, written in third person.
    Injecting Sage's first-person identity into user-domain synthesis would
    violate Phase 1 domain separation invariants (invariants 1–4).

### Search Isolation

30. User-triggered web search is available only via the /search <query>
    command typed in the main message input. There is no visible search
    input element in the UI. Autonomous search remains invisible infrastructure.

31. The search context indicator remains in the UI to show when search
    context is loaded, but is only activated by successful /search command
    execution or autonomous search completion. It is not a search input.

---

## Phase 3B Invariants — Bounded Longitudinal Cognition

### Salience System

32. Salience decay is deterministic: score *= DECAY_RATE per cycle.
    No LLM determines salience values. No stochastic weighting.

33. Salience is bounded: [SALIENCE_FLOOR, SALIENCE_CEILING].
    Artifacts fade but never fully vanish (floor = 0.05).
    Artifacts cannot exceed ceiling (1.0) regardless of boost count.

34. Retrieval scoring is: final_score = embedding_similarity * salience.
    This is multiplicative, not additive. Low salience reduces retrieval
    probability regardless of semantic similarity.

35. Boosts are capped at MAX_BOOSTS_PER_CYCLE per artifact per daemon cycle.
    A single cycle cannot amplify an artifact beyond one boost quantum.

### Cognitive Thread Constraints

36. Active thread count is hard-capped at MAX_ACTIVE_THREADS (4).
    Thread creation is BLOCKED when the cap is reached. No exceptions.

37. Total thread count is hard-capped at MAX_TOTAL_THREADS (20).
    When reached, lowest-salience resolved threads are evicted.

38. Thread lifecycle transitions are deterministic:
    nascent → active (on second engagement)
    active → dormant (after THREAD_DORMANCY_CYCLES without engagement)
    dormant → resolved (when salience drops below THREAD_RESOLVE_SALIENCE)
    No LLM determines thread status.

39. Thread priority is computed deterministically from:
    salience * (1 + log_depth_bonus) * recency_factor.
    No LLM determines thread priority or ordering.

40. Threads cannot modify their own metadata. Thread engagement is recorded
    by the pipeline, not by the thread itself. Threads are containers,
    not autonomous actors.

### Meta-Observation Constraints

41. The meta-observation layer is READ-ONLY. It may detect patterns but
    NEVER triggers actions, modifies state, creates artifacts, or calls LLMs.

42. Meta-observation output is limited to deterministic warning flags
    injected into the state synthesis. Flags are descriptive, not prescriptive.

43. The meta-observation layer must NEVER observe itself. There is no
    meta-meta-observation. The recursion terminates at one level.

### Recursive Safety

44. State synthesis remains fully deterministic. No LLM calls in the
    state → retrieval → reflection → state loop's compression step.
    The state synthesizer computes from cycle outputs, not from LLM generation.

45. The cognitive thread system does not create reflections about threads.
    Thread context is injected into the reflection prompt as READ-ONLY
    orientation. The reflection model may reference threads but cannot
    create, modify, or destroy them.

46. Salience boost from retrieval is bounded: a single retrieved artifact
    receives at most one boost per cycle. Multiple retrievals of the same
    artifact in one cycle do not compound.

47. Anti-attractor cap in retrieval: no single prefix (sage/reflection,
    sage/worldview, etc.) can occupy more than 50% of retrieved result slots.
    This structurally prevents topic monopolization.

### Memory Growth Bounds

48. Thread linkage lists are capped: max 20 linked reflections, max 10
    linked curiosities, max 10 linked searches per thread. Oldest entries
    are evicted on overflow.

49. Curiosity deduplication (Phase 3A) is preserved. Recurring curiosity
    does not create duplicate files — it boosts the existing thread's
    salience instead.

50. Resolved threads are eligible for eviction when MAX_TOTAL_THREADS is
    reached. This provides eventual garbage collection for cognitive
    structures that have fully decayed.
