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
    RenameCandidate,
    check_cross_folder_pointers,
    check_folder_pointer_consistency,
    check_missing_frontmatter,
    check_orphaned_sources,
    check_pointers,
    check_renamed_docs,
    check_section_paths,
    check_unknown_tags,
    fix_pointers,
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
    from dokfu.common import slugify_for_dokfu_id
    src_folder = str(PurePosixPath(rel_src).parent)
    doc = env / rel_doc
    doc.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"# {src_folder}\n\n"
        f"## Sections\n- [auth.py](src/auth.py)\n\n"
        f"## auth.py\npath: {rel_src}\nHandles auth.\n"
    )
    dokfu_id = slugify_for_dokfu_id(src_folder)
    write_frontmatter_file(
        doc,
        {"code": src_folder, "tags": ["auth"], "description": "Auth module.", "dokfu_id": dokfu_id},
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


# ---------------------------------------------------------------------------
# check_cross_folder_pointers (B1)
# ---------------------------------------------------------------------------

class TestCheckCrossFolderPointers:
    def test_no_sources_no_violations(self, cfg, env):
        assert check_cross_folder_pointers(cfg, root=env) == []

    def test_valid_pair_no_violation(self, cfg, env):
        _make_valid_pair(env)
        assert check_cross_folder_pointers(cfg, root=env) == []

    def test_cross_folder_violation_detected(self, cfg, env):
        # doc covers 'src' but the source file is placed in 'src/sub'
        doc = env / "docs" / "src.md"
        write_frontmatter_file(
            doc,
            {"code": "src", "tags": ["auth"], "description": "Src module."},
            "# src\n",
        )
        (env / "src" / "sub").mkdir(parents=True, exist_ok=True)
        src = env / "src" / "sub" / "auth.py"
        src.write_text("# dok-fu: docs/src.md\n", encoding="utf-8")
        violations = check_cross_folder_pointers(cfg, root=env)
        assert len(violations) == 1
        assert "src/sub/auth.py" in violations[0]

    def test_source_without_pointer_ignored(self, cfg, env):
        (env / "src" / "noop.py").write_text("def f(): pass\n", encoding="utf-8")
        assert check_cross_folder_pointers(cfg, root=env) == []

    def test_broken_pointer_skipped(self, cfg, env):
        # Pointer to non-existent doc — should not raise, just skip
        src = env / "src" / "x.py"
        src.write_text("# dok-fu: docs/ghost.md\n", encoding="utf-8")
        result = check_cross_folder_pointers(cfg, root=env)
        assert result == []


# ---------------------------------------------------------------------------
# check_folder_pointer_consistency (B2)
# ---------------------------------------------------------------------------

class TestCheckFolderPointerConsistency:
    def test_no_sources_no_violations(self, cfg, env):
        assert check_folder_pointer_consistency(cfg, root=env) == []

    def test_same_pointer_no_violation(self, cfg, env):
        for name in ["a.py", "b.py"]:
            (env / "src" / name).write_text(
                "# dok-fu: docs/src.md\n", encoding="utf-8"
            )
        assert check_folder_pointer_consistency(cfg, root=env) == []

    def test_different_pointers_flagged(self, cfg, env):
        (env / "src" / "a.py").write_text(
            "# dok-fu: docs/src.md\n", encoding="utf-8"
        )
        (env / "src" / "b.py").write_text(
            "# dok-fu: docs/other.md\n", encoding="utf-8"
        )
        violations = check_folder_pointer_consistency(cfg, root=env)
        assert len(violations) == 1
        assert "src" in violations[0]
        assert "docs/src.md" in violations[0]
        assert "docs/other.md" in violations[0]

    def test_separate_folders_independent(self, cfg, env):
        (env / "src" / "a.py").write_text(
            "# dok-fu: docs/src.md\n", encoding="utf-8"
        )
        (env / "src" / "sub").mkdir()
        (env / "src" / "sub" / "b.py").write_text(
            "# dok-fu: docs/sub.md\n", encoding="utf-8"
        )
        assert check_folder_pointer_consistency(cfg, root=env) == []


# ---------------------------------------------------------------------------
# check_section_paths (B3)
# ---------------------------------------------------------------------------

class TestCheckSectionPaths:
    def test_no_docs_no_issues(self, cfg, env):
        assert check_section_paths(cfg, root=env) == []

    def test_existing_section_path_ok(self, cfg, env):
        src = env / "src" / "auth.py"
        src.write_text("# dok-fu: docs/src.md\n", encoding="utf-8")
        doc = env / "docs" / "src.md"
        write_frontmatter_file(
            doc,
            {"code": "src", "tags": ["auth"], "description": "Src."},
            "# src\n\n## auth.py\npath: src/auth.py\nHandles auth.\n",
        )
        assert check_section_paths(cfg, root=env) == []

    def test_missing_section_path_flagged(self, cfg, env):
        doc = env / "docs" / "src.md"
        write_frontmatter_file(
            doc,
            {"code": "src", "tags": ["auth"], "description": "Src."},
            "# src\n\n## ghost.py\npath: src/ghost.py\nMissing file.\n",
        )
        missing = check_section_paths(cfg, root=env)
        assert len(missing) == 1
        assert "src/ghost.py" in missing[0]

    def test_doc_with_no_sections_ok(self, cfg, env):
        doc = env / "docs" / "empty.md"
        write_frontmatter_file(doc, {"code": "src", "description": ".", "dokfu_id": "src"}, "# empty\n")
        assert check_section_paths(cfg, root=env) == []

    def test_section_path_within_code_folder_ok(self, cfg, env):
        (env / "src" / "auth").mkdir(parents=True, exist_ok=True)
        (env / "src" / "auth" / "login.py").write_text("# dok-fu: docs/src-auth.md\n", encoding="utf-8")
        doc = env / "docs" / "src-auth.md"
        write_frontmatter_file(
            doc,
            {"code": "src/auth", "tags": ["auth"], "description": "Auth.", "dokfu_id": "src-auth"},
            "# auth\n\n## login.py\npath: src/auth/login.py\nHandles login.\n",
        )
        assert check_section_paths(cfg, root=env) == []

    def test_section_path_outside_code_folder_flagged(self, cfg, env):
        (env / "src" / "auth").mkdir(parents=True, exist_ok=True)
        (env / "src" / "other").mkdir(parents=True, exist_ok=True)
        (env / "src" / "other" / "util.py").write_text("def f(): pass\n", encoding="utf-8")
        doc = env / "docs" / "src-auth.md"
        write_frontmatter_file(
            doc,
            {"code": "src/auth", "tags": ["auth"], "description": "Auth.", "dokfu_id": "src-auth"},
            "# auth\n\n## util.py\npath: src/other/util.py\nUtil.\n",
        )
        violations = check_section_paths(cfg, root=env)
        assert len(violations) == 1
        assert "src/other/util.py" in violations[0]
        assert "outside" in violations[0]


# ---------------------------------------------------------------------------
# check_missing_frontmatter (B4)
# ---------------------------------------------------------------------------

class TestCheckMissingFrontmatter:
    def test_no_docs_no_issues(self, cfg, env):
        assert check_missing_frontmatter(cfg, root=env) == []

    def test_complete_frontmatter_ok(self, cfg, env):
        write_frontmatter_file(
            env / "docs" / "x.md",
            {"code": "src", "description": "A module.", "tags": ["auth"], "dokfu_id": "src"},
            "",
        )
        assert check_missing_frontmatter(cfg, root=env) == []

    def test_missing_code_flagged(self, cfg, env):
        write_frontmatter_file(
            env / "docs" / "x.md",
            {"description": "A module.", "tags": ["auth"]},
            "",
        )
        results = check_missing_frontmatter(cfg, root=env)
        assert len(results) == 1
        path, fields = results[0]
        assert "code" in fields

    def test_missing_multiple_fields(self, cfg, env):
        write_frontmatter_file(env / "docs" / "x.md", {"code": "src"}, "")
        results = check_missing_frontmatter(cfg, root=env)
        assert len(results) == 1
        _, fields = results[0]
        assert "description" in fields
        assert "tags" in fields

    def test_missing_tags_flagged(self, cfg, env):
        write_frontmatter_file(
            env / "docs" / "x.md",
            {"code": "src", "description": "Desc."},
            "",
        )
        results = check_missing_frontmatter(cfg, root=env)
        assert len(results) == 1
        _, fields = results[0]
        assert "tags" in fields

    def test_missing_dokfu_id_flagged(self, cfg, env):
        write_frontmatter_file(
            env / "docs" / "x.md",
            {"code": "src", "description": "Desc.", "tags": ["auth"]},
            "",
        )
        results = check_missing_frontmatter(cfg, root=env)
        assert len(results) == 1
        _, fields = results[0]
        assert "dokfu_id" in fields

    def test_all_required_fields_present_ok(self, cfg, env):
        write_frontmatter_file(
            env / "docs" / "x.md",
            {"code": "src", "description": "Desc.", "tags": ["auth"], "dokfu_id": "src"},
            "",
        )
        assert check_missing_frontmatter(cfg, root=env) == []


# ---------------------------------------------------------------------------
# check_renamed_docs (C3)
# ---------------------------------------------------------------------------

def _make_doc_with_id(env: Path, rel_doc: str, code: str, dokfu_id: str) -> Path:
    """Write a doc module with the given frontmatter."""
    doc = env / rel_doc
    doc.parent.mkdir(parents=True, exist_ok=True)
    write_frontmatter_file(
        doc,
        {"dokfu_id": dokfu_id, "code": code, "tags": ["auth"], "description": "Module."},
        f"# {code}\n",
    )
    return doc


class TestCheckRenamedDocs:
    def test_no_sources_no_candidates(self, cfg, env):
        assert check_renamed_docs(cfg, root=env) == []

    def test_valid_pointer_no_candidate(self, cfg, env):
        _make_valid_pair(env)
        assert check_renamed_docs(cfg, root=env) == []

    def test_broken_pointer_with_matching_dokfu_id_detected(self, cfg, env):
        # Source points to docs/src.md which doesn't exist.
        # A doc at docs/src-renamed.md has dokfu_id 'src' (matching source folder).
        _make_doc_with_id(env, "docs/src-renamed.md", "src", "src")
        src = env / "src" / "auth.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("# dok-fu: docs/src.md\n", encoding="utf-8")
        candidates = check_renamed_docs(cfg, root=env)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.source_file == "src/auth.py"
        assert c.broken_pointer == "docs/src.md"
        assert c.candidate_doc == "docs/src-renamed.md"

    def test_broken_pointer_no_matching_dokfu_id_ignored(self, cfg, env):
        # Doc has a different dokfu_id — not a rename candidate.
        _make_doc_with_id(env, "docs/other.md", "other", "other")
        src = env / "src" / "auth.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("# dok-fu: docs/src.md\n", encoding="utf-8")
        candidates = check_renamed_docs(cfg, root=env)
        assert candidates == []

    def test_source_with_no_pointer_ignored(self, cfg, env):
        (env / "src" / "noop.py").write_text("def f(): pass\n", encoding="utf-8")
        assert check_renamed_docs(cfg, root=env) == []


# ---------------------------------------------------------------------------
# fix_pointers (C3)
# ---------------------------------------------------------------------------

class TestFixPointers:
    def test_no_candidates_no_updates(self, cfg, env):
        report = DoctorReport()
        updated = fix_pointers(report, cfg, root=env)
        assert updated == []

    def test_updates_pointer_in_source_file(self, cfg, env):
        _make_doc_with_id(env, "docs/src-new.md", "src", "src")
        src = env / "src" / "auth.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("# dok-fu: docs/src-old.md\n\ndef login(): pass\n", encoding="utf-8")
        candidate = RenameCandidate(
            source_file="src/auth.py",
            broken_pointer="docs/src-old.md",
            candidate_doc="docs/src-new.md",
        )
        report = DoctorReport(renamed=[candidate])
        updated = fix_pointers(report, cfg, root=env)
        assert "src/auth.py" in updated
        new_text = src.read_text(encoding="utf-8")
        assert "docs/src-new.md" in new_text
        assert "docs/src-old.md" not in new_text

    def test_preserves_rest_of_file(self, cfg, env):
        _make_doc_with_id(env, "docs/src-new.md", "src", "src")
        src = env / "src" / "auth.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        original = "# dok-fu: docs/src-old.md\n\ndef login(): pass\nfoo = 1\n"
        src.write_text(original, encoding="utf-8")
        candidate = RenameCandidate(
            source_file="src/auth.py",
            broken_pointer="docs/src-old.md",
            candidate_doc="docs/src-new.md",
        )
        report = DoctorReport(renamed=[candidate])
        fix_pointers(report, cfg, root=env)
        new_text = src.read_text(encoding="utf-8")
        assert "def login(): pass" in new_text
        assert "foo = 1" in new_text

    def test_run_doctor_includes_renamed(self, cfg, env):
        _make_doc_with_id(env, "docs/src-new.md", "src", "src")
        src = env / "src" / "auth.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("# dok-fu: docs/src-old.md\n", encoding="utf-8")
        report = run_doctor(cfg, root=env)
        assert len(report.renamed) == 1
        assert report.has_problems
