"""
tests/test_generate.py - Unit tests for scripts/dokfu/generate.py

Verifies:
- Skills are emitted to both .github and .claude with correct content/frontmatter.
- Prompts are emitted to .github/prompts/ with Copilot frontmatter.
- Instructions are emitted with applyTo frontmatter and as copilot-instructions.md.
- Generation is idempotent (byte-identical on repeated runs).
- Drift detection: .github and .claude skill bodies match base.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from dokfu.generate import generate, GenerateResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def base_dir(tmp_path: Path) -> Path:
    """Create a minimal base/ directory with one skill, one prompt, one instruction."""
    base = tmp_path / "base"

    # Skill
    skill_dir = base / "skills" / "traverse"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# Traverse\n\nTraverse the docs hierarchy.\n",
        encoding="utf-8",
    )

    # Prompt
    prompts_dir = base / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "traverse.md").write_text(
        "# Traverse\n\nApply the Traverse skill.\n",
        encoding="utf-8",
    )

    # Instructions
    instr_dir = base / "instructions"
    instr_dir.mkdir(parents=True)
    (instr_dir / "dok-fu.base.md").write_text(
        "# Dok-Fu Instructions\n\nSystem overview.\n",
        encoding="utf-8",
    )

    return base


@pytest.fixture()
def out_dir(tmp_path: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _read_frontmatter(path: Path) -> tuple[dict, str]:
    import re
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\r?\n(.*?)(?:\r?\n)?---\r?\n?", text, re.DOTALL)
    if not match:
        return {}, text
    fm = yaml.safe_load(match.group(1)) or {}
    body = text[match.end():]
    return fm, body


# ---------------------------------------------------------------------------
# Skill emission
# ---------------------------------------------------------------------------

class TestSkillEmission:
    def test_github_skill_written(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        dest = out_dir / ".github" / "skills" / "traverse" / "SKILL.md"
        assert dest.exists(), "GitHub skill file was not created"

    def test_github_skill_body_matches_base(self, base_dir, out_dir):
        """GitHub skill body must equal the base SKILL.md (no frontmatter added)."""
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        base_body = (base_dir / "skills" / "traverse" / "SKILL.md").read_text(encoding="utf-8")
        github_body = (out_dir / ".github" / "skills" / "traverse" / "SKILL.md").read_text(encoding="utf-8")
        assert github_body == base_body

    def test_claude_skill_written(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        dest = out_dir / ".claude" / "skills" / "traverse" / "SKILL.md"
        assert dest.exists(), "Claude skill file was not created"

    def test_claude_skill_has_frontmatter(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        dest = out_dir / ".claude" / "skills" / "traverse" / "SKILL.md"
        fm, _ = _read_frontmatter(dest)
        assert fm.get("type") == "skill"
        assert fm.get("name") == "traverse"

    def test_claude_skill_body_matches_base(self, base_dir, out_dir):
        """Claude skill body (after frontmatter) must match the base SKILL.md body."""
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        base_text = (base_dir / "skills" / "traverse" / "SKILL.md").read_text(encoding="utf-8")
        _, claude_body = _read_frontmatter(out_dir / ".claude" / "skills" / "traverse" / "SKILL.md")
        assert claude_body == base_text

    def test_multiple_skills_emitted(self, tmp_path):
        base = tmp_path / "base"
        for name in ("enrich", "update", "traverse"):
            d = base / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"# {name.capitalize()}\n\nBody.\n", encoding="utf-8")
        out = tmp_path
        generate(root=out, out_root=out, base_dir=base)
        for name in ("enrich", "update", "traverse"):
            assert (out / ".github" / "skills" / name / "SKILL.md").exists()
            assert (out / ".claude" / "skills" / name / "SKILL.md").exists()


# ---------------------------------------------------------------------------
# Prompt emission
# ---------------------------------------------------------------------------

class TestPromptEmission:
    def test_github_prompt_written(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        dest = out_dir / ".github" / "prompts" / "traverse.prompt.md"
        assert dest.exists()

    def test_github_prompt_frontmatter(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        dest = out_dir / ".github" / "prompts" / "traverse.prompt.md"
        fm, _ = _read_frontmatter(dest)
        assert fm.get("mode") == "agent"
        assert "description" in fm

    def test_github_prompt_description_from_heading(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        dest = out_dir / ".github" / "prompts" / "traverse.prompt.md"
        fm, _ = _read_frontmatter(dest)
        assert fm["description"] == "Traverse"

    def test_github_prompt_body_matches_base(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        base_text = (base_dir / "prompts" / "traverse.md").read_text(encoding="utf-8")
        _, prompt_body = _read_frontmatter(out_dir / ".github" / "prompts" / "traverse.prompt.md")
        assert prompt_body == base_text


# ---------------------------------------------------------------------------
# Instructions emission
# ---------------------------------------------------------------------------

class TestInstructionsEmission:
    def test_github_instructions_written(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        dest = out_dir / ".github" / "instructions" / "dok-fu.instructions.md"
        assert dest.exists()

    def test_github_instructions_apply_to(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        dest = out_dir / ".github" / "instructions" / "dok-fu.instructions.md"
        fm, _ = _read_frontmatter(dest)
        assert fm.get("applyTo") == "**"

    def test_copilot_instructions_written(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        dest = out_dir / ".github" / "copilot-instructions.md"
        assert dest.exists()

    def test_copilot_instructions_no_frontmatter(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        dest = out_dir / ".github" / "copilot-instructions.md"
        text = dest.read_text(encoding="utf-8")
        assert not text.startswith("---"), "copilot-instructions.md should have no frontmatter"

    def test_instructions_body_matches_base(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        base_text = (base_dir / "instructions" / "dok-fu.base.md").read_text(encoding="utf-8")
        _, instr_body = _read_frontmatter(
            out_dir / ".github" / "instructions" / "dok-fu.instructions.md"
        )
        assert instr_body == base_text
        copilot_text = (out_dir / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
        assert copilot_text == base_text


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_repeated_generate_identical_output(self, base_dir, out_dir):
        """Running generate twice must produce byte-identical files."""
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)

        def collect_hashes(root: Path) -> dict[str, bytes]:
            out = {}
            for p in root.rglob("*"):
                if p.is_file():
                    out[str(p.relative_to(root))] = p.read_bytes()
            return out

        first_hashes = collect_hashes(out_dir)
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        second_hashes = collect_hashes(out_dir)

        assert first_hashes == second_hashes

    def test_second_run_reports_unchanged(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        result = generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        assert result.written == [], f"Expected no new writes, got: {result.written}"
        assert len(result.unchanged) > 0

    def test_modified_base_triggers_rewrite(self, base_dir, out_dir):
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        # Modify base skill
        skill_file = base_dir / "skills" / "traverse" / "SKILL.md"
        skill_file.write_text("# Traverse\n\nUpdated body.\n", encoding="utf-8")
        result = generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        written_names = [Path(p).name for p in result.written]
        assert "SKILL.md" in written_names


# ---------------------------------------------------------------------------
# Drift detection: .github vs .claude skill bodies match base
# ---------------------------------------------------------------------------

class TestDriftDetection:
    def test_github_skill_body_matches_base_after_generate(self, base_dir, out_dir):
        """Drift check: GitHub skill body == base SKILL.md."""
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        base_body = (base_dir / "skills" / "traverse" / "SKILL.md").read_text(encoding="utf-8")
        github_body = (out_dir / ".github" / "skills" / "traverse" / "SKILL.md").read_text(encoding="utf-8")
        assert github_body == base_body, "GitHub SKILL.md drifted from base"

    def test_claude_skill_body_matches_base_after_generate(self, base_dir, out_dir):
        """Drift check: Claude skill body (minus frontmatter) == base SKILL.md."""
        generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        base_body = (base_dir / "skills" / "traverse" / "SKILL.md").read_text(encoding="utf-8")
        _, claude_body = _read_frontmatter(out_dir / ".claude" / "skills" / "traverse" / "SKILL.md")
        assert claude_body == base_body, "Claude SKILL.md body drifted from base"

    def test_generate_result_has_expected_files(self, base_dir, out_dir):
        result = generate(root=out_dir, out_root=out_dir, base_dir=base_dir)
        all_paths = result.written + result.unchanged
        file_names = {Path(p).name for p in all_paths}
        assert "SKILL.md" in file_names
        assert "traverse.prompt.md" in file_names
        assert "dok-fu.instructions.md" in file_names
        assert "copilot-instructions.md" in file_names
