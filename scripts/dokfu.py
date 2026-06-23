#!/usr/bin/env python3
"""
dokfu.py - CLI entry point for the dok-fu documentation workflow system.

Subcommands:
  install   [--target DIR]         Scaffold + vendor into a target project
  generate                         Regenerate .github/.claude from base/
  index     [--check]              Build docs/index.json; --check exits nonzero if stale
  tags      --list | --search TAG  List registry / find docs by tag
  doctor    [--fix-index]          Validate pointers, tags, index; report problems
  changes   [--since REF]          List changed source files
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add repo root to path so 'scripts' package can be imported
_repo_root = Path(__file__).parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def _get_config(args_root: str | None = None):
    """Load config from disk, using *args_root* as the project root."""
    from scripts.dokfu.common import load_config
    root = Path(args_root) if args_root else Path.cwd()
    return load_config(root=root), root


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _resolve_root(args: argparse.Namespace) -> Path:
    """Return the project root: --root flag if given, else cwd."""
    return Path(args.root) if args.root else Path.cwd()


def cmd_install(args: argparse.Namespace) -> int:
    from scripts.dokfu.install import install

    target = Path(args.target) if args.target else Path.cwd()
    result = install(target=target, source_root=Path.cwd(), overwrite=args.overwrite)

    print(f"Installed into: {result.target}")
    print(f"  Copied {len(result.copied_files)} file(s)")
    if result.generate_result:
        gr = result.generate_result
        print(f"  Generated {len(gr.written)} file(s), {len(gr.unchanged)} unchanged")
    if result.manifest_path:
        print(f"  Manifest seeded: {result.manifest_path}")
    if result.index_path:
        print(f"  Index path: {result.index_path}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    from scripts.dokfu.generate import generate
    from scripts.dokfu.common import load_config

    root = _resolve_root(args)
    config = load_config(root=root)
    result = generate(config=config, root=root)

    for path in result.written:
        print(f"  wrote   {path}")
    for path in result.unchanged:
        print(f"  ok      {path}")
    print(f"generate: {len(result.written)} written, {len(result.unchanged)} unchanged")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    from scripts.dokfu.index import build_index, is_index_stale, write_index
    from scripts.dokfu.common import load_config

    root = _resolve_root(args)
    config = load_config(root=root)

    if args.check:
        if is_index_stale(config, root=root):
            print("index: STALE — docs/index.json is missing or out-of-date", file=sys.stderr)
            return 1
        print("index: up-to-date")
        return 0

    entries = build_index(config, root=root)
    path = write_index(entries, config, root=root)
    print(f"index: wrote {len(entries)} entries → {path}")
    return 0


def cmd_tags(args: argparse.Namespace) -> int:
    from scripts.dokfu.tags import list_tags, search_by_tag
    from scripts.dokfu.common import load_config

    root = _resolve_root(args)
    config = load_config(root=root)

    if args.list:
        registry = list_tags(config, root=root)
        for tag, explanation in sorted(registry.items()):
            print(f"  {tag:20s}  {explanation}")
        return 0

    if args.search:
        tag = args.search
        try:
            paths = search_by_tag(tag, config, root=root)
        except ValueError as exc:
            print(f"tags: {exc}", file=sys.stderr)
            return 1
        if not paths:
            print(f"tags: no docs found for tag '{tag}'")
            return 0
        for p in paths:
            print(p)
        return 0

    print("tags: use --list or --search TAG", file=sys.stderr)
    return 1


def cmd_doctor(args: argparse.Namespace) -> int:
    from scripts.dokfu.doctor import run_doctor, fix_pointers
    from scripts.dokfu.index import build_index, write_index
    from scripts.dokfu.common import load_config

    root = _resolve_root(args)
    config = load_config(root=root)
    report = run_doctor(config, root=root)

    for line in report.summary_lines():
        print(line)

    if args.fix_index and report.stale_index:
        entries = build_index(config, root=root)
        path = write_index(entries, config, root=root)
        print(f"doctor: rebuilt index → {path}")

    if args.fix_pointers:
        updated = fix_pointers(report, config, root=root)
        if updated:
            print(f"doctor: fixed {len(updated)} pointer(s):")
            for p in updated:
                print(f"  {p}")
        else:
            print("doctor: no pointers to fix")

    return 1 if report.has_problems else 0


def cmd_changes(args: argparse.Namespace) -> int:
    from scripts.dokfu.changes import get_changed_files
    from scripts.dokfu.common import load_config

    root = _resolve_root(args)
    config = load_config(root=root)
    since = args.since if args.since else "HEAD~1"

    changed, method = get_changed_files(config, root=root, since=since)
    print(f"changes ({method}, since {since}):")
    if not changed:
        print("  (none)")
    else:
        for p in changed:
            print(f"  {p}")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dokfu",
        description="Dok-Fu documentation workflow system",
    )
    parser.add_argument(
        "--root",
        default=None,
        metavar="DIR",
        help="Project root directory (default: current directory)",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # install
    p_install = sub.add_parser("install", help="Scaffold dok-fu into a target project")
    p_install.add_argument(
        "--target",
        default=None,
        metavar="DIR",
        help="Target project directory (default: current directory)",
    )
    p_install.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files in the target",
    )

    # generate
    sub.add_parser("generate", help="Regenerate .github/.claude from base/ (idempotent)")

    # index
    p_index = sub.add_parser("index", help="Build docs/index.json")
    p_index.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero if docs/index.json is stale without writing",
    )

    # tags
    p_tags = sub.add_parser("tags", help="Tag registry operations")
    tags_group = p_tags.add_mutually_exclusive_group(required=True)
    tags_group.add_argument("--list", action="store_true", help="List all registered tags")
    tags_group.add_argument("--search", metavar="TAG", help="Find docs with the given tag")

    # doctor
    p_doctor = sub.add_parser(
        "doctor",
        help="Validate pointers, tags, and index freshness",
    )
    p_doctor.add_argument(
        "--fix-index",
        action="store_true",
        dest="fix_index",
        help="Rebuild index if stale",
    )
    p_doctor.add_argument(
        "--fix-pointers",
        action="store_true",
        dest="fix_pointers",
        help="Repair source file pointer comments using dokfu_id rename detection",
    )

    # changes
    p_changes = sub.add_parser("changes", help="List changed source files")
    p_changes.add_argument(
        "--since",
        default=None,
        metavar="REF",
        help="Git ref to diff against (default: HEAD)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    dispatch = {
        "install": cmd_install,
        "generate": cmd_generate,
        "index": cmd_index,
        "tags": cmd_tags,
        "doctor": cmd_doctor,
        "changes": cmd_changes,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
