"""
tests/test_doctor.py - Unit tests for scripts/dokfu/doctor.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from dokfu.common import load_config, write_frontmatter_file
from dokfu.index import build_index, write_index
from dokfu.doctor import (
    DoctorReport,
    check_orphaned_sources,
    check_pointers,
    check_unknown_tags,
    run_doctor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def env(tmp_path):
    registry = {
        "auth": "authentication",
        "cli": "command-line interface",
    }
    cfg_data = {
        "docs_dir": "docs",
        "source_globs": ["**/*.py"],
        "exclude_globs": ["**/__pycache__/**", "docs/**", "scripts/dokfu/**"],
        "pointer_token": "dok-fu",
        "comment_map": {".py": "#"},
        "registry_path": "config/tags.registry.json",
        "manifest_path": "docs/.dokfu-manifest.json",
    }
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "dok-fu.config.json").write_text(
        json.dumps(cfg_data), encoding="utf-8"
    )
    (tmp_path / "config" / "tags.registry.json").write_text(
        json.dumps(registry), encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()
    return tmp_path


@pytest.fixture()
def cfg(env):
    return load_config(root=env)


def _make_valid_pair(env: Path, rel_src="src/auth.py", rel_doc="docs/src.md"):
    """Create a valid module + source file pair.

    The module (rel_doc) covers the folder containing rel_src.
    """
    from pathlib import PurePosixPath
    src_folder = str(PurePosixPath(rel_src).parent)
    doc = env / rel_doc
    doc.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"# {src_folder}\n\n"
        f"## Sections\n- [auth.py](#auth-py)\n\n"
        f"## auth.py\npath: {rel_src}\nHandles auth.\n"
    )
    write_frontmatter_file(
        doc,
        {"code": src_folder, "tags": ["auth"], "description": "Auth module."},
        body,
    )
    src = env / rel_src
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(f"# dok-fu: {rel_doc}\n\ndef login(): pass\n", encoding="utf-8")
    return doc, src


# ---------------------------------------------------------------------------
# check_pointers
# ---------------------------------------------------------------------------

class TestCheckPointers:
    def test_no_docs_no_issues(self, cfg, env):
        broken, orphaned = check_pointers(cfg, root=env)
        assert broken == []
        assert orphaned == []

    def test_valid_pair_no_issues(self, cfg, env):
        _make_valid_pair(env)
        broken, orphaned = check_pointers(cfg, root=env)
        assert broken == []
        assert orphaned == []

    def test_broken_doc_no_code_field(self, cfg, env):
        doc = env / "docs" / "x.md"
        write_frontmatter_file(doc, {"description": "No code."}, "")
        broken, orphaned = check_pointers(cfg, root=env)
        assert any("docs/x.md" in b for b in broken)

    def test_orphaned_doc_missing_source_folder(self, cfg, env):
        doc = env / "docs" / "x.md"
        write_frontmatter_file(doc, {"code": "src/ghost"}, "")
        broken, orphaned = check_pointers(cfg, root=env)
        assert any("docs/x.md" in b for b in broken)
        assert "docs/x.md" in orphaned


# ---------------------------------------------------------------------------
# check_orphaned_sources
# ---------------------------------------------------------------------------

class TestCheckOrphanedSources:
    def test_no_sources_no_orphans(self, cfg, env):
        assert check_orphaned_sources(cfg, root=env) == []

    def test_source_with_doc_not_orphaned(self, cfg, env):
        # src/auth.py -> map_source_to_doc -> docs/src.md (which exists after valid pair)
        _make_valid_pair(env)
        orphans = check_orphaned_sources(cfg, root=env)
        assert "src/auth.py" not in orphans

    def test_source_with_pointer_not_orphaned(self, cfg, env):
        # Source has a pointer comment but no module doc -> still not orphaned
        src = env / "src" / "partial.py"
        src.write_text("# dok-fu: docs/src.md\n", encoding="utf-8")
        orphans = check_orphaned_sources(cfg, root=env)
        assert "src/partial.py" not in orphans

    def test_source_with_neither_is_orphaned(self, cfg, env):
        src = env / "src" / "lonely.py"
        src.write_text("def foo(): pass\n", encoding="utf-8")
        orphans = check_orphaned_sources(cfg, root=env)
        assert "src/lonely.py" in orphans

    def test_results_are_sorted(self, cfg, env):
        for name in ["z.py", "a.py", "m.py"]:
            (env / "src" / name).write_text("# no pointer\n", encoding="utf-8")
        orphans = check_orphaned_sources(cfg, root=env)
        assert orphans == sorted(orphans)


# ---------------------------------------------------------------------------
# check_unknown_tags
# ---------------------------------------------------------------------------

class TestCheckUnknownTags:
    def test_no_docs_no_issues(self, cfg, env):
        assert check_unknown_tags(cfg, root=env) == []

    def test_valid_tags_no_issues(self, cfg, env):
        write_frontmatter_file(env / "docs" / "x.md", {"tags": ["auth"]}, "")
        assert check_unknown_tags(cfg, root=env) == []

    def test_detects_unknown_tags(self, cfg, env):
        write_frontmatter_file(env / "docs" / "x.md", {"tags": ["auth", "bogus"]}, "")
        results = check_unknown_tags(cfg, root=env)
        assert len(results) == 1
        doc_path, unknown = results[0]
        assert "bogus" in unknown

    def test_no_tags_field_no_issue(self, cfg, env):
        write_frontmatter_file(env / "docs" / "x.md", {"description": "No tags"}, "")
        assert check_unknown_tags(cfg, root=env) == []


# ---------------------------------------------------------------------------
# DoctorReport
# ---------------------------------------------------------------------------

class TestDoctorReport:
    def test_no_problems(self):
        r = DoctorReport()
        assert not r.has_problems
        lines = r.summary_lines()
        assert lines == ["No problems found."]

    def test_has_problems_broken_pointers(self):
        r = DoctorReport(broken_pointers=["docs/x.md: broken"])
        assert r.has_problems

    def test_summary_contains_sections(self):
        r = DoctorReport(
            broken_pointers=["docs/a.md: bad pointer"],
            stale_index=True,
        )
        summary = "\n".join(r.summary_lines())
        assert "Broken pointers" in summary
        assert "stale" in summary.lower()


# ---------------------------------------------------------------------------
# run_doctor
# ---------------------------------------------------------------------------

class TestRunDoctor:
    def test_clean_project_no_problems(self, cfg, env):
        _make_valid_pair(env)
        entries = build_index(cfg, root=env)
        write_index(entries, cfg, root=env)
        report = run_doctor(cfg, root=env)
        assert not report.has_problems

    def test_detects_stale_index(self, cfg, env):
        _make_valid_pair(env)
        # Don't write index
        report = run_doctor(cfg, root=env)
        assert report.stale_index

    def test_detects_broken_pointer(self, cfg, env):
        doc = env / "docs" / "broken.md"
        write_frontmatter_file(doc, {"code": "src/ghost.py"}, "")
        entries = build_index(cfg, root=env)
        write_index(entries, cfg, root=env)
        report = run_doctor(cfg, root=env)
        assert report.broken_pointers

    def test_detects_orphaned_source(self, cfg, env):
        src = env / "src" / "lonely.py"
        src.write_text("def foo(): pass\n", encoding="utf-8")
        entries = build_index(cfg, root=env)
        write_index(entries, cfg, root=env)
        report = run_doctor(cfg, root=env)
        assert "src/lonely.py" in report.orphaned_sources

    def test_detects_unknown_tags(self, cfg, env):
        write_frontmatter_file(env / "docs" / "x.md", {"tags": ["notreal"]}, "")
        entries = build_index(cfg, root=env)
        write_index(entries, cfg, root=env)
        report = run_doctor(cfg, root=env)
        assert report.unknown_tag_entries

    def test_nonzero_exit_indicator(self, cfg, env):
        # Just verify has_problems is True when there are issues
        src = env / "src" / "lonely.py"
        src.write_text("def foo(): pass\n", encoding="utf-8")
        report = run_doctor(cfg, root=env)
        assert report.has_problems
