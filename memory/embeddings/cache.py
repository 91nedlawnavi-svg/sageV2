"""
memory/embeddings/cache.py — Local Embedding with LRU + Filesystem Cache

Wraps the BGE-M3 embedding endpoint with:
  - In-memory LRU cache (avoid re-embedding identical text)
  - Filesystem cache (persistence across restarts)
  - Cosine similarity utility

Preserved from V1's memory/embeddings.py — no behavior change.
Only the import paths for config have been updated.
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


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    text: str, client: httpx.AsyncClient
) -> Optional[list[float]]:
    """
    Return embedding vector for text.
    Check memory cache → filesystem cache → llama.cpp endpoint.
    """
    key = _key(text)

    hit = await _cache_get(key)
    if hit is not None:
        return hit

    hit = await _fs_get(key)
    if hit is not None:
        await _cache_set(key, hit)
        return hit

    try:
        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Content-Type": "application/json",
        }
        
        resp = await client.post(
            EMBED_API_URL,
            json={"model": EMBED_MODEL, "input": text, "input_type": "query"},
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
    """Standard cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0
