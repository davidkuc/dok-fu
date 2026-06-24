"""
dok-fu/tests/test_index.py - Unit tests for dok-fu/scripts/dokfu/index.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from dokfu.common import load_config, write_frontmatter_file
from dokfu.index import build_index, is_index_stale, read_index, write_index


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def env(tmp_path):
    """Set up a minimal project environment with config and empty docs/."""
    cfg_data = {
        "docs_dir": "docs",
        "source_globs": ["**/*.py"],
        "exclude_globs": ["**/__pycache__/**"],
        "pointer_token": "dok-fu",
        "comment_map": {".py": "#"},
        "registry_path": "dok-fu/config/tags.registry.json",
        "manifest_path": "docs/.dokfu-manifest.json",
        "dokfu_dir": "dok-fu",
        "output_root": ".",
    }
    (tmp_path / "dok-fu" / "config").mkdir(parents=True)
    (tmp_path / "dok-fu" / "config" / "dok-fu.config.json").write_text(
        json.dumps(cfg_data), encoding="utf-8"
    )
    (tmp_path / "dok-fu" / "config" / "tags.registry.json").write_text(
        json.dumps({"auth": "authentication", "cli": "command-line"}),
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    return tmp_path


@pytest.fixture()
def cfg(env):
    return load_config(root=env)


# ---------------------------------------------------------------------------
# build_index
# ---------------------------------------------------------------------------

class TestBuildIndex:
    def test_empty_docs_dir(self, cfg, env):
        entries = build_index(cfg, root=env)
        assert entries == []

    def test_picks_up_frontmatter(self, cfg, env):
        doc = env / "docs" / "auth.md"
        write_frontmatter_file(
            doc,
            {"code": "src/auth", "tags": ["auth"], "description": "Handles auth."},
            "# Auth\n",
        )
        entries = build_index(cfg, root=env)
        assert len(entries) == 1
        assert entries[0]["path"] == "docs/auth.md"
        assert entries[0]["tags"] == ["auth"]
        assert entries[0]["description"] == "Handles auth."

    def test_file_with_no_frontmatter(self, cfg, env):
        (env / "docs" / "bare.md").write_text("# Bare\n", encoding="utf-8")
        entries = build_index(cfg, root=env)
        assert entries[0]["tags"] == []
        assert entries[0]["description"] == ""

    def test_skips_hidden_files(self, cfg, env):
        (env / "docs" / ".hidden.md").write_text("---\ndescription: hidden\n---\n", encoding="utf-8")
        entries = build_index(cfg, root=env)
        assert all(".hidden" not in e["path"] for e in entries)

    def test_multiple_docs_sorted(self, cfg, env):
        for name in ["z.md", "a.md", "m.md"]:
            write_frontmatter_file(
                env / "docs" / name,
                {"description": name},
                "",
            )
        entries = build_index(cfg, root=env)
        paths = [e["path"] for e in entries]
        assert paths == sorted(paths)

    def test_missing_docs_dir(self, cfg, env):
        (env / "docs").rmdir()
        assert build_index(cfg, root=env) == []


# ---------------------------------------------------------------------------
# write_index / read_index
# ---------------------------------------------------------------------------

class TestWriteReadIndex:
    def test_roundtrip(self, cfg, env):
        entries = [{"path": "docs/a.md", "tags": ["cli"], "description": "A."}]
        write_index(entries, cfg, root=env)
        result = read_index(cfg, root=env)
        assert result == entries

    def test_creates_docs_dir_if_needed(self, cfg, env):
        import shutil
        shutil.rmtree(env / "docs")
        entries = [{"path": "docs/x.md", "tags": [], "description": ""}]
        write_index(entries, cfg, root=env)
        assert (env / "docs" / "index.json").exists()

    def test_read_missing_returns_empty(self, cfg, env):
        assert read_index(cfg, root=env) == []

    def test_read_empty_file_returns_empty(self, cfg, env):
        (env / "docs" / "index.json").write_bytes(b"")
        assert read_index(cfg, root=env) == []

    def test_read_malformed_json_returns_empty(self, cfg, env):
        (env / "docs" / "index.json").write_text("not json", encoding="utf-8")
        assert read_index(cfg, root=env) == []


# ---------------------------------------------------------------------------
# is_index_stale
# ---------------------------------------------------------------------------

class TestIsIndexStale:
    def test_stale_when_index_missing(self, cfg, env):
        write_frontmatter_file(env / "docs" / "x.md", {"description": "X"}, "")
        assert is_index_stale(cfg, root=env) is True

    def test_not_stale_when_current(self, cfg, env):
        write_frontmatter_file(env / "docs" / "x.md", {"description": "X"}, "")
        entries = build_index(cfg, root=env)
        write_index(entries, cfg, root=env)
        assert is_index_stale(cfg, root=env) is False

    def test_stale_after_new_doc_added(self, cfg, env):
        write_frontmatter_file(env / "docs" / "x.md", {"description": "X"}, "")
        entries = build_index(cfg, root=env)
        write_index(entries, cfg, root=env)
        write_frontmatter_file(env / "docs" / "y.md", {"description": "Y"}, "")
        assert is_index_stale(cfg, root=env) is True
