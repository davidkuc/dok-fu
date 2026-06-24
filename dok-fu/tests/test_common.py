"""
dok-fu/tests/test_common.py - Unit tests for dok-fu/scripts/dokfu/common.py
"""

import json
import sys
import textwrap
from pathlib import Path

import pytest

# Make the dok-fu/scripts/ directory importable when running from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from dokfu.common import (
    build_pointer_line,
    comment_for_ext,
    load_config,
    map_doc_to_source,
    map_source_to_doc,
    parse_pointer_line,
    read_frontmatter,
    read_frontmatter_file,
    sha256_file,
    slugify_for_dokfu_id,
    walk_sources,
    write_frontmatter,
    write_frontmatter_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def config_dir(tmp_path):
    """Create a minimal dok-fu config + registry in a temp directory."""
    cfg = {
        "docs_dir": "docs",
        "source_globs": ["**/*.py", "**/*.js"],
        "exclude_globs": ["**/node_modules/**", "**/__pycache__/**"],
        "pointer_token": "dok-fu",
        "comment_map": {".py": "#", ".js": "//"},
        "registry_path": "dok-fu/config/tags.registry.json",
        "manifest_path": "docs/.dokfu-manifest.json",
        "dokfu_dir": "dok-fu",
        "output_root": ".",
    }
    (tmp_path / "dok-fu" / "config").mkdir(parents=True)
    (tmp_path / "dok-fu" / "config" / "dok-fu.config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (tmp_path / "dok-fu" / "config" / "tags.registry.json").write_text(
        json.dumps({"auth": "authentication", "cli": "command-line interface"}),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def cfg(config_dir):
    """Return the loaded config dict (root = config_dir)."""
    return load_config(root=config_dir)


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_loads_successfully(self, config_dir):
        cfg = load_config(root=config_dir)
        assert cfg["docs_dir"] == "docs"
        assert cfg["pointer_token"] == "dok-fu"

    def test_injects_root(self, config_dir):
        cfg = load_config(root=config_dir)
        assert "_root" in cfg
        assert Path(cfg["_root"]) == config_dir

    def test_missing_config_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(root=tmp_path)

    def test_explicit_config_path(self, config_dir):
        explicit = config_dir / "dok-fu" / "config" / "dok-fu.config.json"
        cfg = load_config(config_path=explicit)
        assert cfg["docs_dir"] == "docs"


# ---------------------------------------------------------------------------
# read_frontmatter / write_frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_parse_valid(self):
        text = textwrap.dedent("""\
            ---
            dokfu_id: my-module
            code: src/auth
            tags: [auth, cli]
            description: Handles login flow.
            ---
            # My Module
            Body text here.
        """)
        fm, body = read_frontmatter(text)
        assert fm["dokfu_id"] == "my-module"
        assert fm["code"] == "src/auth"
        assert fm["tags"] == ["auth", "cli"]
        assert body.startswith("# My Module")

    def test_no_frontmatter(self):
        text = "# Just a heading\nNo frontmatter here.\n"
        fm, body = read_frontmatter(text)
        assert fm == {}
        assert body == text

    def test_empty_frontmatter(self):
        text = "---\n---\nBody\n"
        fm, body = read_frontmatter(text)
        assert fm == {}
        assert body == "Body\n"

    def test_invalid_yaml_raises(self):
        text = "---\n: bad: yaml:\n---\nBody\n"
        with pytest.raises(ValueError, match="Invalid YAML frontmatter"):
            read_frontmatter(text)

    def test_roundtrip(self):
        fm = {"code": "src/foo", "tags": ["cli"], "description": "A thing."}
        body = "# Foo\nSome content.\n"
        result = write_frontmatter(fm, body)
        parsed_fm, parsed_body = read_frontmatter(result)
        assert parsed_fm == fm
        assert parsed_body == body

    def test_file_roundtrip(self, tmp_path):
        path = tmp_path / "module.md"
        fm = {"code": "src/bar", "tags": ["io"]}
        body = "# Bar\n"
        write_frontmatter_file(path, fm, body)
        parsed_fm, parsed_body = read_frontmatter_file(path)
        assert parsed_fm == fm
        assert parsed_body == body


# ---------------------------------------------------------------------------
# walk_sources
# ---------------------------------------------------------------------------

class TestWalkSources:
    def _make_tree(self, root):
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text("# app", encoding="utf-8")
        (root / "src" / "util.js").write_text("// util", encoding="utf-8")
        (root / "src" / "README.md").write_text("# readme", encoding="utf-8")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "lib.js").write_text("", encoding="utf-8")
        return root

    def test_includes_matching_extensions(self, cfg, config_dir):
        self._make_tree(config_dir)
        paths = list(walk_sources(cfg, root=config_dir))
        names = {p.name for p in paths}
        assert "app.py" in names
        assert "util.js" in names

    def test_excludes_markdown(self, cfg, config_dir):
        self._make_tree(config_dir)
        paths = list(walk_sources(cfg, root=config_dir))
        names = {p.name for p in paths}
        assert "README.md" not in names

    def test_excludes_node_modules(self, cfg, config_dir):
        self._make_tree(config_dir)
        paths = list(walk_sources(cfg, root=config_dir))
        names = {p.name for p in paths}
        assert "lib.js" not in names

    def test_yields_absolute_paths(self, cfg, config_dir):
        self._make_tree(config_dir)
        for p in walk_sources(cfg, root=config_dir):
            assert p.is_absolute()


# ---------------------------------------------------------------------------
# map_source_to_doc / map_doc_to_source
# ---------------------------------------------------------------------------

class TestPathMapping:
    def test_source_to_doc(self, cfg, config_dir):
        source = config_dir / "src" / "auth.py"
        doc = map_source_to_doc(source, cfg, root=config_dir)
        assert doc == config_dir / "docs" / "src.md"

    def test_source_to_doc_relative(self, cfg, config_dir):
        doc = map_source_to_doc(Path("src/auth.py"), cfg, root=config_dir)
        assert doc == config_dir / "docs" / "src.md"

    def test_source_to_doc_nested(self, cfg, config_dir):
        source = config_dir / "src" / "auth" / "login.py"
        doc = map_source_to_doc(source, cfg, root=config_dir)
        assert doc == config_dir / "docs" / "src" / "auth.md"

    def test_source_to_doc_root_level_file(self, cfg, config_dir):
        source = config_dir / "app.py"
        doc = map_source_to_doc(source, cfg, root=config_dir)
        assert doc == config_dir / "docs" / "root.md"

    def test_doc_to_source_via_frontmatter(self, cfg, config_dir):
        docs_path = config_dir / "docs" / "src.md"
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        write_frontmatter_file(docs_path, {"code": "src"}, "# Src\n")
        result = map_doc_to_source(docs_path, cfg, root=config_dir)
        assert result == config_dir / "src"

    def test_doc_to_source_via_filesystem(self, cfg, config_dir):
        # No frontmatter; source folder exists on disk
        src_folder = config_dir / "src" / "util"
        src_folder.mkdir(parents=True, exist_ok=True)
        docs_path = config_dir / "docs" / "src" / "util.md"
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        docs_path.write_text("# Util\n", encoding="utf-8")
        result = map_doc_to_source(docs_path, cfg, root=config_dir)
        assert result == src_folder

    def test_doc_to_source_no_match(self, cfg, config_dir):
        # No frontmatter and no matching folder on disk
        docs_path = config_dir / "docs" / "src" / "ghost.md"
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        docs_path.write_text("# Ghost\n", encoding="utf-8")
        result = map_doc_to_source(docs_path, cfg, root=config_dir)
        assert result is None


# ---------------------------------------------------------------------------
# comment_for_ext / build_pointer_line / parse_pointer_line
# ---------------------------------------------------------------------------

class TestPointers:
    def test_comment_for_py(self, cfg):
        assert comment_for_ext(".py", cfg) == "#"

    def test_comment_for_js(self, cfg):
        assert comment_for_ext(".js", cfg) == "//"

    def test_comment_for_unknown(self, cfg):
        assert comment_for_ext(".xyz", cfg) is None

    def test_comment_without_leading_dot(self, cfg):
        assert comment_for_ext("py", cfg) == "#"

    def test_build_pointer_line_py(self, cfg, config_dir):
        doc = config_dir / "docs" / "src" / "auth.md"
        line = build_pointer_line(doc, ".py", cfg, root=config_dir)
        assert line == "# dok-fu: docs/src/auth.md"

    def test_build_pointer_line_js(self, cfg, config_dir):
        doc = config_dir / "docs" / "lib" / "helper.md"
        line = build_pointer_line(doc, ".js", cfg, root=config_dir)
        assert line == "// dok-fu: docs/lib/helper.md"

    def test_build_pointer_line_unknown_ext(self, cfg, config_dir):
        doc = config_dir / "docs" / "src" / "auth.md"
        assert build_pointer_line(doc, ".xyz", cfg, root=config_dir) is None

    def test_parse_pointer_line_py(self, cfg):
        line = "# dok-fu: docs/src/auth.md"
        assert parse_pointer_line(line, cfg) == "docs/src/auth.md"

    def test_parse_pointer_line_js(self, cfg):
        line = "// dok-fu: docs/lib/helper.md"
        assert parse_pointer_line(line, cfg) == "docs/lib/helper.md"

    def test_parse_pointer_line_not_a_pointer(self, cfg):
        assert parse_pointer_line("# just a comment", cfg) is None

    def test_parse_pointer_line_wrong_token(self, cfg):
        assert parse_pointer_line("# other-tool: docs/foo.md", cfg) is None

    def test_pointer_roundtrip(self, cfg, config_dir):
        doc = config_dir / "docs" / "src" / "auth.md"
        line = build_pointer_line(doc, ".py", cfg, root=config_dir)
        parsed = parse_pointer_line(line, cfg)
        assert parsed == "docs/src/auth.md"


# ---------------------------------------------------------------------------
# sha256_file
# ---------------------------------------------------------------------------

class TestSha256File:
    def test_deterministic(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"hello world")
        assert sha256_file(f) == sha256_file(f)

    def test_different_content(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_bytes(b"hello")
        b.write_bytes(b"world")
        assert sha256_file(a) != sha256_file(b)

    def test_known_hash(self, tmp_path):
        import hashlib
        data = b"dok-fu"
        f = tmp_path / "data.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert sha256_file(f) == expected


# ---------------------------------------------------------------------------
# slugify_for_dokfu_id (C3)
# ---------------------------------------------------------------------------

class TestSlugifyForDokfuId:
    def test_simple_folder(self):
        assert slugify_for_dokfu_id("src") == "src"

    def test_nested_slash(self):
        assert slugify_for_dokfu_id("src/auth") == "src-auth"

    def test_dot_in_path(self):
        assert slugify_for_dokfu_id("src.util") == "src-util"

    def test_backslash(self):
        assert slugify_for_dokfu_id("src\\auth") == "src-auth"

    def test_deep_path(self):
        assert slugify_for_dokfu_id("src/api/v2") == "src-api-v2"
