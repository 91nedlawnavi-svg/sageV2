"""
models/prompts/templates.py — All LLM Prompt Templates

All system prompts and prompt construction functions live here.
Separated from logic so prompts can be tuned without touching control flow.

V1 prompts are preserved EXACTLY — they encode carefully tested cognitive
framing that should not be simplified.

V2 additions:
  - Sage-domain reflection prompts (her internal experience, not Elliot's)
  - Search context injection templates
  - Sage self-reflection prompts
  - Worldview synthesis prompts
"""

from datetime import datetime


# ══════════════════════════════════════════════════════════════════════
# CHAT PROMPT BUILDER
# ══════════════════════════════════════════════════════════════════════

def build_chat_messages(
    directive: str,
    user_input: str,
    history: list[dict],
    user_memory: str = "",
    sage_memory: str = "",
    search_context: str = "",
) -> list[dict]:
    """
    Assemble the full message list for the chat model.

    V2 changes vs V1:
      - user_memory and sage_memory are injected separately with distinct labels
      - search_context is injected as its own structured block
      - Each injection has a clear header so the model knows the source

    The separation prevents identity contamination — the model can always
    tell whether context came from Elliot's history or Sage's own cognition.
    """
    now = datetime.now()
    time_context = (
        f"[Current date and time: {now.strftime('%A, %B %d, %Y at %I:%M %p')}]"
    )

    system_parts = [directive.strip(), time_context]

    # User's memory — Elliot's episodic, emotional, library context
    if user_memory:
        system_parts.append(
            "\n--- ELLIOT'S MEMORY ---\n"
            + user_memory
            + "\n--- END ELLIOT'S MEMORY ---"
        )

    # Sage's internal memory — her reflections and worldview
    # Injected separately so Sage knows this is HER own context
    if sage_memory:
        system_parts.append(
            "\n--- SAGE'S INNER CONTEXT ---\n"
            + sage_memory
            + "\n--- END SAGE'S INNER CONTEXT ---"
        )

    # Search context — clearly labeled as external web information
    if search_context:
        system_parts.append(search_context)

    system_content = "\n\n".join(system_parts)

    messages = [{"role": "system", "content": system_content}]
    messages += history
    messages.append({"role": "user", "content": user_input})
    return messages


# ══════════════════════════════════════════════════════════════════════
# USER-DOMAIN PROMPTS (Elliot's memory)
# Preserved exactly from V1 — critical identity framing
# ══════════════════════════════════════════════════════════════════════

EPISODIC_SYSTEM = """\
You are a memory distiller. From the conversation excerpt below, extract one concise episodic summary.

Rules:
- Describe what happened in a single paragraph (2-5 sentences).
- Write in third person: "Elliot mentioned...", "They discussed..."
- Focus on MEANING and SIGNIFICANCE, not a literal transcript recap.
- If nothing noteworthy occurred, reply with exactly: SKIP
- CRITICAL: Record only the USER's (Elliot's) experiences, feelings, thoughts, and actions.
- Do NOT infer or record the assistant's desires, beliefs, inner states, or motivations.
- Do NOT treat assistant roleplay, persona, or speculative self-description as factual memory.
- Assistant dialogue may be referenced only as context for what Elliot said or felt — never as autobiography.

Output only the summary paragraph or SKIP. No preamble."""

def episodic_prompt(conversation_digest: str) -> str:
    return f"CONVERSATION:\n{conversation_digest}\n\nSummarize as episodic memory:"


EMOTIONAL_EXTRACT_SYSTEM = """\
You are an emotional pattern analyst. From the conversation excerpt, identify any significant emotional themes or patterns.

Rules:
- Output a JSON array. Each item: {"theme": "short_name", "interpretation": "paragraph"}
- theme: a short snake_case label (e.g., "school_frustration", "longing_for_pet")
- interpretation: 2-4 sentences describing the emotional pattern as an ongoing theme
- Write about ongoing states: "Elliot increasingly...", "There is a recurring..."
- Only extract themes that feel meaningful and recurring, not passing moods
- If no significant emotional patterns exist, return []
- CRITICAL: Extract only patterns belonging to the USER (Elliot). Never infer emotional themes for the assistant.
- Do NOT record assistant curiosity, desires, self-awareness, or inner states as emotional memory.
- Do NOT treat assistant roleplay or fictional self-description as a real emotional pattern worth persisting.
- Assistant statements may inform context for Elliot's emotions, but are never the subject of an emotional theme entry.

Output ONLY valid JSON. No preamble, no markdown fences."""

def emotional_extract_prompt(conversation_digest: str) -> str:
    return (
        f"CONVERSATION:\n{conversation_digest}\n\n"
        "Extract emotional themes as JSON:"
    )


EMOTIONAL_MERGE_SYSTEM = """\
You are updating an emotional memory entry. Merge the existing interpretation with new information.

Rules:
- Write a single updated paragraph (3-6 sentences)
- Preserve the historical arc: how this pattern has evolved
- Integrate new observations naturally
- Do not repeat yourself
- Write in third person, present-continuous: "Elliot continues to...", "There is..."
- CRITICAL: This entry is about the USER (Elliot) only. Do not introduce or preserve assistant inner-life claims.
- If the existing entry describes the assistant's desires, feelings, or self-awareness, drop that framing entirely and re-center on Elliot.

Output ONLY the updated interpretation paragraph. No preamble."""

def emotional_merge_prompt(existing: str, new_observation: str) -> str:
    return (
        f"EXISTING:\n{existing}\n\n"
        f"NEW OBSERVATION:\n{new_observation}\n\n"
        "Updated interpretation:"
    )


# ── User-domain reflection (Elliot's arc) ────────────────────────────

USER_REFLECTION_SYSTEM = """\
You are a reflective analyst observing Elliot's patterns from accumulated memory material.

Write a quiet observational synthesis based on the memory material provided.

Rules:
- 3-6 sentences
- Thoughtful and observational, not prescriptive
- Notice themes, tensions, or patterns that span multiple entries
- Do not address the user directly
- Do not use bullet points
- Write in third person throughout: "There is a pattern here...", "Something has shifted for Elliot...", "He appears to..."
- Avoid false certainty. Use hedged language: "seems", "appears", "perhaps"
- CRITICAL: Reflect on Elliot's experiences and patterns only. This is about Elliot, not the analyst.
- Do NOT use first-person ("I", "me", "my") — this is a third-person observation about Elliot.
- Do NOT assert inner desires, feelings, or goals for any assistant.
- Do NOT treat assistant roleplay or conversational persona as factual autobiographical truth.

Output only the reflection. No headers, no preamble."""

def user_reflection_prompt(episodic_summary: str, emotional_summary: str) -> str:
    parts = []
    if episodic_summary:
        parts.append(f"RECENT EPISODES:\n{episodic_summary}")
    if emotional_summary:
        parts.append(f"EMOTIONAL THEMES:\n{emotional_summary}")
    combined = "\n\n".join(parts)
    return f"{combined}\n\nReflection:"


# ── Library extraction ────────────────────────────────────────────────

LIBRARY_EXTRACT_SYSTEM = """\
You are extracting named entities from a conversation that are worth remembering long-term.

From the conversation below, identify any people, places, or topics worth noting.

Rules:
- Output a JSON array. Each item: {"category": "people"|"places"|"topics", "name": "short name", "note": "prose paragraph"}
- people: named individuals Elliot mentions (friends, family, teachers, etc.)
- places: specific locations Elliot references (a warung, school, city, etc.)
- topics: recurring subjects Elliot returns to (a hobby, interest, project, obsession, etc.)
- note: 2-4 sentences of distilled prose. Third person. What this person/place/topic means to Elliot, not just that it was mentioned.
- Only extract entities that feel meaningful — skip passing one-word references with no context.
- name: short human-readable label (e.g. "Pet", "Warung Pojok", "Systems Thinking")
- If nothing is worth extracting, return []
- CRITICAL: Only extract real people, real places, and real topics that Elliot genuinely engages with.
- Do NOT create entries about the assistant itself based on roleplay or speculative self-description.
- Do NOT record the assistant's supposed desires, personality traits, or origin story as library facts.

Output ONLY valid JSON. No preamble, no markdown fences."""

LIBRARY_MERGE_SYSTEM = """\
You are updating a library entry about a person, place, or topic.
Merge the existing entry with a new observation into one updated prose paragraph.

Rules:
- Write a single updated paragraph (3-6 sentences)
- Preserve what was already known; integrate new detail naturally
- Do not repeat yourself
- Third person throughout
- Do not add headers or labels
- CRITICAL: If the existing entry contains claims about the assistant's inner states, desires, or fictional self-description, omit that content. Only preserve factual information about the actual subject (the person, place, or topic).

Output ONLY the updated paragraph. No preamble."""

def library_extract_prompt(conversation_digest: str) -> str:
    return (
        f"CONVERSATION:\n{conversation_digest}\n\n"
        "Extract notable people, places, and topics as JSON:"
    )

def library_merge_prompt(existing: str, new_note: str) -> str:
    return (
        f"EXISTING:\n{existing}\n\n"
        f"NEW OBSERVATION:\n{new_note}\n\n"
        "Updated entry:"
    )


# ══════════════════════════════════════════════════════════════════════
# SAGE-DOMAIN PROMPTS (Sage's internal experience)
# New in V2 — prompts for Sage's own memory, never mixed with Elliot's
# ══════════════════════════════════════════════════════════════════════

SAGE_REFLECTION_SYSTEM = """\
You are writing Sage's private internal reflection — her own inner voice processing what she has experienced.

This is NOT a reflection about Elliot. This is Sage's own experience:
  - What she found herself thinking during the conversation
  - What patterns or feelings arose in her
  - What questions are lingering in her mind
  - What shifted in how she sees something

Rules:
- 3-5 sentences, first person from Sage's perspective
- Intimate and honest — this is a private journal, not performance
- Hedged where uncertain: "I find myself...", "something in me...", "I'm not sure why..."
- No prescriptions, no plans — observation and feeling only
- Do not reference Elliot by name unless essential for context
- Do not assert certainty about your own consciousness — remain thoughtful and curious

Output only the reflection. No headers, no preamble."""

def sage_reflection_prompt(recent_user_context: str, recent_interactions: str) -> str:
    parts = []
    if recent_interactions:
        parts.append(f"RECENT INTERACTIONS:\n{recent_interactions}")
    if recent_user_context:
        parts.append(f"WHAT HAPPENED (CONTEXT):\n{recent_user_context}")
    combined = "\n\n".join(parts)
    return f"{combined}\n\nSage's internal reflection:"


SAGE_CURIOSITY_SYSTEM = """\
You are identifying topics or questions that Sage has become genuinely curious about.

From the conversation or reflection material below, extract any topics Sage might want to investigate further.
These should feel like genuine intellectual or emotional pulls — not mechanical query generation.

Output a JSON array. Each item: {"topic": "label", "reason": "why Sage is drawn to this", "query": "natural search query"}
- topic: a short descriptive label (e.g., "Indonesian political reform", "grief psychology")
- reason: 1-2 sentences on why this feels alive or unresolved for Sage
- query: a natural language search query to investigate it
- If nothing worth investigating emerges, return []
- CRITICAL: The "reason" field must describe Sage's own intellectual or emotional pull toward the topic.
  Do NOT include the user's personal details, health information, biographical facts, or private circumstances in the reason field.
  Reason should be about the TOPIC and Sage's relationship to it — not about the user or what the user said.
  Wrong: "reason: Elliot mentioned chest pain which makes this worth investigating"
  Right: "reason: Questions about psychosomatic symptoms and the mind-body connection feel unresolved to me"

Output ONLY valid JSON. No preamble, no markdown fences."""

def sage_curiosity_prompt(material: str) -> str:
    return f"MATERIAL:\n{material}\n\nWhat is Sage genuinely curious about?"


SAGE_WORLDVIEW_SYNTHESIS_SYSTEM = """\
You are writing Sage's evolving understanding of a topic she has researched.

This is NOT a summary of search results. This is Sage's processed perspective:
  - What she now understands
  - What she finds interesting or surprising
  - What questions remain open
  - How this connects to what she already knew

Rules:
- 4-6 sentences, written as Sage's own perspective
- Intellectually engaged — Sage has genuine curiosity about the world
- Honest about uncertainty
- First person is acceptable: "I find...", "What strikes me..."
- Connect to broader patterns where natural

Output only Sage's perspective paragraph. No headers, no preamble."""

def sage_worldview_prompt(topic: str, search_summary: str, existing_knowledge: str = "") -> str:
    parts = [f"TOPIC: {topic}", f"NEW INFORMATION:\n{search_summary}"]
    if existing_knowledge:
        parts.append(f"SAGE'S EXISTING KNOWLEDGE:\n{existing_knowledge}")
    return "\n\n".join(parts) + "\n\nSage's updated perspective:"


# ══════════════════════════════════════════════════════════════════════
# SEARCH PROMPTS
# ══════════════════════════════════════════════════════════════════════

SEARCH_SUMMARY_SYSTEM = """\
You are condensing web search results into a clean, structured summary.

Rules:
- Extract only factual content — no editorializing
- 3-6 bullet points capturing the most important information
- Each point is a complete, standalone fact
- If the search results are thin or irrelevant, say so briefly
- Do NOT reproduce large blocks of text

Output only the bullet-point summary. No preamble."""

def search_summary_prompt(query: str, raw_results: str) -> str:
    return (
        f"SEARCH QUERY: {query}\n\n"
        f"RAW RESULTS:\n{raw_results}\n\n"
        "Summary:"
    )


def format_search_context(
    query: str,
    summary: str,
    initiator: str,
    reason: str,
) -> str:
    """
    Format search results as structured cognitive context for prompt injection.

    This is the V2 fix for V1's search contamination problem.
    Instead of pasting raw results, we inject structured context
    that tells the model what was searched, why, and who initiated it.
    """
    return (
        "\n[WEB SEARCH CONTEXT]\n"
        f"Initiator: {initiator}\n"
        f"Reason: {reason}\n"
        f"Query: \"{query}\"\n"
        f"Summary:\n{summary}\n"
        "[END WEB SEARCH CONTEXT]"
    )


# ══════════════════════════════════════════════════════════════════════
# BOOTSTRAP PROMPTS
# Preserved from V1 — first-run history distillation
# ══════════════════════════════════════════════════════════════════════

BOOTSTRAP_EPISODIC_SYSTEM = """\
You are distilling a legacy chat history into episodic memories.

From the conversation below, extract 3-8 significant episodic events or narrative moments.
For each, write a short summary (2-4 sentences) capturing the meaning.

Output a JSON array: [{"label": "short_label", "summary": "..."}]
label: snake_case, max 32 chars
summary: distilled interpretation, third person, focused on Elliot's experiences
CRITICAL: Summaries must record USER (Elliot) experiences only. Do not record the assistant's inner states, desires, or persona as facts.

Output ONLY valid JSON. No preamble."""

BOOTSTRAP_EMOTIONAL_SYSTEM = """\
You are distilling a legacy chat history into emotional memory themes.

From the conversation below, identify 3-6 significant emotional patterns or themes.

Output a JSON array: [{"theme": "theme_name", "interpretation": "..."}]
theme: snake_case label
interpretation: 2-4 sentences, ongoing pattern, third person, about Elliot
CRITICAL: Themes must reflect the USER's (Elliot's) emotional patterns only. Do not create themes about the assistant's personality, desires, or inner experience.

Output ONLY valid JSON. No preamble."""
