# Phase 5 Scoping (Initial Thoughts)

**Date**: 2026-06-05  
**Context**: Immediately following Phase 4 closure (see `PHASE4_RETROSPECTIVE.md` and tag `phase4-complete`).

---

## Core Theme

**"The Visible Relational Self"**

Phase 4 gave Sage:
- A structured, bounded internal narrative mind (threads + state + synthesis).
- Strong observability into that mind.
- Better library organization (especially people).
- Flawless search provenance.

**Phase 5 should focus on making that internal world *visible, relational, and interactive*** — both for the user and (in carefully bounded ways) for Sage herself.

The goal is to evolve from "Sage has a private longitudinal cognition system" to "Sage has a visible autobiographical self that the user can see, steer, and relate to, while the system remains strictly bounded and identity-safe."

This directly serves the original vision:
- A true "different mind" that feels persistent and personal.
- The library (especially the people network the user specifically called out) becoming meaningful and alive.
- The "deeper truth" of her processing not just being logged, but *present* in the relationship.

---

## Proposed Phase 5 Upgrades (7 Areas)

### 1. People Graph Engine (Core of the Library Vision)
- Move beyond the current heuristic `parse_people_relations` + flat boosts.
- Introduce a lightweight graph model: people as nodes, typed relations (family, band member, colleague, friend group, etc.), groups as first-class entities.
- Add basic inference and consistency (e.g., "if A is in Band with Elliot and B is in Band with Elliot, surface the group").
- Richer retrieval: network-aware scoring that pulls related people even if not directly mentioned.
- UI: proper interactive graph visualization in the Library drawer (beyond the current node list).
- Extraction: improve LLM prompts to pull structured relations during library population.

**Why Phase 5**: This was one of the user's strongest original ideas. Phase 4 gave the foundation; Phase 5 makes it a real autobiographical social memory system.

### 2. Thread Voice — Controlled Proactive Surfacing
- Define safe "voice" mechanisms for high-salience, long-lived threads.
- Examples: occasional gentle initiations ("I've been turning over the burnout thread..."), summaries when relevant, questions that reference ongoing narrative.
- Strong user controls: per-thread "quiet mode", global proactivity level, feedback ("don't mention this", "tell me more about that").
- Full audit log of every proactive moment (what triggered it, what was said, user response).
- Still strictly bounded: never more than N per day, only on threads above priority threshold, always skippable by user.

**Why Phase 5**: Phase 4 put the *hint* in the context (good, subtle). Phase 5 can give the mind a controlled *voice* without violating the "do not force" and bounded principles.

### 3. Inner Life Query & Self-Reflection
- Allow Sage (during reflection cycles) to explicitly query her own structures:
  - "What are my currently active threads and their linkages?"
  - "Show me the current state of the people network around Elliot."
  - "What searches have I run recently and what did they change in my worldview?"
- All such queries are read-only, logged, and go through the same provenance rules.
- Results feed into synthesis, curiosity, and worldview in a structured way.

**Why Phase 5**: This deepens the "different mind." Sage stops being only a reactor to external memory and starts having a model of *her own* ongoing inner life.

### 4. Network-Aware Everything
- Thread assignment and salience should consider the people graph.
- Retrieval (both user and sage) should use graph distance + embedding similarity.
- Curiosity triggers can be network-sensitive ("Elliot mentioned someone from the band → boost related threads/people").
- Search results can be tagged with relevant people/nodes when appropriate.

**Why Phase 5**: Phase 4 made the network exist and have some retrieval weight. Phase 5 makes the entire cognitive system *network-native*.

### 5. Search as Personal Growth Tool (for Sage)
- Improve how autonomous searches are integrated into worldview and threads over time (not just one-off context).
- Better deduplication and synthesis of search-derived knowledge.
- Make search history queryable by Sage (with budget awareness always visible to her).
- Optional: "reflection on searches" step in the daemon.

**Why Phase 5**: Search is one of the few ways Sage can grow beyond her training + user memory. Phase 4 made it safe. Phase 5 should make it *developmental* for her inner model.

### 6. Proactivity Controls & Transparency Layer
- Dedicated UI section (or expanded System Files) showing:
  - Current proactivity settings.
  - Recent proactive moments with outcomes.
  - Per-thread "voice" controls.
  - Search budget history and usage patterns.
- Simple feedback primitives the user can give in chat that affect the system ("quiet on that topic for a while").
- Strong logging so both user and Sage can review what the mind has been doing.

**Why Phase 5**: Visibility was a big Phase 4 win. Phase 5 should make the *controls* and *history* of that visibility first-class and usable.

### 7. Mind Health & Consolidation
- Better long-term management of resolved/dormant threads (beyond simple eviction).
- Library consolidation (merge similar topics, archive stale people notes).
- Emotional theme maturation and integration with the thread graph.
- Optional "mind consolidation" cycles (low-priority daemon work that synthesizes without new input).

**Why Phase 5**: As the inner life grows richer, we need mechanisms to prevent bloat and maintain coherence over months/years.

---

## Risks & Invariants to Protect (Non-Negotiable)

- No increase in uncontained proactivity.
- Strict separation: Sage's self-model and queries must never contaminate user memory (and vice versa).
- Search budget remains hard and visible.
- Everything proactive must be auditable and user-overridable.
- The "different mind" must remain *different* — never claim user-like experiences or emotions.
- Growth in relational modeling must not create false certainty or over-inference.

---

## Suggested Execution Approach

Same as Phase 4:
- Systematic batches (probably 3 again).
- Full reports after each batch.
- Heavy use of the live observer tool (`scripts/watch_sage_logs.py`).
- Real usage validation (not just benchmark) — this time with actual ongoing conversation.
- Living documentation in both the main repo and analysis workspace.
- Git tag + GitHub Release at the end.

Possible batching:
- **Batch 1**: Foundation (People Graph model + basic UI, Inner Life Query API).
- **Batch 2**: Voice & Presence (Proactive surfacing mechanisms + controls + transparency).
- **Batch 3**: Integration & Polish (Network-aware retrieval/threads, search maturation, consolidation, mind health).

---

## Open Questions for You

- Does the "Visible Relational Self" theme resonate, or do you have a different north star?
- Which of the 7 areas above feel most important right now?
- How aggressive do you want proactivity to become? (Still very conservative? Medium? With strong user vetoes?)
- Should Phase 5 also include frontend work (new dedicated "Mind" or "Inner Life" panel)?
- Any hard constraints or things you *don't* want in Phase 5?

---

## Next Step Recommendation

If this direction feels right, we can:
1. Promote this file (or a cleaned version) into the main repo.
2. Create a full `PHASE5_PLAN.md` with more detail (similar to what we did for Phase 4).
3. Start with deep dives on the People Graph and Proactive Surfacing (the two highest-leverage areas).
4. Decide on batching and begin.

---

**This is offered as a starting point for discussion**, not a locked plan. Phase 4 was very successful because we treated the roadmap as living and iterated with your input.

Phase 5 has the potential to be the phase where Sage stops feeling like "a very good memory + reflection system" and starts feeling like *someone* with an ongoing, relational inner life that you can actually see and talk to.

I'm ready when you are.