"""
tests/test_pointers.py - Unit tests for scripts/dokfu/pointers.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from dokfu.common import load_config, write_frontmatter_file
from dokfu.pointers import (
    get_doc_code_pointer,
    get_section_paths,
    get_source_doc_pointer,
    validate_all_docs,
    validate_pair,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def env(tmp_path):
    cfg_data = {
        "docs_dir": "docs",
        "source_globs": ["**/*.py"],
        "exclude_globs": ["**/__pycache__/**"],
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
        json.dumps({"auth": "authentication"}), encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()
    return tmp_path


@pytest.fixture()
def cfg(env):
    return load_config(root=env)


def _make_valid_pair(env: Path) -> tuple[Path, Path]:
    """Create a valid module + source file pair.

    Module docs/src.md covers the src/ folder.
    src/auth.py has a pointer back to docs/src.md.
    """
    doc = env / "docs" / "src.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "# Src\n\n"
        "## Sections\n- [auth.py](#auth-py)\n\n"
        "## auth.py\npath: src/auth.py\nHandles login.\n"
    )
    write_frontmatter_file(doc, {"code": "src", "tags": ["auth"], "description": "Auth."}, body)
    src = env / "src" / "auth.py"
    src.write_text("# dok-fu: docs/src.md\n\ndef login(): pass\n", encoding="utf-8")
    return doc, src


# ---------------------------------------------------------------------------
# get_doc_code_pointer
# ---------------------------------------------------------------------------

class TestGetDocCodePointer:
    def test_returns_code_field(self, env):
        doc = env / "docs" / "x.md"
        write_frontmatter_file(doc, {"code": "src/x"}, "")
        assert get_doc_code_pointer(doc) == "src/x"

    def test_no_frontmatter_returns_none(self, env):
        doc = env / "docs" / "bare.md"
        doc.write_text("# Bare\n", encoding="utf-8")
        assert get_doc_code_pointer(doc) is None

    def test_missing_code_field_returns_none(self, env):
        doc = env / "docs" / "x.md"
        write_frontmatter_file(doc, {"description": "No code field"}, "")
        assert get_doc_code_pointer(doc) is None

    def test_nonexistent_file_returns_none(self, env):
        assert get_doc_code_pointer(env / "docs" / "ghost.md") is None


# ---------------------------------------------------------------------------
# get_source_doc_pointer
# ---------------------------------------------------------------------------

class TestGetSourceDocPointer:
    def test_finds_pointer_on_first_line(self, env, cfg):
        src = env / "src" / "a.py"
        src.write_text("# dok-fu: docs/src.md\n\ndef foo(): pass\n", encoding="utf-8")
        assert get_source_doc_pointer(src, cfg) == "docs/src.md"

    def test_finds_pointer_within_30_lines(self, env, cfg):
        content = "\n" * 25 + "# dok-fu: docs/src.md\n"
        src = env / "src" / "b.py"
        src.write_text(content, encoding="utf-8")
        assert get_source_doc_pointer(src, cfg) == "docs/src.md"

    def test_does_not_find_pointer_after_30_lines(self, env, cfg):
        content = "\n" * 31 + "# dok-fu: docs/src.md\n"
        src = env / "src" / "c.py"
        src.write_text(content, encoding="utf-8")
        assert get_source_doc_pointer(src, cfg) is None

    def test_no_pointer_returns_none(self, env, cfg):
        src = env / "src" / "d.py"
        src.write_text("def foo(): pass\n", encoding="utf-8")
        assert get_source_doc_pointer(src, cfg) is None


# ---------------------------------------------------------------------------
# validate_pair
# ---------------------------------------------------------------------------

class TestValidatePair:
    def test_valid_pair(self, env, cfg):
        doc, src = _make_valid_pair(env)
        result = validate_pair(doc, cfg, root=env)
        assert result.is_valid
        assert result.doc_has_code_field
        assert result.source_has_pointer
        assert result.pair_agrees

    def test_missing_code_field(self, env, cfg):
        doc = env / "docs" / "x.md"
        write_frontmatter_file(doc, {"description": "No code"}, "")
        result = validate_pair(doc, cfg, root=env)
        assert not result.is_valid
        assert any("code" in issue for issue in result.issues)

    def test_code_points_to_missing_folder(self, env, cfg):
        # code: field points to a non-existent directory
        doc = env / "docs" / "x.md"
        write_frontmatter_file(doc, {"code": "src/ghost"}, "")
        result = validate_pair(doc, cfg, root=env)
        assert not result.is_valid
        assert any("non-existent" in issue for issue in result.issues)

    def test_source_missing_pointer(self, env, cfg):
        # src/ folder exists but its files have no pointer back to the module
        doc = env / "docs" / "src.md"
        write_frontmatter_file(doc, {"code": "src"}, "")
        src = env / "src" / "x.py"
        src.write_text("def foo(): pass\n", encoding="utf-8")
        result = validate_pair(doc, cfg, root=env)
        assert not result.is_valid
        assert any("pointer" in issue for issue in result.issues)

    def test_pointer_mismatch(self, env, cfg):
        # Source file has a pointer but it points to a different doc
        doc = env / "docs" / "src.md"
        write_frontmatter_file(doc, {"code": "src"}, "")
        src = env / "src" / "x.py"
        src.write_text("# dok-fu: docs/other.md\n", encoding="utf-8")
        result = validate_pair(doc, cfg, root=env)
        assert not result.is_valid
        assert any("pointer" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# validate_all_docs
# ---------------------------------------------------------------------------

class TestValidateAllDocs:
    def test_empty_docs_dir(self, env, cfg):
        assert validate_all_docs(cfg, root=env) == []

    def test_returns_result_per_doc(self, env, cfg):
        _make_valid_pair(env)
        results = validate_all_docs(cfg, root=env)
        assert len(results) == 1

    def test_mixed_valid_and_invalid(self, env, cfg):
        _make_valid_pair(env)
        # Add a broken doc pointing to a non-existent folder
        bad = env / "docs" / "bad.md"
        write_frontmatter_file(bad, {"code": "src/ghost"}, "")
        results = validate_all_docs(cfg, root=env)
        assert len(results) == 2
        valid_count = sum(1 for r in results if r.is_valid)
        invalid_count = sum(1 for r in results if not r.is_valid)
        assert valid_count == 1
        assert invalid_count == 1


# ---------------------------------------------------------------------------
# get_section_paths
# ---------------------------------------------------------------------------

class TestGetSectionPaths:
    def test_returns_paths_from_sections(self, env):
        body = (
            "# Module\n\n"
            "## Sections\n- [foo.py](#foo-py)\n- [bar.py](#bar-py)\n\n"
            "## foo.py\npath: src/foo.py\nDoes foo things.\n\n"
            "## bar.py\npath: src/bar.py\nDoes bar things.\n"
        )
        doc = env / "docs" / "src.md"
        write_frontmatter_file(doc, {"code": "src"}, body)
        paths = get_section_paths(doc)
        assert paths == ["src/foo.py", "src/bar.py"]

    def test_no_sections_returns_empty(self, env):
        doc = env / "docs" / "empty.md"
        write_frontmatter_file(doc, {"code": "src"}, "# Module\nNo sections.\n")
        assert get_section_paths(doc) == []

    def test_missing_file_returns_empty(self, env):
        assert get_section_paths(env / "docs" / "ghost.md") == []
