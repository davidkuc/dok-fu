"""
generate.py - Generate .github/ and .claude/ AI tool scaffolding from base/.

Reads base/ as the single source of truth and emits:
  .github/skills/<name>/SKILL.md          (GitHub Copilot skill)
  .github/prompts/<name>.prompt.md        (GitHub Copilot prompt)
  .github/instructions/dok-fu.instructions.md
  .github/copilot-instructions.md
  .claude/skills/<name>/SKILL.md          (Claude Code skill)

Generation is idempotent: re-running produces byte-identical output for
unchanged inputs, so drift is detectable by comparing file hashes.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .common import load_config

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)(?:\r?\n)?---\r?\n?", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    """Return *text* with any leading YAML frontmatter block removed."""
    m = _FRONTMATTER_RE.match(text)
    return text[m.end():] if m else text


def _read_base_file(path: Path) -> str:
    """Read a base/ source file and return its raw text."""
    return path.read_text(encoding="utf-8")


def _write_if_changed(path: Path, content: str) -> bool:
    """Write *content* to *path* only if it differs from what is on disk.

    Returns True if the file was written (new or changed), False if identical.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _build_frontmatter(data: dict[str, Any]) -> str:
    """Serialise *data* as a YAML frontmatter block (``---\\n...\\n---\\n``)."""
    fm = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return f"---\n{fm}---\n"


def _first_heading(text: str) -> str:
    """Return the text of the first Markdown H1 heading in *text*, or ''."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


# ---------------------------------------------------------------------------
# Per-tool emitters
# ---------------------------------------------------------------------------

def _emit_github_skill(name: str, body: str, out_root: Path) -> bool:
    """Write .github/skills/<name>/SKILL.md for GitHub Copilot."""
    dest = out_root / ".github" / "skills" / name / "SKILL.md"
    return _write_if_changed(dest, body)


def _emit_github_prompt(name: str, body: str, out_root: Path) -> bool:
    """Write .github/prompts/<name>.prompt.md with Copilot prompt frontmatter."""
    title = _first_heading(body) or name
    fm = _build_frontmatter({"mode": "agent", "description": title})
    content = fm + _strip_frontmatter(body)
    dest = out_root / ".github" / "prompts" / f"{name}.prompt.md"
    return _write_if_changed(dest, content)


def _emit_claude_skill(name: str, body: str, out_root: Path) -> bool:
    """Write .claude/skills/<name>/SKILL.md with Claude frontmatter."""
    fm = _build_frontmatter({"type": "skill", "name": name})
    content = fm + _strip_frontmatter(body)
    dest = out_root / ".claude" / "skills" / name / "SKILL.md"
    return _write_if_changed(dest, content)


def _emit_github_instructions(body: str, out_root: Path, stem: str = "dok-fu") -> bool:
    """Write .github/instructions/<stem>.instructions.md with applyTo frontmatter."""
    fm = _build_frontmatter({"applyTo": "**"})
    content = fm + _strip_frontmatter(body)
    dest = out_root / ".github" / "instructions" / f"{stem}.instructions.md"
    return _write_if_changed(dest, content)


def _emit_copilot_instructions(body: str, out_root: Path) -> bool:
    """Write .github/copilot-instructions.md (plain, no frontmatter)."""
    content = _strip_frontmatter(body)
    dest = out_root / ".github" / "copilot-instructions.md"
    return _write_if_changed(dest, content)


def _emit_claude_instructions(body: str, out_root: Path) -> bool:
    """Write .claude/CLAUDE.md (raw markdown, no frontmatter)."""
    content = _strip_frontmatter(body)
    dest = out_root / ".claude" / "CLAUDE.md"
    return _write_if_changed(dest, content)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class GenerateResult:
    """Summary of a generate run."""

    def __init__(self) -> None:
        self.written: list[str] = []
        self.unchanged: list[str] = []

    def record(self, path: Path, changed: bool) -> None:
        (self.written if changed else self.unchanged).append(str(path))

    @property
    def total_files(self) -> int:
        return len(self.written) + len(self.unchanged)


def generate(
    config: dict[str, Any] | None = None,
    root: str | os.PathLike | None = None,
    *,
    out_root: str | os.PathLike | None = None,
    base_dir: str | os.PathLike | None = None,
) -> GenerateResult:
    """Generate .github/ and .claude/ from base/.

    Args:
        config: Loaded dok-fu config dict. Loaded from disk if not provided.
        root: Project root. Defaults to cwd.
        out_root: Where to write .github/ and .claude/.  Defaults to *root*.
        base_dir: Path to the base/ source directory.  Defaults to
            ``<root>/base``.

    Returns:
        :class:`GenerateResult` with lists of written and unchanged files.
    """
    root = Path(root or Path.cwd())
    if config is None:
        try:
            config = load_config(root=root)
        except FileNotFoundError:
            config = {"_root": str(root)}

    out = Path(out_root) if out_root else root
    base = Path(base_dir) if base_dir else root / "base"

    if not base.exists():
        raise FileNotFoundError(f"base/ directory not found: {base}")

    result = GenerateResult()

    # ------------------------------------------------------------------
    # Skills:  base/skills/<name>/SKILL.md → .github + .claude
    # ------------------------------------------------------------------
    skills_dir = base / "skills"
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            name = skill_dir.name
            body = _read_base_file(skill_file)

            changed = _emit_github_skill(name, body, out)
            result.record(out / ".github" / "skills" / name / "SKILL.md", changed)

            changed = _emit_claude_skill(name, body, out)
            result.record(out / ".claude" / "skills" / name / "SKILL.md", changed)

    # ------------------------------------------------------------------
    # Prompts:  base/prompts/<name>.md → .github/prompts/<name>.prompt.md
    # ------------------------------------------------------------------
    prompts_dir = base / "prompts"
    if prompts_dir.exists():
        for prompt_file in sorted(prompts_dir.glob("*.md")):
            name = prompt_file.stem
            body = _read_base_file(prompt_file)

            changed = _emit_github_prompt(name, body, out)
            result.record(out / ".github" / "prompts" / f"{name}.prompt.md", changed)

    # ------------------------------------------------------------------
    # Instructions:  base/instructions/<stem>.md → per-file output + copilot-instructions
    # ------------------------------------------------------------------
    instructions_dir = base / "instructions"
    instruction_bodies: list[str] = []
    if instructions_dir.exists():
        for instr_file in sorted(instructions_dir.glob("*.md")):
            stem = instr_file.stem
            body = _read_base_file(instr_file)
            instruction_bodies.append(body)

            # Per-file GitHub instructions: base/instructions/<stem>.md → .github/instructions/<stem>.instructions.md
            changed = _emit_github_instructions(body, out, stem=stem)
            result.record(
                out / ".github" / "instructions" / f"{stem}.instructions.md", changed
            )

        # Concatenate all instruction bodies for copilot-instructions.md and .claude/CLAUDE.md
        if instruction_bodies:
            combined_body = "\n\n---\n\n".join(b.rstrip() for b in instruction_bodies) + "\n"
            changed = _emit_copilot_instructions(combined_body, out)
            result.record(out / ".github" / "copilot-instructions.md", changed)

            changed = _emit_claude_instructions(combined_body, out)
            result.record(out / ".claude" / "CLAUDE.md", changed)

    return result
