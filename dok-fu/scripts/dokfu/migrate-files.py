#!/usr/bin/env python3
"""
migrate.py — Migration tool to encapsulate dok-fu system files into a dok-fu/ subfolder.

Sub-commands:
  scan      Walk repo, record current paths and inline path references → migration-manifest.json
  move      Execute git mv for each directory in move_map
  patch     Rewrite stale path references in moved files (--dry-run default, --apply to write)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST_FILE = "migration-manifest.json"

# Directories to move into dok-fu/
MOVE_MAP = {
    "base": "dok-fu/base",
    "config": "dok-fu/config",
    "scripts": "dok-fu/scripts",
    "templates": "dok-fu/templates",
    "tests": "dok-fu/tests",
    "examples": "dok-fu/examples",
}

# Always skip these directories when walking
SKIP_DIRS = {".git"}

# Files / globs to skip entirely during patch
PATCH_SKIP_PREFIXES = (".github/", ".claude/")
PATCH_SKIP_FILES = {MANIFEST_FILE, "migrate.py"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    """Return the repo root (directory containing this script)."""
    return Path(__file__).resolve().parent


def _is_binary(path: Path) -> bool:
    """Return True if *path* looks like a binary file (contains a null byte)."""
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


def _relative_str(path: Path, root: Path) -> str:
    """Return a POSIX-style relative path string."""
    return path.relative_to(root).as_posix()


def _walk_text_files(root: Path):
    """Yield (path, rel_posix) for every non-binary file under *root*, skipping SKIP_DIRS."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if _is_binary(fpath):
                continue
            yield fpath, _relative_str(fpath, root)


def _build_known_paths(root: Path) -> set:
    """
    Collect all relative path strings (files + directories) present in the repo,
    excluding .git/ and dok-fu/ subtrees.
    """
    known: set = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel_dir = _relative_str(Path(dirpath), root)
        if rel_dir != ".":
            known.add(rel_dir)
        for fname in filenames:
            fpath = Path(dirpath) / fname
            known.add(_relative_str(fpath, root))
    return known


def _compute_new_path(rel: str) -> str:
    """
    Return the post-migration relative path for *rel*, or the same string if it stays at root.
    """
    for old_prefix, new_prefix in MOVE_MAP.items():
        if rel == old_prefix or rel.startswith(old_prefix + "/"):
            return new_prefix + rel[len(old_prefix):]
    return rel


# ---------------------------------------------------------------------------
# Sub-command: scan
# ---------------------------------------------------------------------------


def cmd_scan(args):
    root = _repo_root()
    print(f"[scan] Repo root: {root}")

    known_paths = _build_known_paths(root)
    print(f"[scan] Known paths collected: {len(known_paths)}")

    # Sort known paths longest-first so that more-specific paths match before shorter ones
    sorted_known = sorted(known_paths, key=len, reverse=True)

    files_entry: dict = {}

    for fpath, rel in _walk_text_files(root):
        new_path = _compute_new_path(rel)
        refs = []

        try:
            lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            print(f"[scan]   WARN: cannot read {rel}: {exc}", file=sys.stderr)
            continue

        for lineno, line in enumerate(lines, start=1):
            for known in sorted_known:
                if known in line:
                    refs.append({
                        "old_ref": known,
                        "line": lineno,
                        "snippet": line.rstrip(),
                    })
                    # Don't double-count the same known path on the same line
                    break  # only record first (longest) match per line

        files_entry[rel] = {
            "new_path": new_path,
            "refs": refs,
        }

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "move_map": MOVE_MAP,
        "files": files_entry,
    }

    out_path = root / MANIFEST_FILE
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[scan] Manifest written to: {out_path}")

    # Summary
    total_refs = sum(len(v["refs"]) for v in files_entry.values())
    files_with_refs = sum(1 for v in files_entry.values() if v["refs"])
    print(f"[scan] Files scanned: {len(files_entry)}")
    print(f"[scan] Files with path references: {files_with_refs}")
    print(f"[scan] Total path references found: {total_refs}")


# ---------------------------------------------------------------------------
# Sub-command: move
# ---------------------------------------------------------------------------


def cmd_move(args):
    root = _repo_root()
    manifest_path = root / MANIFEST_FILE

    if not manifest_path.exists():
        print(f"[move] ERROR: {MANIFEST_FILE} not found. Run 'scan' first.", file=sys.stderr)
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    move_map = manifest.get("move_map", MOVE_MAP)

    # Create the dok-fu/ wrapper directory if needed
    dokfu_dir = root / "dok-fu"
    if not dokfu_dir.exists():
        os.mkdir(dokfu_dir)
        print(f"[move] Created directory: dok-fu/")

    for old_name, new_name in move_map.items():
        old_path = root / old_name
        new_path = root / new_name

        if not old_path.exists():
            print(f"[move]   SKIP (not found): {old_name}")
            continue

        if new_path.exists():
            print(f"[move]   SKIP (destination exists): {new_name}")
            continue

        print(f"[move]   git mv {old_name} → {new_name}")
        result = subprocess.run(
            ["git", "mv", old_name, new_name],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"[move]   ERROR: git mv failed for {old_name}:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"[move]   OK")

    print("[move] Done.")


# ---------------------------------------------------------------------------
# Sub-command: patch
# ---------------------------------------------------------------------------


def _patch_content(content: str) -> str:
    """
    Apply path prefix replacements using regex with proper boundaries.
    Only match path prefixes that appear at the start of a path reference,
    not nested components within paths that already contain multiple segments.
    
    For example:
    - Match: 'scripts/dokfu.py' → 'dok-fu/scripts/dokfu.py'
    - Match: ' scripts/' → ' dok-fu/scripts/'
    - NO match: 'examples/sample/scripts/' (scripts here is nested, not a top-level ref)
    """
    for old_prefix, new_prefix in MOVE_MAP.items():
        # Use a regex that matches old_prefix only when:
        # 1. At start of line OR after whitespace/quote/path-start characters
        # 2. Followed by a slash (indicating it's a directory path)
        # 3. NOT preceded by another path component (avoid nested matches)
        # 
        # This regex looks for:
        # - (^|[=:\s"\']) - start of line or after special chars: (?:^|[=:\s"\'])
        # - (old_prefix) - the directory name
        # - (?=/) - followed by slash (lookahead, not consumed)
        pattern = re.compile(
            r'(^|[=:\s"\'])' + re.escape(old_prefix) + r'(?=/)',
            re.MULTILINE
        )
        content = pattern.sub(r'\1' + new_prefix, content)
    
    return content


def _unified_diff(old_lines: list, new_lines: list, filename: str) -> str:
    """Return a simple unified diff string (no difflib dependency)."""
    import difflib
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )


def cmd_patch(args):
    dry_run: bool = not args.apply
    root = _repo_root()
    manifest_path = root / MANIFEST_FILE

    if not manifest_path.exists():
        print(f"[patch] ERROR: {MANIFEST_FILE} not found. Run 'scan' first.", file=sys.stderr)
        sys.exit(1)

    mode_label = "DRY-RUN" if dry_run else "APPLY"
    print(f"[patch] Mode: {mode_label}")

    changed_files = 0
    total_changes = 0

    # Walk all text files in the repo at their post-move locations.
    for fpath, rel in _walk_text_files(root):
        # Skip files that should not be patched
        if any(rel.startswith(p) for p in PATCH_SKIP_PREFIXES):
            continue
        if rel in PATCH_SKIP_FILES:
            continue
        # Also skip patch_output.txt if it exists
        if rel == "patch_output.txt":
            continue

        try:
            original = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"[patch]   WARN: cannot read {rel}: {exc}", file=sys.stderr)
            continue

        patched = _patch_content(original)

        if patched == original:
            continue

        changed_files += 1
        old_lines = original.splitlines(keepends=True)
        new_lines = patched.splitlines(keepends=True)
        diff = _unified_diff(old_lines, new_lines, rel)
        total_changes += diff.count("\n-")

        if dry_run:
            print(diff, end="")
        else:
            fpath.write_text(patched, encoding="utf-8")
            print(f"[patch]   Updated: {rel}")

    if dry_run:
        print(f"\n[patch] DRY-RUN complete. {changed_files} file(s) would be modified.")
    else:
        print(f"\n[patch] APPLY complete. {changed_files} file(s) updated.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Migration tool: encapsulate dok-fu system files into dok-fu/ subfolder.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Workflow:
              1. python migrate.py scan          → produces migration-manifest.json
              2. python migrate.py move          → git mv all dirs into dok-fu/
              3. python migrate.py patch         → preview reference updates (dry-run)
              4. python migrate.py patch --apply → write reference updates
        """),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="Walk repo and record path references into migration-manifest.json")
    sub.add_parser("move", help="Execute git mv for each directory in the move_map")

    patch_p = sub.add_parser("patch", help="Rewrite stale path references in moved files")
    patch_p.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to disk (default is dry-run / preview only)",
    )

    args = parser.parse_args()

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "move":
        cmd_move(args)
    elif args.command == "patch":
        cmd_patch(args)


if __name__ == "__main__":
    main()
