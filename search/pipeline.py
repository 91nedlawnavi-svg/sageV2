"""
search/pipeline.py — Unified Search Pipeline

Orchestrates the complete search flow:
  1. Query received (from user intent detection or autonomous curiosity)
  2. Provider called (DuckDuckGo)
  3. Results parsed into structured objects
  4. Results summarized by the reflection model
  5. Summary wrapped in labeled cognitive context block
  6. Optional: search memory written (for Sage's autonomous searches)

Used by both user-triggered search and Sage's autonomous search.
The difference is the initiator label and whether memory is persisted.

Returns a SearchOutcome object containing the formatted context
ready for prompt injection, plus metadata about the search.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from search.providers.duckduckgo import search_duckduckgo
from search.summarization.summarizer import summarize_results, build_search_context_block
from memory.storage.base import ensure_dirs, ts_filename, write_memory_entry
from config.settings import SEARCHES_DIR
from utils.logger import log


@dataclass
class SearchOutcome:
    """The result of a completed search pipeline execution."""
    query:         str
    initiator:     str                  # "user" or "Sage"
    reason:        str
    summary:       str
    context_block: str                  # ready for prompt injection
    result_count:  int
    success:       bool
    timestamp:     float = field(default_factory=time.time)


async def run_search(
    query: str,
    reason: str,
    initiator: str,
    client: httpx.AsyncClient,
    persist_to_sage_memory: bool = False,
) -> SearchOutcome:
    """
    Execute the full search pipeline for one query.

    query:                  the search string
    reason:                 why this search is being performed (for context injection)
    initiator:              "user" or "Sage" (affects labeling in context block)
    client:                 shared httpx.AsyncClient
    persist_to_sage_memory: if True, write search result to Sage's search log

    Returns a SearchOutcome with the formatted context block.
    """
    log("search", "pipeline_start", query=query, initiator=initiator, reason=reason)

    # Step 1: Fetch results from provider
    results = await search_duckduckgo(query)

    # Step 2: Summarize
    summary = await summarize_results(query, results, client)

    # Step 3: Build structured context block
    context_block = build_search_context_block(
        query=query,
        summary=summary,
        initiator=initiator,
        reason=reason,
    )

    outcome = SearchOutcome(
        query=query,
        initiator=initiator,
        reason=reason,
        summary=summary,
        context_block=context_block,
        result_count=len(results),
        success=bool(results),
    )

    # Step 4: Optionally persist to Sage's search log
    if persist_to_sage_memory:
        await _persist_search_to_sage_log(outcome)

    log("search", "pipeline_complete",
        query=query,
        initiator=initiator,
        result_count=len(results),
        success=outcome.success)

    return outcome


async def _persist_search_to_sage_log(outcome: SearchOutcome) -> None:
    """
    Write a search result to Sage's permanent search log.
    This gives Sage a memory of searches she has performed.
    """
    from config.settings import SAGE_SEARCH_LOG_DIR
    try:
        ensure_dirs(SAGE_SEARCH_LOG_DIR)
        stem = ts_filename(f"search_")
        content = (
            f"[query: {outcome.query}]\n"
            f"[reason: {outcome.reason}]\n"
            f"[result_count: {outcome.result_count}]\n"
            f"[success: {outcome.success}]\n\n"
            f"SUMMARY:\n{outcome.summary}\n"
        )
        await write_memory_entry(SAGE_SEARCH_LOG_DIR, stem, content)
    except Exception as e:
        log("search", "persist_error", error=str(e))
