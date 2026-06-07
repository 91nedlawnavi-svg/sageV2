"""
launch.py — Sage Server Entry Point

Boots the FastAPI server and wires all subsystems together.

V1's launch.py was a 500-line monolith containing: route logic, session
globals, daemon threading, prompt building, and inference calls all
in one file. Sage's launch.py is a thin orchestrator — it creates the
shared objects and injects them into the modules that own the logic.

Boot sequence:
  1. Run bootstrap (create dirs, load directive)
  2. Create shared objects: JobStore, ConversationSession, AsyncClient
  3. Inject dependencies into API route modules
  4. Register routes on the FastAPI app
  5. Start the reflection daemon as an asyncio task
  6. Serve static frontend from /frontend
  7. Start uvicorn

The only global state here is the app instance. Everything else is
injected, not imported as a global.
"""

import asyncio
import sys
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.chat import router as chat_router, init_routes as init_chat
from backend.api.history import router as history_router
from backend.api.memory import router as memory_router, init_memory_routes
from backend.api.search import router as search_router, init_search_routes
from backend.api.directive import router as directive_router
from backend.api.admin import router as admin_router, init_admin_routes
from backend.monitoring.metrics import AdminMetrics
from backend.orchestration.event_bus import clear_subscriptions
from backend.orchestration.job_store import JobStore
from backend.orchestration.session import ConversationSession
from config.settings import PORT
from daemon.reflection_daemon import ReflectionDaemon
from utils.bootstrap import bootstrap
from utils.logger import log, set_error_hook


# ── FastAPI app ───────────────────────────────────────────────────────

app = FastAPI(title="Sage", version="2.0", docs_url=None)

# Module-level references for shutdown handler
_client:  httpx.AsyncClient | None = None
_daemon:  ReflectionDaemon  | None = None
_metrics: AdminMetrics      | None = None


# ── Startup ───────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    global _client, _daemon, _metrics

    log("bootstrap", "startup_begin")

    # 1. Bootstrap: dirs, directive
    directive, client = await bootstrap()
    _client = client

    # 2. Shared runtime objects
    job_store = JobStore()
    session   = ConversationSession()
    _metrics  = AdminMetrics()

    # 3. Wire logger error hook
    set_error_hook(lambda subsystem: _metrics.record_error(subsystem))

    # 4. Inject into route modules
    init_chat(
        job_store=job_store,
        session=session,
        client=client,
    )
    init_memory_routes(
        session=session,
        daemon=None,       # filled in after daemon is created below
    )
    init_search_routes(client=client)
    init_admin_routes(metrics=_metrics, daemon=None)

    # 5. Start daemon
    _daemon = ReflectionDaemon(session=session, client=client, metrics=_metrics)
    await _daemon.start()

    # Now that daemon exists, back-fill the references
    init_memory_routes(session=session, daemon=_daemon)
    init_admin_routes(metrics=_metrics, daemon=_daemon)

    log("bootstrap", "startup_complete", port=PORT)
    print(f"\n✦ Sage running on http://localhost:{PORT}\n")


@app.on_event("shutdown")
async def shutdown():
    global _client, _daemon
    if _daemon:
        await _daemon.stop()
    if _client:
        await _client.aclose()
    clear_subscriptions()
    log("bootstrap", "shutdown_complete")


# ── Routes ────────────────────────────────────────────────────────────

app.include_router(chat_router)
app.include_router(history_router)
app.include_router(memory_router)
app.include_router(search_router)
app.include_router(directive_router)
app.include_router(admin_router)

# ── Admin metrics middleware ────────────────────────────────────────

_ADMIN_PREFIXES = ("/api/admin", "/static")

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    path = request.url.path
    is_admin = any(path.startswith(p) for p in _ADMIN_PREFIXES)

    t0 = time.time()
    try:
        response = await call_next(request)
        if _metrics and not is_admin:
            _metrics.record_api_latency(
                request.method,
                request.url.path,
                round((time.time() - t0) * 1000, 1),
            )
            if response.status_code >= 400:
                _metrics.record_api_error(request.method, request.url.path)
        return response
    except Exception:
        if _metrics and not is_admin:
            _metrics.record_api_error(request.method, request.url.path)
        raise


# ── Frontend static files ─────────────────────────────────────────────

_frontend_dir = Path(__file__).parent / "frontend"

if _frontend_dir.exists():
    @app.get("/")
    async def serve_index():
        return FileResponse(_frontend_dir / "index.html")

    app.mount("/static", StaticFiles(directory=str(_frontend_dir)), name="static")
else:
    @app.get("/")
    async def no_frontend():
        return JSONResponse({"error": "Frontend not found. Build it first."}, status_code=404)


# ── Entry ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "launch:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="warning",   # suppress uvicorn noise; Sage's logger handles events
    )
