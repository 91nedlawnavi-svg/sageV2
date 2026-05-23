"""
search/providers/duckduckgo.py — DuckDuckGo Search Provider

Performs web searches via DuckDuckGo's HTML interface.
No API key required — consistent with Sage's local-first philosophy.

Uses the duckduckgo-search library (duckduckgo_search).
Install: pip install duckduckgo-search

Design:
  - Returns structured result objects, not raw HTML
  - Applies result count cap (prevents overwhelming summarization)
  - Timeout-bounded — never hangs the system
  - Returns empty list on any failure (graceful degradation)
"""

from typing import Optional
from utils.logger import log


# Maximum results to fetch per search
MAX_RESULTS = 5


class SearchResult:
    """Structured search result from any provider."""
    def __init__(self, title: str, url: str, snippet: str):
        self.title   = title
        self.url     = url
        self.snippet = snippet

    def as_text(self) -> str:
        return f"{self.title}\n{self.url}\n{self.snippet}"


async def search_duckduckgo(
    query: str,
    max_results: int = MAX_RESULTS,
) -> list[SearchResult]:
    """
    Perform a DuckDuckGo web search.
    Returns a list of SearchResult objects (may be empty on failure).
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        log("search", "provider_unavailable",
            provider="duckduckgo",
            error="duckduckgo_search not installed. Run: pip install duckduckgo-search")
        return []

    results = []
    try:
        with DDGS(timeout=20) as ddgs:
            for r in ddgs.text(
                query,
                region="wt-wt",
                safesearch="off",
                max_results=max_results,
            ):
                results.append(SearchResult(
                    title   = r.get("title", ""),
                    url     = r.get("href", ""),
                    snippet = r.get("body", ""),
                ))
        log("search", "provider_success",
            provider="duckduckgo",
            query=query,
            result_count=len(results))
    except Exception as e:
        log("search", "provider_error",
            provider="duckduckgo",
            query=query,
            error=str(e))

    return results


def format_results_for_summarization(results: list[SearchResult]) -> str:
    """
    Format results as structured text for the summarization model.
    Never dumps full page content — only titles + snippets.
    """
    if not results:
        return "No results found."
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[{i}] {r.title}\n{r.snippet}\nURL: {r.url}")
    return "\n\n".join(parts)
