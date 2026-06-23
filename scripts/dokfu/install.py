"""
install.py - Install dok-fu into a target project.

Copies the dok-fu runtime (scripts/, base/, config/) into the target directory,
creates the docs/ scaffold, runs generate to produce .github/ and .claude/,
and seeds the change-detection manifest.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .changes import update_manifest
from .common import load_config
from .generate import GenerateResult, generate
from .index import write_index


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _copy_tree(src: Path, dst: Path, *, overwrite: bool = False) -> list[Path]:
    """Recursively copy *src* directory into *dst*, returning copied paths.

    Existing files are skipped unless *overwrite* is True.
    """
    written: list[Path] = []
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if target.exists() and not overwrite:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        written.append(target)
    return written


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class InstallResult:
    """Summary of a dok-fu install run."""

    target: Path
    copied_files: list[str] = field(default_factory=list)
    generate_result: GenerateResult | None = None
    manifest_path: str | None = None
    index_path: str | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def install(
    target: str | os.PathLike | None = None,
    *,
    source_root: str | os.PathLike | None = None,
    overwrite: bool = False,
) -> InstallResult:
    """Install dok-fu into *target* directory.

    Steps:
    1. Copy ``scripts/dokfu/``, ``base/``, ``config/`` from *source_root* → *target*.
    2. Create ``docs/`` directory.
    3. Run :func:`~generate.generate` to emit ``.github/`` and ``.claude/``.
    4. Seed ``docs/.dokfu-manifest.json`` from current source files.
    5. Initialise an empty ``docs/index.json``.

    Args:
        target: Destination project root.  Defaults to the current working
            directory.
        source_root: The dok-fu repository root (where ``base/``, ``scripts/``,
            ``config/`` live).  Defaults to the current working directory.
        overwrite: If True, overwrite existing files in *target*.  Defaults
            to False (skip existing files).

    Returns:
        :class:`InstallResult` with a summary of what was done.
    """
    target = Path(target) if target else Path.cwd()
    src = Path(source_root) if source_root else Path.cwd()

    result = InstallResult(target=target)

    # 1. Copy runtime directories
    dirs_to_copy = [
        (src / "scripts" / "dokfu", target / "scripts" / "dokfu"),
        (src / "base", target / "base"),
        (src / "config", target / "config"),
        (src / "templates", target / "templates"),
    ]
    for src_dir, dst_dir in dirs_to_copy:
        if src_dir.exists():
            copied = _copy_tree(src_dir, dst_dir, overwrite=overwrite)
            result.copied_files.extend(str(p) for p in copied)

    # 1a. Copy entry point script
    dokfu_py_src = src / "scripts" / "dokfu.py"
    if dokfu_py_src.exists():
        dokfu_py_dst = target / "scripts" / "dokfu.py"
        dokfu_py_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dokfu_py_src, dokfu_py_dst)
        result.copied_files.append(str(dokfu_py_dst))

    # 2. Ensure docs/ directory exists
    docs_dir = target / "docs"
    _ensure_dir(docs_dir)

    # 3. Run generate
    try:
        target_config = load_config(root=target)
    except FileNotFoundError:
        # Config may not be present in the target yet; fall back to defaults
        target_config = {
            "_root": str(target),
            "docs_dir": "docs",
            "source_globs": ["**/*.py", "**/*.js", "**/*.ts"],
            "exclude_globs": ["**/node_modules/**", "**/.git/**", "**/__pycache__/**"],
            "pointer_token": "dok-fu",
            "comment_map": {".py": "#", ".js": "//", ".ts": "//"},
            "registry_path": "config/tags.registry.json",
            "manifest_path": "docs/.dokfu-manifest.json",
        }

    gen = generate(config=target_config, root=target)
    result.generate_result = gen

    # 4. Seed the change-detection manifest
    try:
        manifest = update_manifest(target_config, root=target)
        manifest_path_obj = target / target_config.get("manifest_path", "docs/.dokfu-manifest.json")
        result.manifest_path = str(manifest_path_obj)
    except Exception:
        pass  # Manifest seeding is best-effort

    # 5. Initialise empty index.json if absent
    index_path = docs_dir / "index.json"
    if not index_path.exists():
        index_path.write_text(json.dumps([], indent=2) + "\n", encoding="utf-8")
    result.index_path = str(index_path)

    return result
