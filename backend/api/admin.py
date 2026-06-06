"""
backend/api/admin.py — Admin monitoring endpoints

Exposes runtime health, metrics, daemon history, errors, log tailing, and uptime.
All data comes from the injected AdminMetrics singleton plus on-demand health pings.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response

from backend.monitoring.metrics import AdminMetrics
from config.settings import (
    BASE_DIR,
    CHAT_API_URL,
    EMBED_API_URL,
    EMBED_MODEL,
    LOGS_DIR,
    NVIDIA_API_KEY,
)
from daemon.reflection_daemon import ReflectionDaemon

router = APIRouter(prefix="/api/admin", tags=["admin"])

_metrics: AdminMetrics | None = None
_daemon: ReflectionDaemon | None = None


def init_admin_routes(metrics: AdminMetrics, daemon: ReflectionDaemon | None = None) -> None:
    global _metrics, _daemon
    _metrics = metrics
    _daemon = daemon


# ── Health ──────────────────────────────────────────────────────

@router.get("/health")
async def admin_health():
    checks = []

    # NIM chat endpoint
    t0 = time.time()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                CHAT_API_URL.replace("/chat/completions", "/models"),
                headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                timeout=10.0,
            )
            ok = resp.status_code < 500
        checks.append({
            "name": "NVIDIA NIM API",
            "ok": ok,
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "error": None if ok else f"HTTP {resp.status_code}",
        })
    except Exception as e:
        checks.append({
            "name": "NVIDIA NIM API",
            "ok": False,
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "error": str(e),
        })

    # SearXNG
    t0 = time.time()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8080", timeout=5.0)
        ok = resp.status_code == 200
        checks.append({
            "name": "SearXNG",
            "ok": ok,
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "error": None if ok else f"HTTP {resp.status_code}",
        })
    except Exception as e:
        checks.append({
            "name": "SearXNG",
            "ok": False,
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "error": str(e),
        })

    # Filesystem
    try:
        test_file = BASE_DIR / ".admin_health_check"
        test_file.write_text("ok")
        test_file.unlink()
        checks.append({"name": "Filesystem", "ok": True, "latency_ms": None, "error": None})
    except Exception as e:
        checks.append({"name": "Filesystem", "ok": False, "latency_ms": None, "error": str(e)})

    # Daemon
    checks.append({
        "name": "Reflection Daemon",
        "ok": _daemon.is_running if _daemon else False,
        "latency_ms": None,
        "error": None if (_daemon and _daemon.is_running) else "daemon stopped",
    })

    # Disk usage
    try:
        stat = os.statvfs(BASE_DIR)
        total_gb = round((stat.f_frsize * stat.f_blocks) / (1024**3), 1)
        free_gb = round((stat.f_frsize * stat.f_bavail) / (1024**3), 1)
        used_pct = round((1 - free_gb / total_gb) * 100, 1) if total_gb > 0 else 0
        disk = {"total_gb": total_gb, "free_gb": free_gb, "used_pct": used_pct}
    except Exception:
        disk = None

    # Embedding health
    # For local llama.cpp / OpenAI-compatible (current default): perform a minimal real embedding call.
    # This validates the exact endpoint, payload formatting (incl. e5 prefixes), and that vectors are returned.
    # For NVIDIA embedders: keep the lightweight catalog check to avoid spend.
    t0 = time.time()
    try:
        async with httpx.AsyncClient() as client:
            is_nvidia = "nvidia" in EMBED_API_URL.lower() or bool(NVIDIA_API_KEY)

            if is_nvidia:
                # Legacy / optional NIM path for embeddings — catalog check (cheap)
                resp = await client.get(
                    "https://integrate.api.nvidia.com/v1/models",
                    headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    models = resp.json().get("data", [])
                    found = any(m.get("id") == EMBED_MODEL for m in models)
                    ok = found
                    err = None if ok else "model not found"
                else:
                    ok = False
                    err = f"HTTP {resp.status_code}"
            else:
                # Local embedder (e.g. http://127.0.0.1:8081/v1/embeddings)
                # Use the same prefix logic the app uses for e5 models.
                payload = {"model": EMBED_MODEL, "input": "health"}
                if "e5" in EMBED_MODEL.lower():
                    payload["input"] = "query: health"

                resp = await client.post(
                    EMBED_API_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=15.0,
                )
                try:
                    data = resp.json() if resp.status_code < 500 else {}
                except Exception:
                    data = {}
                ok = resp.status_code == 200 and bool(data.get("data"))
                err = None if ok else ("no embedding data" if resp.status_code == 200 else f"HTTP {resp.status_code}")

        checks.append({
            "name": f"Embedding ({EMBED_MODEL})",
            "ok": ok,
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "error": err,
        })
    except Exception as e:
        checks.append({
            "name": f"Embedding ({EMBED_MODEL})",
            "ok": False,
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "error": str(e),
        })

    all_ok = all(c["ok"] for c in checks)
    status = "ok" if all_ok else "degraded"
    if not any(c["ok"] for c in checks):
        status = "down"

    return {"status": status, "checks": checks, "disk": disk}


# ── Metrics ─────────────────────────────────────────────────────

@router.get("/metrics")
async def admin_metrics():
    if not _metrics:
        raise HTTPException(503, "Metrics not initialized")
    snap = _metrics.snapshot()
    # PHASE 4: Include current thread observability
    try:
        from cognition.threads.store import get_active_threads, load_thread_index
        snap["threads"] = {
            "active": len(get_active_threads()),
            "total": len(load_thread_index()),
        }
    except Exception:
        snap["threads"] = {"active": 0, "total": 0}
    return snap


# ── Daemon history ───────────────────────────────────────────────

@router.get("/daemon/history")
async def admin_daemon_history():
    if not _metrics:
        raise HTTPException(503, "Metrics not initialized")
    return {"cycles": list(_metrics.daemon_cycles)}


# ── Errors ───────────────────────────────────────────────────────

@router.get("/errors")
async def admin_errors():
    if not _metrics:
        raise HTTPException(503, "Metrics not initialized")
    return {
        "by_subsystem": dict(_metrics.error_counts),
        "by_endpoint": dict(_metrics.endpoint_error_counts),
    }


# ── Log tail ─────────────────────────────────────────────────────

@router.get("/logs/tail")
async def admin_log_tail(
    lines: int = Query(default=50, ge=1, le=500),
    since: str = Query(default=""),
):
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = LOGS_DIR / f"sage.{date_str}.jsonl"

    if not log_path.exists():
        return {"lines": [], "fingerprint": None}

    try:
        # Seek-based read from end — avoid O(n) full-file scan
        entries = []
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            buffer_size = lines * 512
            start_pos = max(0, file_size - buffer_size)
            f.seek(start_pos)
            raw = f.read().decode("utf-8", errors="replace")
            raw_lines = raw.strip().split("\n")
            raw_lines = raw_lines[-lines:]
            for rl in raw_lines:
                try:
                    entries.append(json.loads(rl))
                except json.JSONDecodeError:
                    continue

        # Compute fingerprint from last entry for delta-polling
        fingerprint = None
        if entries:
            last = entries[-1]
            fingerprint = hashlib.sha256(
                json.dumps({"ts": last.get("ts"), "subsystem": last.get("subsystem"), "event": last.get("event")}, sort_keys=True).encode()
            ).hexdigest()

        # If client already has this fingerprint, return empty delta
        if since and since == fingerprint:
            return {"lines": [], "fingerprint": fingerprint, "unchanged": True}

        return {"lines": entries, "fingerprint": fingerprint, "unchanged": False}
    except Exception as e:
        return {"lines": [], "fingerprint": None, "error": str(e)}


# ── Uptime ────────────────────────────────────────────────────────

@router.get("/uptime")
async def admin_uptime():
    if not _metrics:
        raise HTTPException(503, "Metrics not initialized")
    return {
        "server_uptime_seconds": round(time.time() - _metrics.server_start_ts, 1),
        "server_start_ts": _metrics.server_start_ts,
    }
