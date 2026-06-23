"""
tests/test_tags.py - Unit tests for scripts/dokfu/tags.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from dokfu.common import load_config, write_frontmatter_file
from dokfu.tags import list_tags, load_registry, search_by_tag, validate_tags


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def env(tmp_path):
    registry = {
        "auth": "authentication and authorization",
        "cli": "command-line interface",
        "io": "file and stream input/output",
    }
    cfg_data = {
        "docs_dir": "docs",
        "source_globs": ["**/*.py"],
        "exclude_globs": [],
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
    return tmp_path


@pytest.fixture()
def cfg(env):
    return load_config(root=env)


# ---------------------------------------------------------------------------
# load_registry / list_tags
# ---------------------------------------------------------------------------

class TestLoadRegistry:
    def test_returns_dict(self, cfg, env):
        reg = load_registry(cfg, root=env)
        assert isinstance(reg, dict)
        assert "auth" in reg

    def test_missing_registry_raises(self, cfg, env):
        (env / "config" / "tags.registry.json").unlink()
        with pytest.raises(FileNotFoundError):
            load_registry(cfg, root=env)

    def test_list_tags_same_as_load_registry(self, cfg, env):
        assert list_tags(cfg, root=env) == load_registry(cfg, root=env)


# ---------------------------------------------------------------------------
# search_by_tag
# ---------------------------------------------------------------------------

class TestSearchByTag:
    def _add_doc(self, env, name, tags):
        doc = env / "docs" / f"{name}.md"
        write_frontmatter_file(doc, {"tags": tags, "description": f"{name} doc."}, "")
        return doc

    def test_finds_matching_doc(self, cfg, env):
        self._add_doc(env, "login", ["auth", "cli"])
        results = search_by_tag("auth", cfg, root=env)
        assert "docs/login.md" in results

    def test_no_match_returns_empty(self, cfg, env):
        self._add_doc(env, "util", ["io"])
        results = search_by_tag("auth", cfg, root=env)
        assert results == []

    def test_multiple_matches(self, cfg, env):
        self._add_doc(env, "login", ["auth"])
        self._add_doc(env, "session", ["auth", "io"])
        results = search_by_tag("auth", cfg, root=env)
        assert len(results) == 2

    def test_unknown_tag_raises(self, cfg, env):
        with pytest.raises(ValueError, match="Unknown tag"):
            search_by_tag("nonexistent", cfg, root=env)

    def test_unknown_tag_no_validate(self, cfg, env):
        # Should not raise; returns empty since no doc has the tag
        results = search_by_tag("nonexistent", cfg, root=env, validate=False)
        assert results == []

    def test_results_are_sorted(self, cfg, env):
        self._add_doc(env, "z_module", ["auth"])
        self._add_doc(env, "a_module", ["auth"])
        results = search_by_tag("auth", cfg, root=env)
        assert results == sorted(results)

    def test_skips_docs_without_matching_tag(self, cfg, env):
        self._add_doc(env, "io_module", ["io"])
        results = search_by_tag("cli", cfg, root=env)
        assert "docs/io_module.md" not in results


# ---------------------------------------------------------------------------
# validate_tags
# ---------------------------------------------------------------------------

class TestValidateTags:
    def test_all_valid(self, cfg, env):
        assert validate_tags(["auth", "cli"], cfg, root=env) == []

    def test_unknown_tags_returned(self, cfg, env):
        unknown = validate_tags(["auth", "bogus", "fake"], cfg, root=env)
        assert set(unknown) == {"bogus", "fake"}

    def test_empty_list(self, cfg, env):
        assert validate_tags([], cfg, root=env) == []
