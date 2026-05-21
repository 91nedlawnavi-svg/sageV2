# models/prompts package
from models.prompts.templates import (
    build_chat_messages,
    # User-domain prompts
    EPISODIC_SYSTEM, episodic_prompt,
    EMOTIONAL_EXTRACT_SYSTEM, emotional_extract_prompt,
    EMOTIONAL_MERGE_SYSTEM, emotional_merge_prompt,
    USER_REFLECTION_SYSTEM, user_reflection_prompt,
    LIBRARY_EXTRACT_SYSTEM, LIBRARY_MERGE_SYSTEM,
    library_extract_prompt, library_merge_prompt,
    # Sage-domain prompts
    SAGE_REFLECTION_SYSTEM, sage_reflection_prompt,
    SAGE_CURIOSITY_SYSTEM, sage_curiosity_prompt,
    SAGE_WORLDVIEW_SYNTHESIS_SYSTEM, sage_worldview_prompt,
    # Search prompts
    SEARCH_SUMMARY_SYSTEM, search_summary_prompt, format_search_context,
    # Bootstrap prompts
    BOOTSTRAP_EPISODIC_SYSTEM, BOOTSTRAP_EMOTIONAL_SYSTEM,
)
