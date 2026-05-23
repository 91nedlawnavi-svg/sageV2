# search/providers/searxng.py
import httpx
from dataclasses import dataclass

SEARXNG_URL = "http://localhost:8080/search"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

    def as_text(self) -> str:
        return f"{self.title}\n{self.url}\n{self.snippet}"


async def search_searxng(query: str, max_results: int = 10) -> list[SearchResult]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                SEARXNG_URL,
                params={"q": query, "format": "json", "pageno": 1},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.RequestError as e:
        raise RuntimeError(f"SearXNG unreachable: {e}") from e
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"SearXNG returned {e.response.status_code}") from e

    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("content", ""),
        )
        for r in data.get("results", [])[:max_results]
    ]
