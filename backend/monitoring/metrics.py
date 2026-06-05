"""
backend/monitoring/metrics.py — Admin-facing runtime metrics

Ring-buffer metrics collector. Singleton injected at boot.
All data is in-memory and resets on server restart.
"""

import time
from collections import deque
from typing import Any


class AdminMetrics:
    def __init__(self):
        self.server_start_ts = time.time()
        self.daemon_cycles: deque[dict] = deque(maxlen=50)
        self.error_counts: dict[str, int] = {}
        self.api_latencies: deque[tuple] = deque(maxlen=200)
        self.inference_latencies: deque[tuple] = deque(maxlen=100)
        self.endpoint_error_counts: dict[str, int] = {}
        self.total_requests = 0

    # ── Recorders ─────────────────────────────────────────────────

    def record_daemon_cycle(self, result: dict) -> None:
        self.daemon_cycles.append({
            "ts": time.time(),
            **result,
        })

    def record_error(self, subsystem: str) -> None:
        if subsystem not in self.error_counts:
            self.error_counts[subsystem] = 0
        self.error_counts[subsystem] += 1

    def record_api_latency(self, method: str, path: str, ms: float) -> None:
        self.api_latencies.append((method, path, ms))
        self.total_requests += 1

    def record_api_error(self, method: str, path: str) -> None:
        key = f"{method} {path}"
        if key not in self.endpoint_error_counts:
            self.endpoint_error_counts[key] = 0
        self.endpoint_error_counts[key] += 1

    def record_inference(self, model: str, ms: float, success: bool) -> None:
        self.inference_latencies.append((model, ms, success))

    # ── Snapshot ──────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        latencies = [ms for _, _, ms in self.api_latencies] if self.api_latencies else [0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        total_errors = sum(self.error_counts.values())

        return {
            "uptime_seconds": round(time.time() - self.server_start_ts, 1),
            "total_requests": self.total_requests,
            "avg_api_latency_ms": round(avg_latency, 1),
            "total_errors": total_errors,
            "daemon_cycles_run": len(self.daemon_cycles),
            "error_by_subsystem": dict(self.error_counts),
            "daemon_last_run": self.daemon_cycles[-1]["ts"] if self.daemon_cycles else None,
            # PHASE 4: Thread observability in metrics snapshot
            "active_threads": self._get_active_thread_count(),
            "thread_snapshots": list(getattr(self, 'thread_snapshots', []))[-5:],  # last few
        }

    def _get_active_thread_count(self) -> int:
        try:
            from cognition.threads.store import get_active_threads
            return len(get_active_threads())
        except Exception:
            return 0

    def record_thread_snapshot(self, active_count: int, total_count: int) -> None:
        """PHASE 4: Record thread state for observability."""
        if not hasattr(self, 'thread_snapshots'):
            self.thread_snapshots = deque(maxlen=20)
        self.thread_snapshots.append({
            "ts": time.time(),
            "active": active_count,
            "total": total_count,
        })
