"""
dok-fu/tests/test_install.py - Unit tests for dok-fu/scripts/dokfu/install.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from dokfu.install import install


SOURCE_ROOT = Path(__file__).parent.parent


class TestInstall:
    def test_dokfu_py_entry_point_copied(self, tmp_path):
        install(target=tmp_path, source_root=SOURCE_ROOT)
        assert (tmp_path / "scripts" / "dokfu.py").exists()

    def test_dokfu_package_dir_copied(self, tmp_path):
        install(target=tmp_path, source_root=SOURCE_ROOT)
        assert (tmp_path / "scripts" / "dokfu").is_dir()

    def test_base_dir_copied(self, tmp_path):
        install(target=tmp_path, source_root=SOURCE_ROOT)
        assert (tmp_path / "base").is_dir()

    def test_config_dir_copied(self, tmp_path):
        install(target=tmp_path, source_root=SOURCE_ROOT)
        assert (tmp_path / "config").is_dir()

    def test_templates_dir_copied(self, tmp_path):
        install(target=tmp_path, source_root=SOURCE_ROOT)
        assert (tmp_path / "templates").is_dir()

    def test_docs_dir_created(self, tmp_path):
        install(target=tmp_path, source_root=SOURCE_ROOT)
        assert (tmp_path / "docs").is_dir()

    def test_copilot_instructions_generated(self, tmp_path):
        install(target=tmp_path, source_root=SOURCE_ROOT)
        assert (tmp_path / ".github" / "copilot-instructions.md").exists()

    def test_claude_md_generated(self, tmp_path):
        install(target=tmp_path, source_root=SOURCE_ROOT)
        assert (tmp_path / ".claude" / "CLAUDE.md").exists()

    def test_index_json_created(self, tmp_path):
        install(target=tmp_path, source_root=SOURCE_ROOT)
        assert (tmp_path / "docs" / "index.json").exists()
