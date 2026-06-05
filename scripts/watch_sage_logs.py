#!/usr/bin/env python3
"""
Sage V2 Live Log Observer

Watches the newest daily log in ~/sage_data_v2/logs/ and streams filtered events
that reveal the internal "mind" (daemon cycles, bounded threads & lifecycle,
autonomous searches with budget provenance, reflections, curiosities, salience,
worldview, meta warnings, prompt fingerprints, etc.).

This is the practical tool for observing the deeper truth of message processing
and Phase 4 systems in real time.

Usage (while server is running):
    python scripts/watch_sage_logs.py
    python scripts/watch_sage_logs.py --once          # dump recent interesting lines and exit
    python scripts/watch_sage_logs.py --filter "thread|lifecycle" 

The script survives log rotation by re-detecting the latest file.
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_LOG_DIR = Path.home() / "sage_data_v2" / "logs"
DEFAULT_FILTER = r'(daemon|cycle|thread|lifecycle|search|budget|reflection|curiosit|proactive|retrieval|prompt|salience|worldview|meta)'

def find_latest_log(log_dir: Path) -> Path | None:
    if not log_dir.exists():
        return None
    candidates = sorted(log_dir.glob("sage.*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None

def tail_follow(path: Path, pattern: re.Pattern):
    proc = subprocess.Popen(
        ["tail", "-n", "0", "-F", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1
    )
    try:
        for line in proc.stdout:
            if pattern.search(line):
                sys.stdout.write(line)
                sys.stdout.flush()
    finally:
        proc.terminate()

def main():
    ap = argparse.ArgumentParser(description="Sage V2 live log observer for internal state (threads, search budget, daemon cycles, etc.)")
    ap.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    ap.add_argument("--filter", default=DEFAULT_FILTER, help="regex for interesting lines")
    ap.add_argument("--once", action="store_true", help="print current matching tail and exit (no follow)")
    args = ap.parse_args()

    pat = re.compile(args.filter, re.I)

    log_dir = args.log_dir
    print(f"[sage-observe] monitoring {log_dir} (filter: {args.filter})", file=sys.stderr)

    last_path = None
    while True:
        current = find_latest_log(log_dir)
        if current is None:
            print("[sage-observe] no log files yet, waiting...", file=sys.stderr)
            time.sleep(2)
            continue

        if current != last_path:
            print(f"[sage-observe] now following {current.name}", file=sys.stderr)
            last_path = current

        if args.once:
            with open(current, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if pat.search(line):
                        print(line, end="")
            return

        try:
            tail_follow(current, pat)
        except KeyboardInterrupt:
            print("\n[sage-observe] stopped", file=sys.stderr)
            return
        except Exception as e:
            print(f"[sage-observe] tail error: {e}", file=sys.stderr)

        time.sleep(1)

if __name__ == "__main__":
    main()
