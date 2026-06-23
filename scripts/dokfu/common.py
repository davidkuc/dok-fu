"""
common.py - Shared utilities for dok-fu: config loading, frontmatter, source walking,
path mapping, and comment/pointer helpers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterator

import yaml

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = "config/dok-fu.config.json"


def load_config(config_path: str | os.PathLike | None = None, root: str | os.PathLike | None = None) -> dict[str, Any]:
    """Load and return the dok-fu config as a dict.

    Args:
        config_path: Path to the JSON config file. Defaults to
            ``config/dok-fu.config.json`` relative to *root*.
        root: Project root directory. Defaults to the current working directory.

    Returns:
        Parsed config dict with all expected keys present (merges defaults).
    """
    root = Path(root) if root else Path.cwd()
    if config_path is None:
        config_path = root / _DEFAULT_CONFIG_PATH
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"dok-fu config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as fh:
        cfg = json.load(fh)

    # Inject root so callers can resolve relative paths
    cfg.setdefault("_root", str(root))
    return cfg


# ---------------------------------------------------------------------------
# YAML Frontmatter
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)(?:\r?\n)?---\r?\n?", re.DOTALL)


def read_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from *text*.

    Returns:
        (frontmatter_dict, body_text) where *body_text* is everything after
        the closing ``---`` delimiter (preserving the original body verbatim).
        If no frontmatter is present, returns ({}, original text).
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML frontmatter: {exc}") from exc

    body = text[match.end():]
    return fm, body


def write_frontmatter(frontmatter: dict[str, Any], body: str) -> str:
    """Serialize *frontmatter* dict + *body* back to a complete document string.

    The YAML block uses the default PyYAML dumper (block style, utf-8 safe).
    *body* is appended verbatim after the closing ``---`` delimiter.
    """
    fm_text = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return f"---\n{fm_text}---\n{body}"


def read_frontmatter_file(path: str | os.PathLike) -> tuple[dict[str, Any], str]:
    """Convenience wrapper: read a file and return (frontmatter, body)."""
    text = Path(path).read_text(encoding="utf-8")
    return read_frontmatter(text)


def write_frontmatter_file(path: str | os.PathLike, frontmatter: dict[str, Any], body: str) -> None:
    """Convenience wrapper: write frontmatter + body to *path*."""
    Path(path).write_text(write_frontmatter(frontmatter, body), encoding="utf-8")


# ---------------------------------------------------------------------------
# Source walking
# ---------------------------------------------------------------------------

def _matches_any(rel_str: str, patterns: list[str]) -> bool:
    """Return True if *rel_str* matches any of the glob *patterns*.

    Uses ``Path.match()`` which supports ``**`` recursive wildcards
    (requires Python 3.12+).  Also tests against the bare filename so
    simple extension patterns like ``*.min.js`` work without a path prefix.
    """
    p = Path(rel_str)
    for pat in patterns:
        if p.match(pat):
            return True
        # Path.match("**/X/**") may not match when the leading ** covers zero
        # components, so strip the leading **/ and retry.
        if pat.startswith("**/") and p.match(pat[3:]):
            return True
        # Also match bare filename for simple patterns like "*.min.js"
        if p.name != rel_str and Path(p.name).match(pat):
            return True
    return False


def walk_sources(config: dict[str, Any], root: str | os.PathLike | None = None) -> Iterator[Path]:
    """Yield source file Paths matching config source_globs, excluding exclude_globs.

    Args:
        config: Loaded dok-fu config dict.
        root: Project root. Falls back to config['_root'] then cwd.

    Yields:
        Absolute Paths for each matching source file.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    include = config.get("source_globs", [])
    exclude = config.get("exclude_globs", [])

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if exclude and _matches_any(rel, exclude):
            continue
        if include and not _matches_any(rel, include):
            continue
        yield path


# ---------------------------------------------------------------------------
# Path mapping: source <-> doc
# ---------------------------------------------------------------------------

def map_source_to_doc(source_path: str | os.PathLike, config: dict[str, Any], root: str | os.PathLike | None = None) -> Path:
    """Return the docs/ mirror path for a given source file.

    The mapping preserves directory structure:
        <root>/<rel/path/to/source.py>  ->  <root>/<docs_dir>/<rel/path/to/source.md>

    Args:
        source_path: Absolute or root-relative path to the source file.
        config: Loaded dok-fu config dict.
        root: Project root.  Falls back to config['_root'] then cwd.

    Returns:
        Absolute Path of the corresponding docs file (may not exist yet).
    """
    root = Path(root or config.get("_root") or Path.cwd())
    docs_dir = config.get("docs_dir", "docs")
    source_path = Path(source_path)
    if source_path.is_absolute():
        rel = source_path.relative_to(root)
    else:
        rel = source_path
    doc_rel = Path(docs_dir) / rel.with_suffix(".md")
    return root / doc_rel


def map_doc_to_source(doc_path: str | os.PathLike, config: dict[str, Any], root: str | os.PathLike | None = None) -> Path | None:
    """Return the source file path for a given docs/ mirror file.

    Inspects the file's YAML frontmatter ``code`` field if present;
    otherwise derives the source path by reversing the mirror mapping using
    the configured ``source_globs`` extensions.

    Args:
        doc_path: Absolute or root-relative path to the doc file.
        config: Loaded dok-fu config dict.
        root: Project root.  Falls back to config['_root'] then cwd.

    Returns:
        Absolute Path of the corresponding source file, or None if it cannot
        be determined.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    docs_dir = config.get("docs_dir", "docs")
    doc_path = Path(doc_path)
    if doc_path.is_absolute():
        rel = doc_path.relative_to(root)
    else:
        rel = doc_path

    # Try frontmatter 'code' field first
    abs_doc = root / rel
    if abs_doc.exists():
        try:
            fm, _ = read_frontmatter_file(abs_doc)
            code_field = fm.get("code")
            if code_field:
                return root / code_field
        except (ValueError, OSError):
            pass

    # Derive from path: strip docs_dir prefix, replace .md with known source exts
    try:
        rel_after_docs = rel.relative_to(docs_dir)
    except ValueError:
        return None

    stem = rel_after_docs.with_suffix("")
    comment_map: dict[str, str] = config.get("comment_map", {})
    for ext in comment_map:
        candidate = root / stem.with_suffix(ext)
        if candidate.exists():
            return candidate

    return None


# ---------------------------------------------------------------------------
# Comment / pointer helpers
# ---------------------------------------------------------------------------

def comment_for_ext(ext: str, config: dict[str, Any]) -> str | None:
    """Return the single-line comment prefix for *ext* (e.g. '.py' -> '#').

    Returns None if the extension is not in the comment_map.
    """
    comment_map: dict[str, str] = config.get("comment_map", {})
    # Normalise: ensure leading dot
    if not ext.startswith("."):
        ext = "." + ext
    return comment_map.get(ext)


def build_pointer_line(doc_path: str | os.PathLike, ext: str, config: dict[str, Any], root: str | os.PathLike | None = None) -> str | None:
    """Build the pointer comment line to embed in a source file.

    Format: ``<comment_prefix> <token>: <docs_relative_path>``
    Example: ``# dok-fu: docs/src/auth.md``

    Args:
        doc_path: Absolute or root-relative path of the documentation file.
        ext: Source file extension (e.g. '.py').
        config: Loaded dok-fu config dict.
        root: Project root.  Falls back to config['_root'] then cwd.

    Returns:
        The pointer line string, or None if the extension has no comment syntax.
    """
    prefix = comment_for_ext(ext, config)
    if prefix is None:
        return None
    root = Path(root or config.get("_root") or Path.cwd())
    doc_path = Path(doc_path)
    if doc_path.is_absolute():
        rel = doc_path.relative_to(root).as_posix()
    else:
        rel = doc_path.as_posix()
    token = config.get("pointer_token", "dok-fu")
    return f"{prefix} {token}: {rel}"


def parse_pointer_line(line: str, config: dict[str, Any]) -> str | None:
    """Extract the doc path from a source pointer comment line.

    Args:
        line: A single line of source code (stripped or not).
        config: Loaded dok-fu config dict.

    Returns:
        The doc path string from the pointer, or None if the line is not a
        pointer line for the configured token.
    """
    token = config.get("pointer_token", "dok-fu")
    # Match: <anything> <token>: <path>
    pattern = re.compile(rf"^\s*\S+\s+{re.escape(token)}:\s+(\S+)")
    match = pattern.match(line)
    if match:
        return match.group(1)
    return None


# ---------------------------------------------------------------------------
# Content hashing (used by changes.py / manifest)
# ---------------------------------------------------------------------------

def sha256_file(path: str | os.PathLike) -> str:
    """Return the hex SHA-256 digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
