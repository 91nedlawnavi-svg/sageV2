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
