"""
index.py - Build and validate the docs/index.json flat index for dok-fu.

Scans all docs/*.md files, reads their YAML frontmatter, and emits a flat
JSON array of {path, tags, description} entries into docs/index.json.
Supports a --check mode that exits nonzero if the on-disk index is stale.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .common import load_config, read_frontmatter_file


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _iter_doc_files(docs_root: Path):
    """Yield all .md files under *docs_root* (recursive), skipping hidden files."""
    for p in sorted(docs_root.rglob("*.md")):
        # Skip hidden files/dirs (e.g. .dokfu-manifest)
        if any(part.startswith(".") for part in p.parts):
            continue
        yield p


def build_index(config: dict[str, Any], root: str | os.PathLike | None = None) -> list[dict[str, Any]]:
    """Scan all doc files and return a flat list of index entries.

    Each entry is ``{path: str, tags: list[str], description: str}``.
    Files with no frontmatter are included with empty tags and description.

    Args:
        config: Loaded dok-fu config dict.
        root: Project root. Falls back to config['_root'] then cwd.

    Returns:
        Sorted list of index entry dicts.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    docs_dir = config.get("docs_dir", "docs")
    docs_root = root / docs_dir

    entries: list[dict[str, Any]] = []
    if not docs_root.exists():
        return entries

    for doc_path in _iter_doc_files(docs_root):
        try:
            fm, _ = read_frontmatter_file(doc_path)
        except (ValueError, OSError):
            fm = {}

        rel = doc_path.relative_to(root).as_posix()
        entry: dict[str, Any] = {
            "path": rel,
            "tags": fm.get("tags") or [],
            "description": fm.get("description") or "",
        }
        entries.append(entry)

    return entries


def write_index(entries: list[dict[str, Any]], config: dict[str, Any], root: str | os.PathLike | None = None) -> Path:
    """Write *entries* to docs/index.json and return the written path.

    Args:
        entries: List of index entry dicts from :func:`build_index`.
        config: Loaded dok-fu config dict.
        root: Project root.

    Returns:
        Absolute Path of the written index file.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    docs_dir = config.get("docs_dir", "docs")
    index_path = root / docs_dir / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return index_path


def read_index(config: dict[str, Any], root: str | os.PathLike | None = None) -> list[dict[str, Any]]:
    """Read and return the current docs/index.json as a list of dicts.

    Returns an empty list if the file does not exist.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    docs_dir = config.get("docs_dir", "docs")
    index_path = root / docs_dir / "index.json"
    if not index_path.exists():
        return []
    return json.loads(index_path.read_text(encoding="utf-8"))


def is_index_stale(config: dict[str, Any], root: str | os.PathLike | None = None) -> bool:
    """Return True if docs/index.json is missing or does not match the current scan.

    Args:
        config: Loaded dok-fu config dict.
        root: Project root.
    """
    current = build_index(config, root=root)
    on_disk = read_index(config, root=root)
    return current != on_disk
