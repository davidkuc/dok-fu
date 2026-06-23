# Plan: Implement Dok-Fu Documentation System

Treat the **spec.md** file as authoritative requirements. You must reference the spec before each implementation. This plan = execution detail.

Progress tracked via checkboxes below. Keep in sync as work proceeds.

## Decisions (from user)
- Scripts: Python, may use a few pinned packages (pyyaml, gitpython ok)
- Code->doc pointer: comment-based tag near top of file (configurable token)
- Doc->code pointer: YAML frontmatter
- Scope: reusable system for ANY target project (vendored via install script)
- Docs location: top-level docs/ mirroring source structure
- Change detection: git primary, content-hash manifest fallback
- Copilot targets: .github/skills (SKILL.md), .github/prompts/*.prompt.md,
  .github/instructions/*.instructions.md, .github/copilot-instructions.md
- Claude target: .claude/skills/<name>/SKILL.md
- Base reference: single source dir (dok-fu/base/) -> generated .github + .claude
- Rename handling: doctor/validate script flags broken/orphaned pointers, AI repairs
- Tags: controlled vocabulary governed by tags.registry.json
- Source comment injection: allowed (1-sentence comments + doc pointer)

## Architecture
Source repo layout:
- base/skills/{enrich,update,traverse}/SKILL.md  (tool-agnostic bodies)
- base/instructions/dok-fu.base.md
- base/prompts/{enrich,update,traverse}.md
- scripts/dokfu/ python package: common, index, tags, pointers, doctor, changes, generate, install
- scripts/dokfu.py CLI (argparse)
- templates/module.md.tmpl
- config/dok-fu.config.json, config/tags.registry.json
- README-DOK-FU.md, GLOSSARY

Installed into target:
- .github/{copilot-instructions.md, instructions/, prompts/, skills/}
- .claude/skills/
- scripts/dokfu (vendored), base/ (vendored single source), config/
- docs/index.json, docs/<mirror>.md

## FORMAT REFERENCE (authoritative for implementation)
Doc frontmatter (YAML at top of every docs/*.md):
  dokfu_id: stable slug (optional aid for rename repair)
  code: repo-relative path to source file
  tags: [list, from, registry]
  description: ONE sentence (index source)
Module body (after frontmatter): H1 title; "## Sections" mini-index (bullet list of the
  module's own H2 headings); then H2 sections, each <=3 sentences and <=5 bullets.
Code pointer: single comment line near top using language comment + token, e.g.
  "<comment> dok-fu: docs/<mirrored>.md". Token + per-language comment map in config.
Index file docs/index.json: flat array of {path, tags[], description}; consumers group
  by directory prefix (progressive disclosure). Regenerated, never hand-edited.
Tag registry config/tags.registry.json: { tag: short-explanation } controlled vocabulary.
Change manifest docs/.dokfu-manifest.json: { path: sha256 } fallback when git absent.
Config config/dok-fu.config.json: docs_dir, source_globs[], exclude_globs[], pointer_token,
  comment_map{ext:comment}, registry_path, manifest_path.

## CLI (scripts/dokfu.py, argparse subcommands)
- install [--target .] : scaffold + vendor scripts/base/config + create docs/ + run generate
- generate            : base/ -> .github + .claude (idempotent, drift-safe)
- index [--check]     : build docs/index.json; --check exits nonzero if stale
- tags --list|--search TAG : list registry / find docs by tag (validates vs registry)
- doctor [--fix-index]: validate pointers (both directions), tags vs registry, index freshness;
                        report broken + orphaned; nonzero exit on problems
- changes [--since REF]: list changed source files (git diff primary, manifest fallback)

============================================================
## PHASE 0 — Repo scaffolding & spec  (no deps)
- [X] Confirm spec.md is the canonical spec; link it from README later
- [X] Create top-level dirs: base/, scripts/dokfu/, templates/, config/, tests/, examples/sample/
- [X] Add scripts/requirements.txt (pyyaml pinned; git via subprocess, no gitpython)
- [X] Add scripts/dokfu/__init__.py (package marker + version)

## PHASE 1 — Foundations: config, formats, common  (deps: P0)
- [X] Write config/dok-fu.config.json with all keys from FORMAT REFERENCE + sane defaults
- [X] Write config/tags.registry.json seed vocabulary (e.g. auth, http, config, cli, io, test)
- [X] common.py: load_config()
- [X] common.py: read/write YAML frontmatter (parse + serialize, preserve body)
- [X] common.py: walk_sources(config) honoring source_globs/exclude_globs
- [X] common.py: map_source_to_doc(path) + map_doc_to_source(path) (docs/ mirror rules)
- [X] common.py: comment_for_ext(ext) + build/parse pointer line
- [X] tests/test_common.py for the above

## PHASE 2 — Deterministic scripts  (deps: P1; modules parallel) + pytest
- [ ] index.py: scan docs/, read frontmatter, emit flat docs/index.json; --check staleness
- [ ] pointers.py: extract doc->code (frontmatter) and code->doc (comment) pointers
- [ ] pointers.py: validate_pair() both directions resolve & agree
- [ ] tags.py: --list registry; --search returns matching doc paths; reject unknown tags
- [ ] changes.py: git diff --name-only since REF/HEAD; fallback sha256 manifest compare
- [ ] changes.py: update_manifest() writes docs/.dokfu-manifest.json
- [ ] doctor.py: broken pointers, orphaned docs/code, unknown tags, stale index; report+exit
- [ ] tests: test_index, test_pointers, test_tags, test_changes, test_doctor

## PHASE 3 — Base reference content (single source)  (deps: P1; parallel w/ P2)
- [ ] base/skills/traverse/SKILL.md: index->modules(section index)->comments->code; uses `dokfu tags`; save relevant paths to memory
- [ ] base/skills/enrich/SKILL.md: detect missing comment/section/index entry; fill within terseness limits (idx 1 sent, module 3 sent/5 bullets, comment 1 sent)
- [ ] base/skills/update/SKILL.md: run `dokfu changes` -> follow pointers -> edit section+comments -> `dokfu index`
- [ ] base/instructions/dok-fu.base.md: system overview, pillars, format rules, when to run which skill/script
- [ ] base/prompts/{traverse,enrich,update}.md: short invokable wrappers around skill bodies
- [ ] templates/module.md.tmpl: frontmatter + ## Sections + sample H2
- [ ] base/GLOSSARY.md: index, module, comment, pointer, tag, traverse, enrich, update, drift, orphan

## PHASE 4 — Generator + installer + CLI  (deps: P2 + P3)
- [ ] generate.py: read base/ once; emit .claude/skills/<n>/SKILL.md (claude frontmatter)
- [ ] generate.py: emit .github/skills/<n>/SKILL.md + .github/prompts/<n>.prompt.md
- [ ] generate.py: emit .github/instructions/dok-fu.instructions.md (applyTo) + .github/copilot-instructions.md
- [ ] generate.py: token/path substitution per tool; idempotent (stable output, drift-safe)
- [ ] install.py: copy scripts/ base/ config/ into --target; create docs/; run generate; seed manifest
- [ ] dokfu.py: argparse wiring for install/generate/index/tags/doctor/changes
- [ ] tests/test_generate.py: .github & .claude skill bodies match (drift check)

## PHASE 5 — Docs & verification harness  (deps: P4)
- [ ] README-DOK-FU.md: quickstart, copy-paste commands, architecture overview, link spec.md
- [ ] examples/sample/: tiny project (1-2 source files) + matching docs for e2e
- [ ] Verification run (below) all green; record commands in README

## VERIFICATION (run at end of P5)
- [ ] `python -m pytest` all unit tests pass
- [ ] `python -m py_compile scripts/dokfu/*.py scripts/dokfu.py`
- [ ] `dokfu install --target examples/sample` creates .github/.claude/docs/scripts
- [ ] `dokfu generate` twice -> identical output (idempotent) + .github/.claude bodies match
- [ ] sample doc+code pair -> `dokfu index` -> entry present in index.json
- [ ] break a pointer & move a file -> `dokfu doctor` reports broken + orphaned (nonzero exit)
- [ ] `dokfu tags --search auth` returns the doc; unknown tag rejected
- [ ] `dokfu changes` lists edited file via git, and via manifest when git disabled
