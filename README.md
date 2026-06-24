# Dok-Fu

Dok-Fu is a documentation workflow system that connects source code and documentation through two-way pointers, a searchable index, and a controlled tag vocabulary. It is designed for incremental, AI-assisted documentation that stays in sync with a living codebase.

---

## Pillars

**Terseness** — minimal verbosity, maximal signal. Every layer has hard limits:
- Index entries: 1 sentence description maximum
- Module sections: ≤ 3 sentences, ≤ 5 bullet points per H2 section
- Inline code comments: 1 sentence maximum

**Progressive Disclosure** — avoid loading unnecessary context. Information is layered from coarsest to finest:
1. `docs/index.json` — quickest lookup; tags and 1-sentence descriptions only
2. Doc modules (`docs/**/*.md`) — medium detail; section-level summaries
3. Code comments — high detail; granular descriptions inside source files
4. Source code — full detail; last resort

**Deterministic Foundation** — scripts handle traversal, extraction, and validation. AI handles reasoning, writing, and orchestration. Never implement what a script can do reliably or if a script already handles a certain problem.

**AI Augmenting** — AI uses scripts as tools. Scripts produce structured output; AI interprets, writes, and decides.

---

## Quickstart

### Install into a target project

```bash
# From the dok-fu source repo, install into <your-project>
python dok-fu/scripts/dokfu.py install --target /path/to/your-project
```

This scaffolds `.github/`, `.claude/`, `docs/`, `scripts/`, `base/`, and `config/` into the target.

### Day-to-day commands

```bash
# Regenerate .github/ and .claude/ from dok-fu/base/ (idempotent)
python dok-fu/scripts/dokfu.py generate

# Rebuild docs/index.json
python dok-fu/scripts/dokfu.py index

# Check if index is stale (exits 1 if yes)
python dok-fu/scripts/dokfu.py index --check

# List all registered tags
python dok-fu/scripts/dokfu.py tags --list

# Find docs tagged with a specific tag
python dok-fu/scripts/dokfu.py tags --search util

# Validate all pointers, tags, and index freshness
python dok-fu/scripts/dokfu.py doctor

# Validate and rebuild index if stale
python dok-fu/scripts/dokfu.py doctor --fix-index

# Validate and auto-repair broken doc↔code pointers
python dok-fu/scripts/dokfu.py doctor --fix-pointers

# List source files changed since last commit (HEAD~1 default)
python dok-fu/scripts/dokfu.py changes

# List changed files since a specific git ref
python dok-fu/scripts/dokfu.py changes --since main

# Install dok-fu into a target project
python dok-fu/scripts/dokfu.py install --target /path/to/your-project
```

---

## Architecture

```
dok-fu/
├── dok-fu/base/                         Single source for all AI tool output
│   ├── instructions/             System-level instructions (base)
│   ├── prompts/                  Invokable prompt wrappers
│   └── skills/                   Skill bodies (traverse, enrich, update)
├── dok-fu/config/
│   ├── dok-fu.config.json        Docs dir, source globs, comment map, paths
│   └── tags.registry.json        Controlled tag vocabulary
├── dok-fu/scripts/
│   ├── dokfu.py                  CLI entry point (argparse)
│   └── dokfu/                    Python package
│       ├── common.py             Config, frontmatter, path mapping, pointers
│       ├── index.py              Build/check docs/index.json
│       ├── pointers.py           Extract and validate doc↔code pointers
│       ├── tags.py               Tag registry: list and search
│       ├── changes.py            Changed-file detection (git + manifest)
│       ├── doctor.py             Validate everything, report problems
│       ├── generate.py           dok-fu/base/ → .github/ + .claude/ (idempotent)
│       └── install.py            Vendor dok-fu into a target project
├── dok-fu/templates/
│   └── module.md.tmpl            Template for new doc modules
├── dok-fu/tests/                        pytest unit tests
└── dok-fu/examples/
    └── sample/                   Minimal two-file project with complete docs
```

Generated into any target project:
```
<target>/
├── .github/
│   ├── copilot-instructions.md
│   ├── instructions/dok-fu.base.instructions.md
│   ├── prompts/{traverse,enrich,update}.prompt.md
│   └── skills/{traverse,enrich,update}/SKILL.md
└── .claude/
    ├── CLAUDE.md
    └── skills/{traverse,enrich,update}/SKILL.md
```

---

## Core Concepts

| Concept | Description |
|---|---|
| **module** | A `docs/<folder>.md` file documenting one source directory |
| **section** | An H2 in a module documenting one source file (`path:` first line) |
| **pointer** | Two-way link: `code:` in doc frontmatter ↔ `# dok-fu:` in source |
| **index** | `docs/index.json` — flat array of `{path, tags[], description}` |
| **tag** | Short label from `config/tags.registry.json` attached to a module |
| **drift** | State where docs no longer reflect source (detected by `dokfu doctor`) |
| **orphan** | Doc or source whose pointer target no longer exists |

See [dok-fu\base\GLOSSARY.md](dok-fu\base\GLOSSARY.md) for full definitions.

---

## Format Reference

See [dok-fu\base\FORMAT.md](dok-fu\base\FORMAT.md) for the canonical format specification covering doc module structure, frontmatter fields, code pointer syntax, and index entry format.

---

## AI Skills

| Skill | When to use |
|---|---|
| **Traverse** | Exploring unfamiliar code; navigates index → modules → comments → code |
| **Enrich** | New file added or gaps detected by `dokfu doctor`; fills missing docs |
| **Update** | Source changed; uses `dokfu changes` to find and sync stale docs |

### Choosing the right skill

- **Exploring unfamiliar code?** → Traverse
- **New file added / doc gaps detected by `dokfu doctor`?** → Enrich
- **`dokfu changes` returned a non-empty list?** → Update
- **Pointer broken / file renamed?** → Run `python dok-fu/scripts/dokfu.py doctor` to detect rename candidates via `dokfu_id` matching; run `python dok-fu/scripts/dokfu.py doctor --fix-pointers` to auto-repair pointer comments; then run `python dok-fu/scripts/dokfu.py index`

---

## Invariants

- Tags must always be from `config/tags.registry.json`. Never invent tags.
- `docs/index.json` is always regenerated by script, never edited by hand.
- A doc module and its source file must always point to each other (two-way).
- Terseness limits are hard constraints, not guidelines.

---

## Verification

```bash
# All unit tests
python -m pytest

# Syntax check
python -m py_compile dok-fu/scripts/dokfu/*.py dok-fu/scripts/dokfu.py

# Install into a test target
python dok-fu/scripts/dokfu.py install --target /tmp/test-project

# Verify installed target's own CLI runs
cd /tmp/test-project
python dok-fu/scripts/dokfu.py index
python dok-fu/scripts/dokfu.py doctor
python dok-fu/scripts/dokfu.py tags --search util
python dok-fu/scripts/dokfu.py changes
```

---

## Configuration

`config/dok-fu.config.json` keys:

| Key | Purpose |
|---|---|
| `docs_dir` | Docs output directory (default: `docs`) |
| `source_globs` | File patterns to include as source files |
| `exclude_globs` | Patterns to exclude (node_modules, build, etc.) |
| `pointer_token` | Comment tag token (default: `dok-fu`) |
| `comment_map` | Per-extension comment prefix (`{ ".py": "#", ".js": "//" }`) |
| `registry_path` | Path to tags registry JSON |
| `manifest_path` | Path to change-detection manifest JSON |

Add tags to `config/tags.registry.json` as `{ "tag": "short explanation" }`. Unknown tags are rejected by all scripts.
