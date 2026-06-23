# Dok-Fu

A documentation workflow system that connects source code and documentation through two-way pointers, a searchable index, and a controlled tag vocabulary. Designed for incremental, AI-assisted documentation that stays in sync with a living codebase.

> See [spec.md](spec.md) for the full requirements spec.

---

## Quickstart

### Install into a target project

```bash
# From the dok-fu source repo, install into <your-project>
python scripts/dokfu.py install --target /path/to/your-project
```

This scaffolds `.github/`, `.claude/`, `docs/`, `scripts/`, `base/`, and `config/` into the target.

### Day-to-day commands

```bash
# Regenerate .github/ and .claude/ from base/ (idempotent)
python scripts/dokfu.py generate

# Rebuild docs/index.json
python scripts/dokfu.py index

# Check if index is stale (exits 1 if yes)
python scripts/dokfu.py index --check

# List all registered tags
python scripts/dokfu.py tags --list

# Find docs tagged with a specific tag
python scripts/dokfu.py tags --search util

# Validate all pointers, tags, and index freshness
python scripts/dokfu.py doctor

# Validate and rebuild index if stale
python scripts/dokfu.py doctor --fix-index

# List source files changed since HEAD (git primary, manifest fallback)
python scripts/dokfu.py changes

# List changed files since a specific git ref
python scripts/dokfu.py changes --since main
```

---

## Architecture

```
dok-fu/
├── base/                         Single source for all AI tool output
│   ├── instructions/             System-level instructions (base)
│   ├── prompts/                  Invokable prompt wrappers
│   └── skills/                   Skill bodies (traverse, enrich, update)
├── config/
│   ├── dok-fu.config.json        Docs dir, source globs, comment map, paths
│   └── tags.registry.json        Controlled tag vocabulary
├── scripts/
│   ├── dokfu.py                  CLI entry point (argparse)
│   └── dokfu/                    Python package
│       ├── common.py             Config, frontmatter, path mapping, pointers
│       ├── index.py              Build/check docs/index.json
│       ├── pointers.py           Extract and validate doc↔code pointers
│       ├── tags.py               Tag registry: list and search
│       ├── changes.py            Changed-file detection (git + manifest)
│       ├── doctor.py             Validate everything, report problems
│       ├── generate.py           base/ → .github/ + .claude/ (idempotent)
│       └── install.py            Vendor dok-fu into a target project
├── templates/
│   └── module.md.tmpl            Template for new doc modules
├── tests/                        pytest unit tests
└── examples/
    └── sample/                   Minimal two-file project with complete docs
```

Generated into any target project:
```
<target>/
├── .github/
│   ├── copilot-instructions.md
│   ├── instructions/dok-fu.instructions.md
│   ├── prompts/{traverse,enrich,update}.prompt.md
│   └── skills/{traverse,enrich,update}/SKILL.md
└── .claude/
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

See [base/GLOSSARY.md](base/GLOSSARY.md) for full definitions.

---

## Format Reference

### Doc module (`docs/<folder>.md`)

```markdown
---
dokfu_id: src-auth
code: src/auth
tags: [auth, http]
description: One sentence describing this folder.
---

# Auth

## Sections
- [login.py](#loginpy)
- [tokens.py](#tokenspy)

## login.py
path: src/auth/login.py
≤3 sentences describing the file.
- Up to 5 bullets with key details
```

### Code pointer (top of each source file)

```python
# dok-fu: docs/src/auth.md
```

### Index entry (`docs/index.json`)

```json
{ "path": "docs/src/auth.md", "tags": ["auth"], "description": "One sentence." }
```

---

## AI Skills

| Skill | When to use |
|---|---|
| **Traverse** | Exploring unfamiliar code; navigates index → modules → comments → code |
| **Enrich** | New file added or gaps detected by `dokfu doctor`; fills missing docs |
| **Update** | Source changed; uses `dokfu changes` to find and sync stale docs |

---

## Verification

```bash
# All unit tests
python -m pytest

# Syntax check
python -m py_compile scripts/dokfu/*.py scripts/dokfu.py

# Install into sample
python scripts/dokfu.py install --target examples/sample

# Idempotency (second run should show 0 written)
python scripts/dokfu.py generate
python scripts/dokfu.py generate

# From sample dir: index, doctor, tags
cd examples/sample
python ../../scripts/dokfu.py index
python ../../scripts/dokfu.py doctor
python ../../scripts/dokfu.py tags --search util
python ../../scripts/dokfu.py changes
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
