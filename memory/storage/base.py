"""
memory/storage/base.py — Filesystem I/O Primitives

All disk operations go through here.
Single async lock prevents concurrent write corruption.

This is a direct preservation of V1's memory/storage.py primitives —
the low-level I/O has not been changed because it was correct and stable.
The only change: this module no longer holds chat-history helpers
(those moved to memory/storage/history.py) to keep single-responsibility.
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

_file_lock = asyncio.Lock()


# ── Low-level I/O ─────────────────────────────────────────────────────

async def read_text(path: Path) -> str:
    """Read a text file. Returns '' on missing or error."""
    async with _file_lock:
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""


async def write_text(path: Path, content: str) -> None:
    """Overwrite a file atomically (write to .tmp then rename)."""
    async with _file_lock:
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise


async def append_text(path: Path, line: str) -> None:
    """Append a line to a file."""
    async with _file_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


def ensure_dirs(*dirs: Path) -> None:
    """Create directories if missing."""
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def safe_stem(name: str) -> str:
    """Convert a name to a safe filesystem stem."""
    return "".join(
        c if (c.isalnum() or c in "-_") else "_"
        for c in name.lower()
    ).strip("_")


# ── Timestamped memory files ──────────────────────────────────────────

def ts_filename(prefix: str = "") -> str:
    """Generate a timestamp-based filename stem."""
    return f"{prefix}{datetime.now().strftime('%Y%m%d_%H%M%S')}"


async def write_memory_entry(directory: Path, stem: str, content: str) -> Path:
    """Write a single memory entry file."""
    path = directory / f"{stem}.txt"
    await write_text(path, content)
    return path


async def list_memory_files(directory: Path) -> list[Path]:
    """List all .txt files in a memory directory, sorted by name."""
    if not directory.exists():
        return []
    return sorted(directory.glob("*.txt"))


async def read_memory_entry(path: Path) -> Optional[str]:
    """Read one memory file. Returns None if missing or empty."""
    content = await read_text(path)
    return content if content.strip() else None
