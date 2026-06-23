"""
changes.py - Detect changed source files for dok-fu.

Strategy:
1. Primary: ``git diff --name-only <ref>`` to list changed files.
2. Fallback: compare current file SHA-256 hashes against a stored manifest
   (docs/.dokfu-manifest.json) when git is unavailable or the repo has no
   commits yet.

Provides:
- get_changed_files(): list changed source paths (git primary, manifest fallback)
- update_manifest(): write/update the SHA-256 manifest for all tracked sources
- read_manifest(): load the current manifest from disk
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .common import load_config, sha256_file, walk_sources


# ---------------------------------------------------------------------------
# Manifest read / write
# ---------------------------------------------------------------------------

def _manifest_path(config: dict[str, Any], root: Path) -> Path:
    return root / config.get("manifest_path", "docs/.dokfu-manifest.json")


def read_manifest(config: dict[str, Any], root: str | os.PathLike | None = None) -> dict[str, str]:
    """Load and return the SHA-256 manifest as ``{rel_posix_path: sha256hex}``.

    Returns an empty dict if the manifest file does not exist.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    mpath = _manifest_path(config, root)
    if not mpath.exists():
        return {}
    return json.loads(mpath.read_text(encoding="utf-8"))


def update_manifest(
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
    *,
    paths: list[Path] | None = None,
) -> dict[str, str]:
    """Compute and persist SHA-256 hashes for all tracked source files.

    Args:
        config: Loaded dok-fu config dict.
        root: Project root.
        paths: Explicit list of absolute source Paths to hash.  Defaults to
            all files returned by :func:`~common.walk_sources`.

    Returns:
        The newly written manifest dict.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    if paths is None:
        paths = list(walk_sources(config, root=root))

    manifest: dict[str, str] = {}
    for p in paths:
        rel = p.relative_to(root).as_posix()
        manifest[rel] = sha256_file(p)

    mpath = _manifest_path(config, root)
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


# ---------------------------------------------------------------------------
# Git-based change detection
# ---------------------------------------------------------------------------

def _git_changed_files(ref: str, root: Path) -> list[str] | None:
    """Run ``git diff --name-only <ref>`` and return a list of relative paths.

    Returns None if git is unavailable, the directory is not a git repo, or
    any other subprocess error occurs.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", ref],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _git_is_available(root: Path) -> bool:
    """Return True if git is available and *root* is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


# ---------------------------------------------------------------------------
# Manifest-based change detection
# ---------------------------------------------------------------------------

def _manifest_changed_files(
    config: dict[str, Any],
    root: Path,
) -> list[str]:
    """Compare current file hashes to the stored manifest.

    Returns root-relative posix paths of files that are new or have changed.
    """
    stored = read_manifest(config, root=root)
    changed: list[str] = []
    for source_path in walk_sources(config, root=root):
        rel = source_path.relative_to(root).as_posix()
        current_hash = sha256_file(source_path)
        if stored.get(rel) != current_hash:
            changed.append(rel)
    return sorted(changed)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_changed_files(
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
    *,
    since: str = "HEAD",
    force_manifest: bool = False,
) -> tuple[list[str], str]:
    """Return a list of changed source file paths and the detection method used.

    Args:
        config: Loaded dok-fu config dict.
        root: Project root.
        since: Git ref to diff against (default ``"HEAD"``).
        force_manifest: If True, skip git and use the manifest method.

    Returns:
        A tuple ``(changed_paths, method)`` where *changed_paths* is a sorted
        list of root-relative posix path strings and *method* is either
        ``"git"`` or ``"manifest"``.
    """
    root = Path(root or config.get("_root") or Path.cwd())

    if not force_manifest and _git_is_available(root):
        git_paths = _git_changed_files(since, root)
        if git_paths is not None:
            # Filter to only tracked source extensions
            source_globs = config.get("source_globs", [])
            exclude_globs = config.get("exclude_globs", [])
            from .common import _matches_any
            filtered = sorted(
                p for p in git_paths
                if (not exclude_globs or not _matches_any(p, exclude_globs))
                and (not source_globs or _matches_any(p, source_globs))
            )
            return filtered, "git"

    return _manifest_changed_files(config, root), "manifest"
