"""
tags.py - Tag registry operations and doc search for dok-fu.

Provides:
- load_registry(): load the controlled tag vocabulary
- list_tags(): return all known tags with explanations
- search_by_tag(): return doc paths that carry a given tag
- validate_tags(): check a list of tags against the registry
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .common import load_config, read_frontmatter_file


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def load_registry(config: dict[str, Any], root: str | os.PathLike | None = None) -> dict[str, str]:
    """Load and return the tag registry as a ``{tag: explanation}`` dict.

    Args:
        config: Loaded dok-fu config dict.
        root: Project root. Falls back to config['_root'] then cwd.

    Raises:
        FileNotFoundError: If the registry file does not exist.
        json.JSONDecodeError: If the registry file is not valid JSON.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    registry_path = root / config.get("registry_path", "config/tags.registry.json")
    if not registry_path.exists():
        raise FileNotFoundError(f"Tag registry not found: {registry_path}")
    return json.loads(registry_path.read_text(encoding="utf-8"))


def list_tags(config: dict[str, Any], root: str | os.PathLike | None = None) -> dict[str, str]:
    """Return the full tag registry as ``{tag: explanation}``.

    This is a direct alias for :func:`load_registry` exposed at the module
    level so CLI code can call ``list_tags()`` without caring about internals.
    """
    return load_registry(config, root=root)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_by_tag(
    tag: str,
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
    *,
    validate: bool = True,
) -> list[str]:
    """Return doc paths (root-relative posix strings) whose 'tags' list contains *tag*.

    Args:
        tag: The tag to search for.
        config: Loaded dok-fu config dict.
        root: Project root.
        validate: If True (default), raise :exc:`ValueError` when *tag* is not
            in the registry.  Set to False to search without validation.

    Returns:
        Sorted list of root-relative posix paths to matching doc files.

    Raises:
        ValueError: If *validate* is True and *tag* is not in the registry.
    """
    root = Path(root or config.get("_root") or Path.cwd())

    if validate:
        registry = load_registry(config, root=root)
        if tag not in registry:
            raise ValueError(
                f"Unknown tag '{tag}'. Run 'dokfu tags --list' to see valid tags."
            )

    docs_dir = config.get("docs_dir", "docs")
    docs_root = root / docs_dir
    matches: list[str] = []

    if not docs_root.exists():
        return matches

    for doc_path in sorted(docs_root.rglob("*.md")):
        if any(part.startswith(".") for part in doc_path.parts):
            continue
        try:
            fm, _ = read_frontmatter_file(doc_path)
        except (ValueError, OSError):
            continue
        doc_tags = fm.get("tags") or []
        if tag in doc_tags:
            matches.append(doc_path.relative_to(root).as_posix())

    return matches


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_tags(
    tags: list[str],
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
) -> list[str]:
    """Return a list of tags from *tags* that are NOT in the registry.

    Args:
        tags: List of tag strings to validate.
        config: Loaded dok-fu config dict.
        root: Project root.

    Returns:
        List of unknown tag strings (empty list if all tags are valid).
    """
    registry = load_registry(config, root=root)
    return [t for t in tags if t not in registry]
