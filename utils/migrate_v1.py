"""
utils/migrate_v1.py — V1 → V2 Memory Migration

Imports all V1 memory files into the V2 user-domain memory directories.
Run once, manually, after installing V2:

    cd ~/sageV2 && python utils/migrate_v1.py

What migrates:
  V1 ~/sage/episodic/*.txt  → V2 USER_EPISODIC_DIR/*.txt
  V1 ~/sage/emotional/*.txt → V2 USER_EMOTIONAL_DIR/*.txt
  V1 ~/sage/library/        → V2 USER_LIBRARY_DIR/
  V1 ~/sage/reflections/    → V2 USER_REFLECTIONS_DIR/

What does NOT migrate:
  - Chat history (incompatible format changes; start fresh or copy manually)
  - V1 embeddings (hash keys are unchanged; they will be reused automatically)
  - V1 directive.txt → copy manually to ~/sage_data_v2/directive.txt

The migration is additive — existing V2 files are never overwritten.
Run it multiple times safely.

Safety: V1 source files are never deleted or modified.
"""

import shutil
import sys
from pathlib import Path


# V1 source root (default install path)
V1_ROOT = Path.home() / "sage"

# V2 import destinations
# Import these at runtime so they resolve against the actual config
from config.settings import (
    USER_EPISODIC_DIR,
    USER_EMOTIONAL_DIR,
    USER_REFLECTIONS_DIR,
    USER_LIBRARY_DIR,
    EMBEDDINGS_DIR,
    LIBRARY_CATS,
)


def _copy_dir(src: Path, dst: Path, label: str) -> int:
    """Copy all .txt files from src to dst (skip existing). Returns count copied."""
    if not src.exists():
        print(f"  [skip] {label}: source not found ({src})")
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in src.glob("*.txt"):
        target = dst / f.name
        if not target.exists():
            shutil.copy2(f, target)
            count += 1
    return count


def _copy_library(v1_lib: Path, v2_lib: Path) -> int:
    """Copy library category subdirectories."""
    total = 0
    for cat in LIBRARY_CATS:
        src = v1_lib / cat
        dst = v2_lib / cat
        n = _copy_dir(src, dst, f"library/{cat}")
        print(f"  library/{cat}: {n} files copied")
        total += n
    return total


def _copy_embeddings(v1_emb: Path, v2_emb: Path) -> int:
    """Copy embedding cache files (*.json) from V1."""
    if not v1_emb.exists():
        print(f"  [skip] embeddings: source not found ({v1_emb})")
        return 0
    v2_emb.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in v1_emb.glob("*.json"):
        target = v2_emb / f.name
        if not target.exists():
            shutil.copy2(f, target)
            count += 1
    return count


def main():
    if not V1_ROOT.exists():
        print(f"V1 root not found at {V1_ROOT}. Nothing to migrate.")
        sys.exit(0)

    print(f"\n=== Sage V1 → V2 Migration ===")
    print(f"  Source:      {V1_ROOT}")
    print(f"  Destination: {USER_EPISODIC_DIR.parent.parent}\n")

    n_ep  = _copy_dir(V1_ROOT / "episodic",    USER_EPISODIC_DIR,    "episodic")
    n_em  = _copy_dir(V1_ROOT / "emotional",   USER_EMOTIONAL_DIR,   "emotional")
    n_ref = _copy_dir(V1_ROOT / "reflections", USER_REFLECTIONS_DIR, "reflections")
    n_lib = _copy_library(V1_ROOT / "library", USER_LIBRARY_DIR)
    n_emb = _copy_embeddings(V1_ROOT / "embeddings", EMBEDDINGS_DIR)

    print(f"\n  episodic:    {n_ep}  files copied")
    print(f"  emotional:   {n_em}  files copied")
    print(f"  reflections: {n_ref} files copied")
    print(f"  library:     {n_lib} files copied (total)")
    print(f"  embeddings:  {n_emb} files copied")

    total = n_ep + n_em + n_ref + n_lib + n_emb
    print(f"\n  Total: {total} files migrated.\n")

    print("Next steps:")
    print("  1. Copy your directive:  cp ~/sage/directive.txt ~/sage_data_v2/directive.txt")
    print("  2. Start V2:             cd ~/sageV2 && python launch.py")
    print("  3. V1 source is untouched — keep it until V2 is stable.\n")


if __name__ == "__main__":
    main()
