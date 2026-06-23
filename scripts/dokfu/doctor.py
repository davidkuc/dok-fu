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

from .common import load_config, map_source_to_doc, slugify_for_dokfu_id, walk_sources
from .index import is_index_stale
from .pointers import (
    get_doc_code_pointer,
    get_section_paths,
    get_source_doc_pointer,
    validate_all_docs,
    validate_pair,
)
from .tags import load_registry, validate_tags as _validate_tags


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class RenameCandidate:
    """A source file whose pointer target is missing but a matching doc exists elsewhere."""

    source_file: str
    """Root-relative posix path of the source file."""

    broken_pointer: str
    """The pointer target that no longer exists (as stored in the source file)."""

    candidate_doc: str
    """Root-relative posix path of a doc whose dokfu_id matches the source's folder."""


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

    cross_folder_violations: list[str] = field(default_factory=list)
    """Source files whose pointer targets a doc whose 'code' folder doesn't match the source's folder."""

    inconsistent_folder_pointers: list[str] = field(default_factory=list)
    """Folders where source files point to different doc modules."""

    missing_section_paths: list[str] = field(default_factory=list)
    """Doc section 'path:' entries that reference non-existent files."""

    missing_frontmatter_fields: list[tuple[str, list[str]]] = field(default_factory=list)
    """List of (doc_path, [missing_field_names]) for docs with incomplete frontmatter."""

    renamed: list[RenameCandidate] = field(default_factory=list)
    """Source files with broken pointers where a matching doc was found via dokfu_id."""

    @property
    def has_problems(self) -> bool:
        return bool(
            self.broken_pointers
            or self.orphaned_docs
            or self.orphaned_sources
            or self.unknown_tag_entries
            or self.stale_index
            or self.cross_folder_violations
            or self.inconsistent_folder_pointers
            or self.missing_section_paths
            or self.missing_frontmatter_fields
            or self.renamed
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

        if self.cross_folder_violations:
            lines.append(f"Cross-folder pointer violations ({len(self.cross_folder_violations)}):")
            for p in self.cross_folder_violations:
                lines.append(f"  - {p}")

        if self.inconsistent_folder_pointers:
            lines.append(f"Inconsistent folder pointers ({len(self.inconsistent_folder_pointers)}):")
            for p in self.inconsistent_folder_pointers:
                lines.append(f"  - {p}")

        if self.missing_section_paths:
            lines.append(f"Missing section paths ({len(self.missing_section_paths)}):")
            for p in self.missing_section_paths:
                lines.append(f"  - {p}")

        if self.missing_frontmatter_fields:
            lines.append(f"Missing frontmatter fields ({len(self.missing_frontmatter_fields)}):")
            for doc_p, fields in self.missing_frontmatter_fields:
                lines.append(f"  - {doc_p}: missing {', '.join(fields)}")

        if self.renamed:
            lines.append(f"Rename candidates ({len(self.renamed)}) — run `dokfu doctor --fix-pointers` to repair:")
            for r in self.renamed:
                lines.append(f"  - {r.source_file}: broken pointer '{r.broken_pointer}' → candidate '{r.candidate_doc}'")

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
        broken: docs with any pointer validation failure (source file missing or pointer mismatch).
        orphaned_docs: docs where the source file simply does not exist (subset of broken).
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


def check_cross_folder_pointers(
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
) -> list[str]:
    """Find source files whose pointer targets a doc whose 'code' field doesn't match.

    A source file in ``src/foo/`` should only point to a doc whose ``code:`` field
    resolves to ``src/foo/``. Any other combination is a cross-folder violation.

    Returns:
        List of human-readable violation strings.
    """
    root = Path(root or config.get("_root") or Path.cwd())
    violations: list[str] = []

    for source_path in walk_sources(config, root=root):
        pointer = get_source_doc_pointer(source_path, config)
        if pointer is None:
            continue
        doc_path = root / pointer
        if not doc_path.exists():
            continue  # broken pointer — already caught by check_pointers
        code_field = get_doc_code_pointer(doc_path)
        if code_field is None:
            continue  # malformed doc — caught elsewhere
        expected_folder = (root / code_field).resolve()
        actual_folder = source_path.parent.resolve()
        if expected_folder != actual_folder:
            violations.append(
                f"{source_path.relative_to(root).as_posix()}: points to {pointer} "
                f"(code: {code_field}), but file is in {source_path.parent.relative_to(root).as_posix()}/"
            )

    return violations


def check_folder_pointer_consistency(
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
) -> list[str]:
    """Find folders where source files point to more than one doc module.

    All source files within a folder should point to the same doc module.

    Returns:
        List of human-readable violation strings (one per offending folder).
    """
    root = Path(root or config.get("_root") or Path.cwd())
    folder_targets: dict[str, set[str]] = {}

    for source_path in walk_sources(config, root=root):
        pointer = get_source_doc_pointer(source_path, config)
        if pointer is None:
            continue
        folder_rel = source_path.parent.relative_to(root).as_posix()
        folder_targets.setdefault(folder_rel, set()).add(pointer)

    violations: list[str] = []
    for folder, targets in sorted(folder_targets.items()):
        if len(targets) > 1:
            violations.append(
                f"{folder}/: files point to multiple docs: {', '.join(sorted(targets))}"
            )
    return violations


def check_section_paths(
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
) -> list[str]:
    """Find doc section 'path:' entries that reference non-existent files or paths outside the module's code folder.

    Returns:
        List of human-readable strings, one per missing or boundary-violating path.
    """
    from .common import read_frontmatter_file

    root = Path(root or config.get("_root") or Path.cwd())
    docs_dir = config.get("docs_dir", "docs")
    docs_root = root / docs_dir
    missing: list[str] = []

    if not docs_root.exists():
        return missing

    for doc_path in sorted(docs_root.rglob("*.md")):
        if any(part.startswith(".") for part in doc_path.parts):
            continue
        try:
            fm, _ = read_frontmatter_file(doc_path)
        except (ValueError, OSError):
            continue
        code_field = fm.get("code")
        if not code_field:
            continue  # no code field — cannot validate boundary
        code_folder = (root / code_field).resolve()
        section_paths = get_section_paths(doc_path)
        for sp in section_paths:
            resolved = root / sp
            if not resolved.exists():
                missing.append(
                    f"{doc_path.relative_to(root).as_posix()}: section path '{sp}' does not exist"
                )
            else:
                # Check boundary: section path must be within the module's code folder
                try:
                    resolved.relative_to(code_folder)
                except ValueError:
                    missing.append(
                        f"{doc_path.relative_to(root).as_posix()}: section path '{sp}' is outside module's code folder '{code_field}'"
                    )

    return missing


def check_missing_frontmatter(
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
) -> list[tuple[str, list[str]]]:
    """Find doc files missing required frontmatter fields.

    Required fields: ``code``, ``description``, ``tags``, ``dokfu_id``.

    Returns:
        List of (root-relative doc path, [missing field names]).
    """
    root = Path(root or config.get("_root") or Path.cwd())
    docs_dir = config.get("docs_dir", "docs")
    docs_root = root / docs_dir
    results: list[tuple[str, list[str]]] = []

    if not docs_root.exists():
        return results

    from .common import read_frontmatter_file

    required = ["code", "description", "tags", "dokfu_id"]
    for doc_path in sorted(docs_root.rglob("*.md")):
        if any(part.startswith(".") for part in doc_path.parts):
            continue
        try:
            fm, _ = read_frontmatter_file(doc_path)
        except (ValueError, OSError):
            continue
        missing = [f for f in required if not fm.get(f)]
        if missing:
            results.append((doc_path.relative_to(root).as_posix(), missing))

    return results


def check_renamed_docs(
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
) -> list[RenameCandidate]:
    """Detect source files with broken pointers that match a renamed/moved doc.

    For each source file whose pointer target does not exist, compute the
    expected ``dokfu_id`` for the source file's folder and look for a doc
    module with that ``dokfu_id`` at a different path.

    Returns:
        List of :class:`RenameCandidate` objects.
    """
    from .common import read_frontmatter_file

    root = Path(root or config.get("_root") or Path.cwd())
    docs_dir = config.get("docs_dir", "docs")
    docs_root = root / docs_dir

    # Build a map: dokfu_id → doc_path (root-relative posix)
    dokfu_id_index: dict[str, str] = {}
    if docs_root.exists():
        for doc_path in sorted(docs_root.rglob("*.md")):
            if any(part.startswith(".") for part in doc_path.parts):
                continue
            try:
                fm, _ = read_frontmatter_file(doc_path)
            except (ValueError, OSError):
                continue
            did = fm.get("dokfu_id")
            if did:
                dokfu_id_index[str(did)] = doc_path.relative_to(root).as_posix()

    candidates: list[RenameCandidate] = []
    for source_path in walk_sources(config, root=root):
        pointer = get_source_doc_pointer(source_path, config)
        if pointer is None:
            continue
        pointer_path = root / pointer
        if pointer_path.exists():
            continue  # pointer is valid — not broken
        # Pointer target is missing; check for rename candidate
        folder_rel = source_path.parent.relative_to(root).as_posix()
        expected_id = slugify_for_dokfu_id(folder_rel)
        candidate_doc = dokfu_id_index.get(expected_id)
        if candidate_doc and candidate_doc != pointer:
            candidates.append(
                RenameCandidate(
                    source_file=source_path.relative_to(root).as_posix(),
                    broken_pointer=pointer,
                    candidate_doc=candidate_doc,
                )
            )

    return candidates


def fix_pointers(
    report: "DoctorReport",
    config: dict[str, Any],
    root: str | os.PathLike | None = None,
) -> list[str]:
    """Repair source file pointer comments using rename candidates from *report*.

    For each :class:`RenameCandidate` in ``report.renamed``, rewrites the
    pointer comment in the source file so it points to ``candidate_doc``.

    Returns:
        Root-relative posix paths of source files that were updated.
    """
    from .common import build_pointer_line, parse_pointer_line

    root = Path(root or config.get("_root") or Path.cwd())
    updated: list[str] = []

    for candidate in report.renamed:
        source_path = root / candidate.source_file
        if not source_path.exists():
            continue
        text = source_path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        new_pointer = build_pointer_line(candidate.candidate_doc, source_path.suffix, config, root=root)
        replaced = False
        new_lines = []
        for line in lines:
            if not replaced and parse_pointer_line(line.rstrip("\n"), config) is not None:
                new_lines.append(new_pointer + "\n")
                replaced = True
            else:
                new_lines.append(line)
        if replaced:
            source_path.write_text("".join(new_lines), encoding="utf-8")
            updated.append(candidate.source_file)

    return updated


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
    report.cross_folder_violations = check_cross_folder_pointers(config, root=root)
    report.inconsistent_folder_pointers = check_folder_pointer_consistency(config, root=root)
    report.missing_section_paths = check_section_paths(config, root=root)
    report.missing_frontmatter_fields = check_missing_frontmatter(config, root=root)
    report.renamed = check_renamed_docs(config, root=root)

    return report
