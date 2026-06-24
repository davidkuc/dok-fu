"""
dok-fu/tests/test_changes.py - Unit tests for dok-fu/scripts/dokfu/changes.py
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from dokfu.common import load_config
from dokfu.changes import (
    get_changed_files,
    read_manifest,
    update_manifest,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def env(tmp_path):
    cfg_data = {
        "docs_dir": "docs",
        "source_globs": ["**/*.py"],
        "exclude_globs": ["**/__pycache__/**", "docs/**"],
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
        json.dumps({"auth": "authentication"}), encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()
    return tmp_path


@pytest.fixture()
def cfg(env):
    return load_config(root=env)


def _write_source(env, rel, content="# source\n"):
    p = env / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# read_manifest / update_manifest
# ---------------------------------------------------------------------------

class TestManifest:
    def test_read_missing_returns_empty(self, cfg, env):
        assert read_manifest(cfg, root=env) == {}

    def test_update_writes_hashes(self, cfg, env):
        src = _write_source(env, "src/app.py")
        manifest = update_manifest(cfg, root=env)
        assert "src/app.py" in manifest
        assert len(manifest["src/app.py"]) == 64  # hex sha256

    def test_update_is_deterministic(self, cfg, env):
        _write_source(env, "src/app.py")
        m1 = update_manifest(cfg, root=env)
        m2 = update_manifest(cfg, root=env)
        assert m1 == m2

    def test_update_explicit_paths(self, cfg, env):
        src = _write_source(env, "src/app.py")
        manifest = update_manifest(cfg, root=env, paths=[src])
        assert "src/app.py" in manifest

    def test_read_after_update(self, cfg, env):
        _write_source(env, "src/app.py")
        written = update_manifest(cfg, root=env)
        read = read_manifest(cfg, root=env)
        assert written == read

    def test_creates_docs_dir(self, cfg, env):
        import shutil
        shutil.rmtree(env / "docs")
        _write_source(env, "src/app.py")
        update_manifest(cfg, root=env)
        assert (env / "docs" / ".dokfu-manifest.json").exists()


# ---------------------------------------------------------------------------
# get_changed_files (manifest path - no git)
# ---------------------------------------------------------------------------

class TestGetChangedFilesManifest:
    def _no_git(self):
        """Context manager that disables git detection."""
        return patch("dokfu.changes._git_is_available", return_value=False)

    def test_all_new_files_are_changed(self, cfg, env):
        _write_source(env, "src/app.py")
        _write_source(env, "src/util.py")
        with self._no_git():
            changed, method = get_changed_files(cfg, root=env, force_manifest=True)
        assert method == "manifest"
        assert "src/app.py" in changed
        assert "src/util.py" in changed

    def test_unchanged_file_not_in_results(self, cfg, env):
        _write_source(env, "src/app.py")
        update_manifest(cfg, root=env)
        with self._no_git():
            changed, method = get_changed_files(cfg, root=env, force_manifest=True)
        assert "src/app.py" not in changed

    def test_modified_file_detected(self, cfg, env):
        src = _write_source(env, "src/app.py", "v1\n")
        update_manifest(cfg, root=env)
        src.write_text("v2\n", encoding="utf-8")  # modify after manifest
        with self._no_git():
            changed, method = get_changed_files(cfg, root=env, force_manifest=True)
        assert "src/app.py" in changed

    def test_force_manifest_skips_git(self, cfg, env):
        _write_source(env, "src/app.py")
        # Even if git would work, force_manifest should use manifest
        changed, method = get_changed_files(cfg, root=env, force_manifest=True)
        assert method == "manifest"

    def test_results_are_sorted(self, cfg, env):
        for name in ["z.py", "a.py", "m.py"]:
            _write_source(env, f"src/{name}")
        with self._no_git():
            changed, _ = get_changed_files(cfg, root=env, force_manifest=True)
        assert changed == sorted(changed)


# ---------------------------------------------------------------------------
# get_changed_files (git path - mocked)
# ---------------------------------------------------------------------------

class TestGetChangedFilesGit:
    def test_uses_git_when_available(self, cfg, env):
        _write_source(env, "src/app.py")
        with (
            patch("dokfu.changes._git_is_available", return_value=True),
            patch("dokfu.changes._git_changed_files", return_value=["src/app.py"]) as mock_git,
        ):
            changed, method = get_changed_files(cfg, root=env, since="HEAD~1")
        assert method == "git"
        mock_git.assert_called_once()

    def test_default_ref_is_head_tilde_one(self, cfg, env):
        """Verify the default since ref is HEAD~1 (last commit)."""
        _write_source(env, "src/app.py")
        with (
            patch("dokfu.changes._git_is_available", return_value=True),
            patch("dokfu.changes._git_changed_files", return_value=["src/app.py"]) as mock_git,
        ):
            changed, method = get_changed_files(cfg, root=env)  # no since specified
        assert method == "git"
        mock_git.assert_called_once_with("HEAD~1", env)

    def test_falls_back_to_manifest_when_git_fails(self, cfg, env):
        _write_source(env, "src/app.py")
        with (
            patch("dokfu.changes._git_is_available", return_value=True),
            patch("dokfu.changes._git_changed_files", return_value=None),
        ):
            changed, method = get_changed_files(cfg, root=env)
        assert method == "manifest"

    def test_git_results_filtered_by_source_globs(self, cfg, env):
        # git returns a non-source file; it should be filtered out
        with (
            patch("dokfu.changes._git_is_available", return_value=True),
            patch(
                "dokfu.changes._git_changed_files",
                return_value=["src/app.py", "README.md"],
            ),
        ):
            changed, method = get_changed_files(cfg, root=env)
        assert method == "git"
        assert "README.md" not in changed
        assert "src/app.py" in changed
