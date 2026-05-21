"""
memory/storage/history.py — Chat History I/O

JSONL format: each line is {"role": "user"|"assistant", "content": "...", "ts": float}

Extracted from V1's memory/storage.py to keep single-responsibility.
Logic is identical — no behavior change, just cleaner module boundaries.
"""

import json
import time
from pathlib import Path

from memory.storage.base import append_text, _file_lock


async def load_history(history_file: Path) -> list[dict]:
    """Load JSONL chat history. Each line is {role, content, ts}."""
    try:
        raw = history_file.read_text(encoding="utf-8")
    except Exception:
        return []

    messages = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except Exception:
            pass
    return messages


async def append_history(history_file: Path, role: str, content: str) -> None:
    """Append one turn to the JSONL history file."""
    entry = json.dumps({"role": role, "content": content, "ts": time.time()})
    await append_text(history_file, entry + "\n")


async def strip_last_assistant(history_file: Path) -> bool:
    """
    Remove the last assistant entry from the JSONL history file.
    Called by retry to prevent duplicate consecutive assistant turns.
    Returns True if an entry was removed, False otherwise.
    """
    async with _file_lock:
        try:
            if not history_file.exists():
                return False
            lines = history_file.read_text(encoding="utf-8").splitlines(keepends=True)
            for i in range(len(lines) - 1, -1, -1):
                line = lines[i].strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if entry.get("role") == "assistant":
                    del lines[i]
                    tmp = history_file.with_suffix(".tmp")
                    tmp.write_text("".join(lines), encoding="utf-8")
                    tmp.replace(history_file)
                    return True
                break
            return False
        except Exception:
            return False


def history_for_prompt(history: list[dict], n: int) -> list[dict]:
    """Slice the last n*2 messages for prompt injection."""
    recent = history[-(n * 2):]
    return [{"role": m["role"], "content": m["content"]} for m in recent]
