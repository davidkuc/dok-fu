"""
doctor.py - Validate the dok-fu documentation system and report problems.

Checks performed:
1. Broken pointers     - doc 'code' field points to non-existent source, or
                         source pointer comment points to non-existent doc.
2. Orphaned docs       - doc files that have no corresponding source file.
3. Orphaned sources    - source files whose expected doc does not exist AND
                         which have no pointer comment at all.
4. Unknown tags        - doc files using tags not in the registry.
5. Stale index         - docs/index.json missing or out-of-date.

Exit codes (for CLI use):
  0 - no problems found
  1 - one or more problems found

All public functions return structured data; printing/exit is left to the CLI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .common import load_config, map_source_to_doc, walk_sources
from .index import is_index_stale
from .pointers import (
    get_doc_code_pointer,
    get_source_doc_pointer,
    validate_all_docs,
    validate_pair,
)
from .tags import load_registry, validate_tags as _validate_tags


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DoctorReport:
    """Aggregated findings from a full doctor run."""

    broken_pointers: list[str] = field(default_factory=list)
    """Docs whose 'code' pointer is broken (file missing or pointer mismatch)."""

    orphaned_docs: list[str] = field(default_factory=list)
    """Doc files with no resolvable source file."""

    orphaned_sources: list[str] = field(default_factory=list)
    """Source files that are tracked but have no doc and no pointer comment."""

    unknown_tag_entries: list[tuple[str, list[str]]] = field(default_factory=list)
    """List of (doc_path, [unknown_tags]) for docs with unregistered tags."""

    stale_index: bool = False
    """True if docs/index.json is missing or doesn't match the current scan."""

    @property
    def has_problems(self) -> bool:
        return bool(
            self.broken_pointers
            or self.orphaned_docs
            or self.orphaned_sources
            or self.unknown_tag_entries
            or self.stale_index
        )

    def summary_lines(self) -> list[str]:
        """Return a human-readable list of problem descriptions."""
        lines: list[str] = []

        if self.broken_pointers:
            lines.append(f"Broken pointers ({len(self.broken_pointers)}):")
            for p in self.broken_pointers:
                lines.append(f"  - {p}")

        if self.orphaned_docs:
            lines.append(f"Orphaned docs ({len(self.orphaned_docs)}):")
            for p in self.orphaned_docs:
                lines.append(f"  - {p}")

        if self.orphaned_sources:
            lines.append(f"Orphaned sources ({len(self.orphaned_sources)}):")
            for p in self.orphaned_sources:
                lines.append(f"  - {p}")

        if self.unknown_tag_entries:
            lines.append(f"Unknown tags ({len(self.unknown_tag_entries)}):")
            for doc_p, tags in self.unknown_tag_entries:
                lines.append(f"  - {doc_p}: {', '.join(tags)}")

        if self.stale_index:
            lines.append("Index is stale: docs/index.json is missing or out-of-date.")

        if not lines:
            lines.append("No problems found.")

        return lines


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_pointers(
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
) -> tuple[list[str], list[str]]:
    """Check all doc<->source pointer pairs.

    Returns:
        (broken, orphaned_docs) - lists of root-relative posix path strings.
        broken: docs with any pointer validation failure.
        orphaned_docs: docs where the source file simply does not exist.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    results = validate_all_docs(config, root=root)

    broken: list[str] = []
    orphaned_docs: list[str] = []

    for r in results:
        if not r.is_valid:
            rel = r.doc_path.relative_to(root).as_posix()
            broken.append(f"{rel}: {'; '.join(r.issues)}")
            # If the source simply doesn't exist, also flag as orphaned
            if r.doc_has_code_field and (r.source_path is None or not r.source_path.exists()):
                orphaned_docs.append(rel)
        elif not r.doc_has_code_field:
            # Doc with no code field is also orphaned
            rel = r.doc_path.relative_to(root).as_posix()
            orphaned_docs.append(rel)

    return broken, orphaned_docs


def check_orphaned_sources(
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
) -> list[str]:
    """Find source files that have no doc file and no pointer comment.

    A source file is considered 'orphaned' only when it both lacks a doc
    mirror AND has no pointer comment (i.e. it has never been connected to
    the documentation system at all).

    Returns:
        Sorted list of root-relative posix path strings.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    orphaned: list[str] = []

    for source_path in walk_sources(config, root=root):
        expected_doc = map_source_to_doc(source_path, config, root=root)
        has_doc = expected_doc.exists()
        has_pointer = get_source_doc_pointer(source_path, config) is not None
        if not has_doc and not has_pointer:
            orphaned.append(source_path.relative_to(root).as_posix())

    return sorted(orphaned)


def check_unknown_tags(
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
) -> list[tuple[str, list[str]]]:
    """Find doc files that reference tags not in the registry.

    Returns:
        List of (root-relative doc path, [unknown tag strings]).
    """
    root = Path(root or config.get("_root") or Path.cwd())
    docs_dir = config.get("docs_dir", "docs")
    docs_root = root / docs_dir
    results: list[tuple[str, list[str]]] = []

    if not docs_root.exists():
        return results

    from .common import read_frontmatter_file

    for doc_path in sorted(docs_root.rglob("*.md")):
        if any(part.startswith(".") for part in doc_path.parts):
            continue
        try:
            fm, _ = read_frontmatter_file(doc_path)
        except (ValueError, OSError):
            continue
        tags = fm.get("tags") or []
        unknown = _validate_tags(tags, config, root=root)
        if unknown:
            results.append((doc_path.relative_to(root).as_posix(), unknown))

    return results


# ---------------------------------------------------------------------------
# Full doctor run
# ---------------------------------------------------------------------------

def run_doctor(
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
) -> DoctorReport:
    """Run all checks and return a consolidated :class:`DoctorReport`.

    Args:
        config: Loaded dok-fu config dict.
        root: Project root.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    report = DoctorReport()

    broken, orphaned_docs = check_pointers(config, root=root)
    report.broken_pointers = broken
    report.orphaned_docs = orphaned_docs
    report.orphaned_sources = check_orphaned_sources(config, root=root)
    report.unknown_tag_entries = check_unknown_tags(config, root=root)
    report.stale_index = is_index_stale(config, root=root)

    return report
