"""
search/summarization/summarizer.py — Search Result Summarization

This is the V2 fix for V1's fatal search integration flaw.

V1 pasted raw search results directly into the model prompt.
This caused identity drift, language contamination, and model confusion.

V2 NEVER injects raw results. Instead:
  1. Raw results are summarized into structured bullet points
  2. Summary is wrapped in a labeled cognitive context block
  3. The model is told what was searched, why, and by whom
  4. The model can reason about the search as an event, not just absorb content

The format_search_context function in models/prompts/templates.py defines
the exact injection format. This module handles the summarization step.
"""

import httpx

from models.inference.engine import nim_complete
from models.prompts.templates import (
    SEARCH_SUMMARY_SYSTEM,
    search_summary_prompt,
    format_search_context,
)
from search.providers.duckduckgo import SearchResult, format_results_for_summarization
from utils.logger import log


async def summarize_results(
    query: str,
    results: list[SearchResult],
    client: httpx.AsyncClient,
) -> str:
    """
    Summarize raw search results into clean structured bullet points.
    Returns formatted summary string, or a fallback message if summarization fails.
    """
    if not results:
        return "No results were found for this search."

    raw_text = format_results_for_summarization(results)

    summary = await nim_complete(
        system=SEARCH_SUMMARY_SYSTEM,
        user=search_summary_prompt(query, raw_text),
        client=client,
        max_tokens=300,
    )

    if not summary:
        # Fallback: extract just the snippets manually
        log("search", "summarization_failed", query=query)
        fallback_parts = [f"- {r.snippet[:200]}" for r in results[:3] if r.snippet]
        return "\n".join(fallback_parts) if fallback_parts else "Search returned results but summarization failed."

    log("search", "summarized", query=query, summary_len=len(summary))
    return summary


def build_search_context_block(
    query: str,
    summary: str,
    initiator: str,
    reason: str,
) -> str:
    """
    Wrap a search summary in the structured context block for prompt injection.

    This gives the model full situational awareness:
    - WHAT was searched
    - WHY it was searched
    - WHO initiated it (user vs Sage autonomous)
    - WHAT was found (the summarized bullets)

    The model can reference this information naturally without
    being contaminated by raw web text.
    """
    return format_search_context(
        query=query,
        summary=summary,
        initiator=initiator,
        reason=reason,
    )
