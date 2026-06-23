
---

## Validation Report: Dok-Fu vs. Spec & Plan

### CONFLICTS

1. **Anchor format mismatch** — Spec/instructions show `#filename-py` anchors, but src.md uses `#greeterpy` (GitHub-style special-char removal). Inconsistent across tools.

2. **Generate silently loses extra instruction files** — `generate.py` iterates instruction files but always writes to fixed paths (dok-fu.instructions.md, copilot-instructions.md). Multiple instruction source files in instructions would silently clobber each other. (Currently there is only one, so it doesn't bite yet, but the plan says *idempotent* and this pattern breaks that guarantee the moment a second file is added.)

---

### AMBIGUITIES

1. **Markdown anchor algorithm unspecified** — Spec shows `#filename-py` but never defines the normalization rule. Different renderers produce different anchors from `## greeter.py`. The example and the instructions disagree; one will be wrong.

2. **Pointer validation scope** — Spec says "all files within the same folder point to the same module," but `pointers.py` and `doctor.py` only check that *at least one* file in the folder has a back-pointer. Files pointing to the *wrong* module pass silently.

---

### GAPS

1. **Doctor: cross-folder pointer violation undetected** — `src/file.py` pointing to `docs/other.md` instead of `docs/src.md` passes validation. The folder-based module boundary invariant is not enforced.

2. **Doctor: folder-wide pointer consistency not validated** — Files in the same folder pointing to *different* modules are not reported as a conflict.

3. **No terseness enforcement** — Spec defines hard limits (1-sentence index, ≤3 sentences/≤5 bullets per section, 1-sentence comments). No script checks these; `doctor` doesn't report violations.

4. **Section `path:` lines not existence-checked** — `pointers.py` parses `path:` lines from H2 sections but doesn't verify the referenced file exists. A stale path passes until `doctor` runs a full check.

5. **Install gives no format validation signal** — `install.py` creates an empty `docs/` and seeds an empty index but doesn't warn that subsequently created modules must conform to format rules. A first-time user gets no guardrails until `dokfu doctor` is manually invoked.

---

**Totals**: 2 conflicts · 2 ambiguities · 5 gaps. No false positives detected in the happy path; all issues surface only on edge cases or growth scenarios.

---
---

## Dok-Fu Validation Report

### Conflicts

**1. `dokfu_id` — documented but not enforced**
Spec, plan, instructions, and template all define `dokfu_id` as the rename-repair anchor. No script (doctor.py, pointers.py, generate.py) reads or validates this field. It is populated in templates but silently ignored at runtime — the rename-repair promise is a documentation-only claim with zero implementation.

**2. `doctor` orphan definition — inconsistent between spec and code**
Spec says "orphaned source = source file whose expected doc does not exist." `doctor.py/check_orphaned_sources` adds a second condition: the file must *also* have no pointer comment. A source file with a pointer comment pointing to a non-existent doc is silently skipped rather than flagged — contradicting the spec's intent that every missing doc is an orphan.

**3. Code pointer format — missing comment token in sample**
calculator.py and `greeter.py` use `# dok-fu: docs/src.md` — no space between `#` and `dok-fu`. dok-fu.config.json sets `pointer_token = "dok-fu"` and `comment_map[".py"] = "#"`. `common.py/build_pointer_line` (not read in full, but used by enrich skill instructions) needs to produce `# dok-fu:`. Verify the format is exactly `# dok-fu:` not `#dok-fu:` — the sample files use `# dok-fu:` (with space), but the pointer parser in `parse_pointer_line` should handle both. **Ambiguity**: the spec says "language comment token + dok-fu", but never specifies whether a space separates them.

---

### Gaps

**4. No rename/move repair logic exists**
Spec requires: "doctor/validate script flags broken/orphaned pointers; AI repairs them." Plan marks "rename handling" as resolved. doctor.py flags broken pointers correctly but there is no `--fix-pointers` or repair command — only `--fix-index`. The AI instructions say "AI repairs" but no structured repair workflow or helper is provided. The claimed `dokfu_id` anchor for rename detection is completely unused.

**5. generate.py does not produce a .claude instructions file**
Spec: "Technology Agnostic — scripts generate … GitHub Copilot and Claude Code infrastructure." generate.py emits dok-fu.instructions.md and copilot-instructions.md, but produces *no* equivalent for Claude (e.g. `.claude/CLAUDE.md` or `.claude/instructions/`). Claude Code skills are emitted, but the system instructions/context file for Claude is absent.

**6. install.py does not copy templates**
Plan step: "copy scripts base config into `--target`." install.py copies those three directories but not templates. The Enrich skill instructs AI to use module.md.tmpl — which won't exist in the installed target.

**7. No `--root` / `--config` flag on CLI**
All `cmd_*` handlers hardcode `root = Path.cwd()`. There is no way to run `dokfu` against a project in a different directory without `cd`-ing first. The plan's CLI spec does not mention this flag, but it is a practical gap for a "reusable system for ANY target project."

**8. `dokfu changes` default ref behaviour is ambiguous**
CLI passes `since = args.since if args.since else "HEAD"` to `get_changed_files`. In git, `git diff HEAD` shows unstaged changes, not "since last commit." The intended semantic (changes since last commit) typically requires `HEAD~1` or `HEAD^`. The spec says "since last commit" but the implementation defaults to `HEAD`, which may return nothing on a clean working tree.

**9. Index includes docs without frontmatter (silent empty entries)**
`index.py/build_index` includes every `.md` under `docs/` even if it has no frontmatter — emitting `{path, tags:[], description:""}`. doctor.py does not flag these. The spec says the index entry is derived from frontmatter; a doc without valid frontmatter should be flagged by `doctor`, not silently indexed.

---

### Ambiguities

**10. Module boundary for top-level source files**
`map_source_to_doc` maps `app.py` (root-level) to `docs/root.md`. The spec says "docs location: top-level `docs/` mirroring source structure" but gives no explicit rule for root-level files. `root.md` is an undocumented convention — not in the spec, glossary, or instructions.

**11. `## Sections` anchor format**
Instructions and README show `[filename.py](#filename-py)` (dot replaced by hyphen in anchor). This is a GitHub Markdown convention but not enforced or validated anywhere. If a tool renders anchors differently, section links break silently — no validator checks this.