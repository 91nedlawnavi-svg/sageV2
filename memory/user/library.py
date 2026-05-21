"""
memory/user/library.py — User Library Memory

Stores distilled knowledge about entities in Elliot's world:
  - people Elliot mentions (friends, family, teachers)
  - places Elliot references
  - topics Elliot returns to (hobbies, projects, interests)

Each file is one entity — prose format, third person, updated not duplicated.

This is USER domain memory. Sage's knowledge of topics (from autonomous
search) goes into memory/sage/worldview.py.
"""

from pathlib import Path
from typing import Optional

from config.settings import USER_LIBRARY_DIR, LIBRARY_CATS
from memory.storage.base import (
    ensure_dirs,
    list_memory_files,
    read_memory_entry,
    safe_stem,
    write_text,
)


def _entry_path(category: str, name: str) -> Path:
    """Resolve the file path for a library entry."""
    return USER_LIBRARY_DIR / category / f"{safe_stem(name)}.txt"


async def load_library_entry(category: str, name: str) -> Optional[str]:
    """Read an existing library entry. Returns None if absent."""
    path = _entry_path(category, name)
    if not path.exists():
        return None
    return await read_memory_entry(path)


async def write_library_entry(category: str, name: str, content: str) -> None:
    """Write a library entry file."""
    ensure_dirs(USER_LIBRARY_DIR / category)
    path = _entry_path(category, name)
    await write_text(path, content.strip() + "\n")


async def load_all_library_entries() -> list[tuple[str, str]]:
    """
    Load all library entries as (label, content) pairs.
    label format: "people/friend_name", "topics/systems_thinking"
    Used by retrieval.
    """
    result = []
    for cat in LIBRARY_CATS:
        cat_dir = USER_LIBRARY_DIR / cat
        if not cat_dir.exists():
            continue
        for f in cat_dir.glob("*.txt"):
            content = await read_memory_entry(f)
            if content:
                result.append((f"library/{cat}/{f.stem}", content))
    return result


async def list_library_tree() -> dict[str, list[str]]:
    """Return {category: [name_stems]} for the UI library browser."""
    tree = {}
    for cat in LIBRARY_CATS:
        files = sorted((USER_LIBRARY_DIR / cat).glob("*.txt"))
        tree[cat] = [f.stem for f in files]
    return tree


async def delete_library_entry(category: str, name: str) -> bool:
    """Delete a library entry. Returns True if deleted."""
    path = _entry_path(category, name)
    if path.exists():
        path.unlink()
        return True
    return False
