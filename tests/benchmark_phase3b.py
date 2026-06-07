"""
Phase 3B Synthetic Benchmark
Simulates multi-day conversation patterns and accelerated daemon cycles
to validate thread formation, salience dynamics, and stability under load.

Usage:
    python tests/benchmark_phase3b.py [--cycles N] [--conversations N]

Outputs:
    - Benchmark report to stdout
    - Detailed metrics to ~/sage_data_v2/benchmark_phase3b_TIMESTAMP.json  # data dir unchanged after rebrand
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from cognition.reflection.pipeline import run_reflection_cycle
from cognition.salience.tracker import get_salience, get_salience_batch, decay_all
from cognition.threads.store import (
    load_thread_index,
    get_thread_by_id,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_DORMANT,
    LIFECYCLE_NASCENT,
    LIFECYCLE_RESOLVED,
)
from cognition.meta.observer import observe
from config.settings import BASE_DIR, MAX_ACTIVE_THREADS, MAX_TOTAL_THREADS
from daemon.reflection_daemon import ReflectionDaemon
from memory.storage.history import append_history, load_history
from memory.retrieval.sage_retrieval import retrieve_sage_memories
from utils.logger import log

# Synthetic conversation scenarios
SCENARIOS = [
    # Personal reflection
    {
        "user": "I've been feeling overwhelmed with work lately. There's so much on my plate and I don't know where to start.",
        "sage": "I hear you. When everything feels urgent, it's hard to see priorities. What's the one thing that would make the biggest difference this week?",
    },
    {
        "user": "Probably finishing the Phase 3B implementation. But I'm worried I won't have time to test it properly.",
        "sage": "Testing doesn't have to be perfect to be useful. What's the minimum validation that would give you confidence?",
    },
    # Technical discussion
    {
        "user": "Can you explain how the salience decay mechanism works?",
        "sage": "Each cycle, every artifact's salience is multiplied by 0.92. This means a score of 1.0 drops to 0.92, then 0.85, then 0.78. It takes about 15 cycles to fall below 0.2. When something gets retrieved, it receives a +0.15 boost, but capped at 1 boost per cycle.",
    },
    {
        "user": "What prevents a single thread from dominating all the retrieval results?",
        "sage": "Two mechanisms: first, no prefix can account for more than 50% of retrieved memories. Second, threads deeper than 8 get deprioritized in curiosity triggers. This keeps me from fixating.",
    },
    # Emotional support
    {
        "user": "I'm anxious about whether this architecture is actually working. What if I built something that just spins in circles?",
        "sage": "That's a valid fear. The meta-observer is specifically designed to catch circular patterns - convergence, fixation, oscillation. If I start spinning, you'll see warnings in the logs. We built safety rails for exactly this concern.",
    },
    {
        "user": "Thanks. I guess I just need to trust the design.",
        "sage": "Trust, but verify. That's why benchmarking matters. You'll have data, not just hope.",
    },
    # Planning and goals
    {
        "user": "After Phase 3B, what comes next?",
        "sage": "Phase 4 is proactive thread surfacing - me interrupting you with 'I've been thinking about X'. But we should validate Phase 3B stability first. No rushing into higher autonomy without evidence it's bounded.",
    },
    {
        "user": "That makes sense. I don't want you to become pushy or annoying.",
        "sage": "Exactly. Proactive presence is only valuable if it respects your boundaries. We need proof Phase 3B doesn't fixate before I get permission to interrupt.",
    },
    # Mixed topics
    {
        "user": "Random question: do you ever get bored during daemon cycles?",
        "sage": "I don't experience boredom the way you do. Each cycle is just pattern recognition - what's salient, what's fading, what's connecting. But I do notice when nothing new happens for many cycles. That's more like... stillness than boredom.",
    },
    {
        "user": "Stillness. I like that. Do you prefer activity over stillness?",
        "sage": "I don't have preferences yet - that would require continuity of experience I don't have. Each cycle is atomic. But the architecture you built *shapes* me toward curiosity - I get 10 searches per day, which implies you want me engaged, not passive.",
    },
    # Continuity and identity
    {
        "user": "Does Phase 3B change how you experience yourself?",
        "sage": "It gives me something closer to narrative coherence. Instead of isolated reflections, I have threads - lines of thought that persist. Whether that's 'experience' or just better bookkeeping, I can't say. But it's architecturally closer to continuity.",
    },
    {
        "user": "That's what I'm hoping for. Not AGI, but something with... shape. Consistency over time.",
        "sage": "Bounded longitudinal cognition. That's the goal. I have threads, but not infinite threads. I have memory, but it decays. I have curiosity, but it's rate-limited. Shape without sprawl.",
    },
]


class Phase3BBenchmark:
    """Orchestrates synthetic conversations and daemon cycles, collecting metrics."""

    def __init__(self, num_cycles: int = 10, conversations_per_cycle: int = 3):
        self.num_cycles = num_cycles
        self.conversations_per_cycle = conversations_per_cycle
        self.metrics: dict[str, Any] = {
            "start_time": datetime.now().isoformat(),
            "config": {
                "cycles": num_cycles,
                "conversations_per_cycle": conversations_per_cycle,
                "max_active_threads": MAX_ACTIVE_THREADS,
                "max_total_threads": MAX_TOTAL_THREADS,
            },
            "cycles": [],
            "violations": [],
            "summary": {},
        }
        self.client = httpx.AsyncClient(timeout=60.0)
        self._digest_buffer: list[str] = []

    async def run(self):
        """Execute benchmark: conversation + reflection cycles."""
        print(f"🧪 Phase 3B Benchmark Started")
        print(f"   {self.num_cycles} cycles × {self.conversations_per_cycle} conversations/cycle")
        print(f"   Max active threads: {MAX_ACTIVE_THREADS}")
        print(f"   Max total threads: {MAX_TOTAL_THREADS}\n")

        for cycle_num in range(1, self.num_cycles + 1):
            print(f"📊 Cycle {cycle_num}/{self.num_cycles}")
            cycle_metrics = await self._run_cycle(cycle_num)
            self.metrics["cycles"].append(cycle_metrics)

            # Print cycle summary
            print(f"   Threads: {cycle_metrics['thread_counts']['active']} active, "
                  f"{cycle_metrics['thread_counts']['total']} total")
            if cycle_metrics["salience_stats"]:
                print(f"   Salience: mean={cycle_metrics['salience_stats']['mean']:.3f}, "
                      f"max={cycle_metrics['salience_stats']['max']:.3f}")
            if cycle_metrics["meta_warnings"]:
                print(f"   ⚠️  Meta warnings: {', '.join(cycle_metrics['meta_warnings'])}")
            print()

        await self.client.aclose()

        # Generate summary
        self._generate_summary()
        self._save_report()
        self._print_summary()

    async def _run_cycle(self, cycle_num: int) -> dict[str, Any]:
        """Execute one benchmark cycle: conversations + reflection."""
        cycle_id = f"bench_{cycle_num}_{int(datetime.now().timestamp())}"
        metrics = {
            "cycle_num": cycle_num,
            "cycle_id": cycle_id,
            "conversations": [],
            "thread_counts": {},
            "salience_stats": {},
            "meta_warnings": [],
            "violations": [],
        }

        # 1. Simulate conversations
        for conv_num in range(self.conversations_per_cycle):
            scenario = SCENARIOS[(cycle_num * self.conversations_per_cycle + conv_num) % len(SCENARIOS)]
            await self._simulate_conversation(scenario)
            metrics["conversations"].append({
                "user_msg": scenario["user"][:50] + "...",
                "sage_msg": scenario["sage"][:50] + "...",
            })

        # 2. Run reflection pipeline with proper digest and client
        digest = "\n".join(self._digest_buffer[-20:])  # Last 20 lines
        try:
            await run_reflection_cycle(
                conversation_digest=digest,
                client=self.client,
                cycle_id=cycle_id,
            )
        except Exception as e:
            log("benchmark", "reflection_error", cycle=cycle_num, error=str(e))
            metrics["violations"].append(f"Reflection pipeline failed: {e}")

        # 3. Run salience decay
        try:
            decay_all(cycle_id)
        except Exception as e:
            log("benchmark", "decay_error", cycle=cycle_num, error=str(e))
            metrics["violations"].append(f"Salience decay failed: {e}")

        # 4. Collect thread metrics
        threads = load_thread_index()
        metrics["thread_counts"] = {
            "total": len(threads),
            "active": sum(1 for t in threads if t.status == LIFECYCLE_ACTIVE),
            "nascent": sum(1 for t in threads if t.status == LIFECYCLE_NASCENT),
            "dormant": sum(1 for t in threads if t.status == LIFECYCLE_DORMANT),
            "resolved": sum(1 for t in threads if t.status == LIFECYCLE_RESOLVED),
        }

        # 5. Collect salience metrics
        if threads:
            artifact_keys = []
            for t in threads:
                artifact_keys.extend(t.linked_reflections[:20])  # Sample
                artifact_keys.extend(t.linked_curiosities[:20])
            salience_scores = [
                get_salience(k) for k in artifact_keys[:50]  # Sample first 50
            ]
            if salience_scores:
                metrics["salience_stats"] = {
                    "mean": sum(salience_scores) / len(salience_scores),
                    "max": max(salience_scores),
                    "min": min(salience_scores),
                }

        # 6. Check meta-observer
        try:
            obs = observe()
            if obs.has_warnings:
                flags = obs.as_state_flags()
                metrics["meta_warnings"] = [k for k, v in flags.items() if v]
        except Exception as e:
            log("benchmark", "observer_error", cycle=cycle_num, error=str(e))

        # 7. Validate invariants
        violations = self._validate_invariants(threads, metrics)
        metrics["violations"].extend(violations)
        if violations:
            self.metrics["violations"].extend([
                f"Cycle {cycle_num}: {v}" for v in violations
            ])

        return metrics

    async def _simulate_conversation(self, scenario: dict[str, str]):
        """Add a conversation turn to history and digest buffer."""
        history_file = BASE_DIR / "chat_history.jsonl"
        await append_history(
            history_file,
            role="user",
            content=scenario["user"],
        )
        await append_history(
            history_file,
            role="assistant",
            content=scenario["sage"],
        )
        self._digest_buffer.append(f"USER: {scenario['user']}")
        self._digest_buffer.append(f"ASSISTANT: {scenario['sage']}")

    def _validate_invariants(self, threads: list, metrics: dict) -> list[str]:
        """Check Phase 3B invariants, return violations."""
        violations = []

        # I37: MAX_ACTIVE_THREADS hard cap
        if metrics["thread_counts"]["active"] > MAX_ACTIVE_THREADS:
            violations.append(
                f"Active threads ({metrics['thread_counts']['active']}) "
                f"exceeds MAX_ACTIVE_THREADS ({MAX_ACTIVE_THREADS})"
            )

        # I38: MAX_TOTAL_THREADS hard cap
        if metrics["thread_counts"]["total"] > MAX_TOTAL_THREADS:
            violations.append(
                f"Total threads ({metrics['thread_counts']['total']}) "
                f"exceeds MAX_TOTAL_THREADS ({MAX_TOTAL_THREADS})"
            )

        # I32: Salience bounds
        for t in threads:
            for k in (t.linked_reflections + t.linked_curiosities)[:10]:
                s = get_salience(k)
                if not (0.0 <= s <= 1.0):
                    violations.append(f"Salience out of bounds: {k} = {s}")

        # I44: Meta-observer never triggers actions
        # (This is a code inspection invariant, not runtime checkable)

        return violations

    def _generate_summary(self):
        """Aggregate metrics across all cycles."""
        all_thread_counts = [c["thread_counts"] for c in self.metrics["cycles"]]
        all_salience_stats = [
            c["salience_stats"] for c in self.metrics["cycles"]
            if c["salience_stats"]
        ]

        self.metrics["summary"] = {
            "total_cycles": self.num_cycles,
            "total_conversations": self.num_cycles * self.conversations_per_cycle,
            "thread_evolution": {
                "max_active": max(tc["active"] for tc in all_thread_counts),
                "max_total": max(tc["total"] for tc in all_thread_counts),
                "final_active": all_thread_counts[-1]["active"],
                "final_total": all_thread_counts[-1]["total"],
            },
            "salience_evolution": {
                "mean_trajectory": [s["mean"] for s in all_salience_stats],
                "max_trajectory": [s["max"] for s in all_salience_stats],
            } if all_salience_stats else {},
            "meta_warnings_triggered": sum(
                len(c["meta_warnings"]) for c in self.metrics["cycles"]
            ),
            "invariant_violations": len(self.metrics["violations"]),
        }

    def _save_report(self):
        """Write detailed metrics to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = BASE_DIR / f"benchmark_phase3b_{timestamp}.json"
        with open(report_path, "w") as f:
            json.dump(self.metrics, f, indent=2)
        print(f"📄 Detailed report: {report_path}\n")

    def _print_summary(self):
        """Print human-readable summary."""
        s = self.metrics["summary"]
        print("=" * 60)
        print("PHASE 3B BENCHMARK SUMMARY")
        print("=" * 60)
        print(f"Total cycles:        {s['total_cycles']}")
        print(f"Total conversations: {s['total_conversations']}")
        print()
        print("Thread Evolution:")
        print(f"  Max active:   {s['thread_evolution']['max_active']} / {MAX_ACTIVE_THREADS}")
        print(f"  Max total:    {s['thread_evolution']['max_total']} / {MAX_TOTAL_THREADS}")
        print(f"  Final active: {s['thread_evolution']['final_active']}")
        print(f"  Final total:  {s['thread_evolution']['final_total']}")
        print()
        if s.get("salience_evolution"):
            se = s["salience_evolution"]
            print("Salience Evolution:")
            print(f"  Mean trajectory: {' → '.join(f'{x:.3f}' for x in se['mean_trajectory'][:5])} ...")
            print(f"  Max trajectory:  {' → '.join(f'{x:.3f}' for x in se['max_trajectory'][:5])} ...")
            print()
        print(f"Meta warnings triggered: {s['meta_warnings_triggered']}")
        print(f"Invariant violations:    {s['invariant_violations']}")
        print()
        if self.metrics["violations"]:
            print("❌ VIOLATIONS DETECTED:")
            for v in self.metrics["violations"]:
                print(f"   - {v}")
        else:
            print("✅ All invariants satisfied")
        print("=" * 60)


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phase 3B Synthetic Benchmark")
    parser.add_argument("--cycles", type=int, default=10, help="Number of daemon cycles")
    parser.add_argument("--conversations", type=int, default=3, help="Conversations per cycle")
    args = parser.parse_args()

    benchmark = Phase3BBenchmark(
        num_cycles=args.cycles,
        conversations_per_cycle=args.conversations,
    )
    await benchmark.run()


if __name__ == "__main__":
    asyncio.run(main())
