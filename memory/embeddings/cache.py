"""
memory/embeddings/cache.py — Embedding client with LRU + Filesystem Cache

Supports both:
  - NVIDIA NIM (current default)
  - Local llama.cpp server (--embedding) or any OpenAI-compatible /v1/embeddings endpoint

Features:
  - In-memory LRU cache (avoid re-embedding identical text)
  - Filesystem cache (persistence across restarts)
  - Cosine similarity utility
  - Auto-detects NVIDIA vs local format

The client will automatically drop NVIDIA-specific fields (Authorization + input_type)
when EMBED_API_URL does not look like NVIDIA.
"""

import asyncio
import hashlib
import json
import math
from pathlib import Path
from typing import Optional

import httpx

from config.settings import (
    EMBED_API_URL,
    EMBED_CACHE_MAX,
    EMBEDDINGS_DIR,
    EMBED_MODEL,
    NVIDIA_API_KEY,
)


# ── In-memory LRU cache ───────────────────────────────────────────────

_cache: dict[str, list[float]] = {}
_cache_lock = asyncio.Lock()


def _key(text: str, model: str = "") -> str:
    # Namespace by model (and text) so vectors from a different embedder/dimension
    # are never reused for the wrong model. Prevents silent semantic corruption
    # when switching embedders (e.g. NIM vs local, or different dimensions).
    return hashlib.sha256((model + "\x00" + text).encode("utf-8")).hexdigest()


async def _cache_get(key: str) -> Optional[list[float]]:
    async with _cache_lock:
        return _cache.get(key)


async def _cache_set(key: str, vec: list[float]) -> None:
    async with _cache_lock:
        if len(_cache) >= EMBED_CACHE_MAX:
            victims = list(_cache.keys())[: EMBED_CACHE_MAX // 4]
            for v in victims:
                del _cache[v]
        _cache[key] = vec


# ── Filesystem cache ──────────────────────────────────────────────────

def _fs_path(key: str) -> Path:
    return EMBEDDINGS_DIR / f"{key[:16]}.json"


async def _fs_get(key: str) -> Optional[list[float]]:
    path = _fs_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("vec")
    except Exception:
        return None


async def _fs_set(key: str, vec: list[float]) -> None:
    path = _fs_path(key)
    try:
        path.write_text(json.dumps({"vec": vec}), encoding="utf-8")
    except Exception:
        pass  # cache write failure is non-fatal


# ── Public API ────────────────────────────────────────────────────────

async def get_embedding(
    text: str, client: httpx.AsyncClient, doc_type: str = "query"
) -> Optional[list[float]]:
    """
    Return embedding vector for text.
    Check memory cache → filesystem cache → endpoint (NIM or local).

    doc_type: "query" (for user input / retrieval queries) or "passage"
    (for stored content). E5-family models require asymmetric prefixes for
    best retrieval quality; using the same prefix for queries and passages
    degrades ranking.
    """
    key = _key(text, EMBED_MODEL)

    hit = await _cache_get(key)
    if hit is not None:
        return hit

    hit = await _fs_get(key)
    if hit is not None:
        await _cache_set(key, hit)
        return hit

    try:
        # Decide based on the embed endpoint URL itself.
        # Do not key off NVIDIA_API_KEY (which is usually present for chat/reflection).
        is_nvidia = "nvidia" in EMBED_API_URL.lower() or "integrate.api.nvidia.com" in EMBED_API_URL.lower()

        headers = {"Content-Type": "application/json"}
        if is_nvidia and NVIDIA_API_KEY:
            headers["Authorization"] = f"Bearer {NVIDIA_API_KEY}"

        payload = {"model": EMBED_MODEL, "input": text}

        if is_nvidia:
            payload["input_type"] = doc_type
        elif "e5" in EMBED_MODEL.lower():
            # E5 instruct models want asymmetric prefixes.
            # "query: " for retrieval queries; "passage: " for stored documents.
            prefix = "query" if doc_type == "query" else "passage"
            payload["input"] = f"{prefix}: {text}"

        resp = await client.post(
            EMBED_API_URL,
            json=payload,
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        vec = resp.json().get("data", [{}])[0].get("embedding")
        if vec:
            await _cache_set(key, vec)
            await _fs_set(key, vec)
        return vec
    except Exception as e:
        from utils.logger import log
        log("memory", "embedding_error", error=str(e))
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Standard cosine similarity between two vectors.
    Returns 0.0 (fail-safe) on dimension mismatch to avoid silent corruption
    when a stale vector from a previous embedder is served.
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0
