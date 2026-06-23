# Plan: Dok-Fu Refinement Pass

Address all confirmed issues from `refine.md` (2 validation reports). False positive confirmed: install.py already copies `templates/` — skip that item.

**Decisions**
- Anchor format: GitHub-style `#greeterpy` (dots removed, not replaced)
- Claude instructions: generate `.claude/CLAUDE.md`
- `dokfu_id`: implement rename detection in `doctor.py` + `--fix-pointers`
- `changes` default ref: `HEAD~1` (changes since last commit)
- Terseness enforcement: descoped
- `--root` flag: yes, global CLI flag

---

## Phase A — Bug Fixes (all independent, run in parallel)

**A1. `changes.py` default ref**
- Change `since: str = "HEAD"` → `"HEAD~1"` in `get_changed_files()` signature
- Change CLI default in `dokfu.py`: `since = args.since if args.since else "HEAD~1"`
- Update `test_changes.py` default-ref test

**A2. `generate.py` multi-instruction-file handling**
- Replace fixed-path loop with per-file routing:
  - Each `base/instructions/<stem>.md` → `.github/instructions/<stem>.instructions.md`
  - For `copilot-instructions.md`: concatenate all instruction file bodies (separator: `\n\n---\n\n`)
- Update `test_generate.py` to cover multi-file and single-file scenarios

**A3. Anchor format standardization**
- Replace all `#filename-py` style with `#filenamepy` (dots removed) in:
  - `templates/module.md.tmpl` (update `{{FILENAME_ANCHOR}}` generation note/comment)
  - `base/instructions/dok-fu.base.md` (## Sections format examples)
  - `base/skills/enrich/SKILL.md` (section link examples)
  - `base/skills/update/SKILL.md` (if any anchor examples)
  - `examples/sample/docs/src.md` already uses correct format — confirm no changes needed

**A4. `doctor.py` orphan vs. broken-pointer clarity**
- Audit `check_broken_pointers`: confirm it already catches source files whose pointer points to a non-existent doc file
- If not, fix: add check that the resolved pointer path actually exists
- Document the distinction clearly: orphaned = never connected; broken = connected but target gone

---

## Phase B — Doctor Enhancements (independent of each other; parallel)

**B1. Cross-folder pointer violation**
- Add `check_cross_folder_pointers(config, root)` to `doctor.py`
- Logic: for each source file with a pointer, resolve pointer → doc; read doc's `code:` field; verify it matches the source file's folder; flag if not
- Integrate into `DoctorReport` and `cmd_doctor()`

**B2. Folder-wide pointer consistency**
- Add `check_folder_pointer_consistency(config, root)` to `doctor.py`
- Logic: group source files by parent folder; for each group, collect all pointer targets; if set has >1 unique target, flag as "inconsistent folder pointers"
- Integrate into `DoctorReport` and `cmd_doctor()`

**B3. Section `path:` existence check**
- Add `check_section_paths(config, root)` to `doctor.py`
- Logic: for each doc, parse H2 sections via `get_section_paths()` from `pointers.py`; verify each resolved path exists on disk
- Integrate into `DoctorReport` and `cmd_doctor()`

**B4. Missing frontmatter fields check**
- Add `check_missing_frontmatter(config, root)` to `doctor.py`
- Flag docs missing any of: `code`, `description`, `tags` fields in frontmatter (not just completely missing frontmatter)
- Integrate into `DoctorReport` and `cmd_doctor()`

**Tests for B1–B4**: add to `test_doctor.py`

---

## Phase C — New Features (sequential: C1 then C2/C3 in parallel)

**C1. Global `--root` CLI flag** *(blocks C2 and C3 indirectly — threads through all cmds)*
- Add `parser.add_argument("--root", ...)` to top-level argparse in `dokfu.py`
- Pass `root=args.root` to all `cmd_*` handler calls; each handler already accepts `root` via config or function arg
- All `cmd_*` functions: accept `root` parameter and pass to `load_config()` with `root` override
  - Reference: `common.py/load_config()` accepts `root` param (confirm or add)

**C2. Generate `.claude/CLAUDE.md`**
- Add `_emit_claude_instructions(body, out)` in `generate.py`
- Emits to `out / ".claude" / "CLAUDE.md"` with Claude-appropriate preamble (no YAML frontmatter, just raw markdown)
- Call from main `generate()` function for each instruction file body (same loop as GitHub instructions)
- Add to `result.record()` tracking for idempotency
- Add test in `test_generate.py`

**C3. `dokfu_id` rename detection + `--fix-pointers`**
- Add `_slugify_for_dokfu_id(folder_path)` helper in `common.py` (e.g. `src/auth` → `src-auth`, replaces `/` and `.` with `-`)
- Add `check_renamed_docs(config, root)` to `doctor.py`:
  - Collect all docs → `{dokfu_id: doc_path}` index
  - For each broken pointer, compute expected `dokfu_id` for the source file's folder
  - If a doc with matching `dokfu_id` exists at a different path, report as `RenameCandidate(source, broken_ptr, candidate_doc)`
  - Integrate into `DoctorReport.renamed` field
- Add `--fix-pointers` to `dokfu doctor` CLI:
  - For each `RenameCandidate`, update pointer comment in source file using `build_pointer_line()`
  - Report what was updated
- Add tests in `test_doctor.py`

---

## Phase D — Documentation & Consistency (parallel, no code deps)

**D1. Document `root.md` convention**
- Add to `spec.md` under Key Functionalities: explicit note that root-level source files map to `docs/root.md`
- Add to `base/GLOSSARY.md`: entry for `root.md`
- Add to `base/instructions/dok-fu.base.md`: mention `root.md` in module mapping rules

**D2. Canonicalize pointer format with space**
- In `spec.md` and `base/instructions/dok-fu.base.md`: explicitly show `# dok-fu:` (with space between `#` and `dok-fu`) as canonical format

**D3. Install post-install signal**
- In `install.py` output / `cmd_install()`: add print message at end: "Run `dokfu doctor` to validate the installation."

---

## Phase E — Base/ Content Updates (parallel with D; depends on C3 design)

**E1. `base/instructions/dok-fu.base.md`**
- Fix anchor examples in "Doc module body" section: `#filename-py` → `#filenamepy` (GitHub-style)
- Add `dokfu doctor --fix-pointers` row to Scripts Reference table
- Update "Pointer broken / file renamed?" guidance: "Run `dokfu doctor` to detect rename candidates via `dokfu_id` matching; run `dokfu doctor --fix-pointers` to auto-repair pointer comments in source files; then run `dokfu index`"

**E2. `base/skills/update/SKILL.md`**
- In **Step 2a** (read source file), add: "If the pointer target no longer exists (broken pointer), run `dokfu doctor` — it will identify rename candidates matched by `dokfu_id`. Run `dokfu doctor --fix-pointers` to repair, then reload the file and continue."
- In **Step 4** (Validate), add: "If doctor reports broken pointers with rename candidates, run `dokfu doctor --fix-pointers` before finalizing."

**E3. `base/skills/enrich/SKILL.md`**
- In **Step 1** (Identify scope), add: "If `dokfu doctor` reports rename candidates (broken pointer with a `dokfu_id` match), run `dokfu doctor --fix-pointers` first — these are not documentation gaps, they are pointer repairs."
- In **Step 4** (Add a section), add note on anchor format: "`## Sections` bullet anchors use GitHub-style normalization — remove all non-alphanumeric characters except hyphens. `filename.py` → `#filenamepy`."

**E4. `base/GLOSSARY.md`**
- Update **orphan** entry: clarify that a broken pointer with a matching `dokfu_id` in another doc is a *rename candidate*, not an orphan; orphan = no pointer and no expected doc
- Add **rename candidate** entry: "A source file whose `dok-fu:` pointer target no longer exists, but a doc module with a matching `dokfu_id` was found at a different path. Detected by `dokfu doctor`; repaired by `dokfu doctor --fix-pointers`."
- Add **dokfu_id** entry: "A stable slug in doc module frontmatter derived from the source folder path (e.g. `src/auth` → `src-auth`). Used by `dokfu doctor` to match broken pointers to renamed or moved doc modules."

**E5. `base/prompts/update.md`**
- Add sentence: "If `dokfu doctor` reports broken pointers with rename candidates, run `dokfu doctor --fix-pointers` to repair them before proceeding."

---

## Relevant Files

- `scripts/dokfu/changes.py` — A1
- `scripts/dokfu/generate.py` — A2, C2
- `templates/module.md.tmpl`, `base/instructions/dok-fu.base.md`, `base/skills/enrich/SKILL.md` — A3, E1, E3
- `scripts/dokfu/doctor.py` — A4, B1–B4, C3
- `scripts/dokfu/common.py` — C3
- `scripts/dokfu.py` — C1, C3
- `spec.md`, `base/GLOSSARY.md`, `base/instructions/dok-fu.base.md` — D1, D2, E1, E4
- `scripts/dokfu/install.py` — D3
- `base/skills/update/SKILL.md`, `base/skills/enrich/SKILL.md` — E2, E3
- `base/prompts/update.md` — E5
- `tests/test_changes.py`, `tests/test_generate.py`, `tests/test_doctor.py` — all test updates

## Verification

1. `python -m pytest` — all tests pass (baseline: 137; expect increase for new checks)
2. Break a pointer to a renamed doc → `dokfu doctor` reports rename candidate; `dokfu doctor --fix-pointers` updates pointer comment
3. Create two source files in same folder pointing to different docs → `dokfu doctor` reports folder consistency violation
4. Add `path: nonexistent.py` to a doc section → `dokfu doctor` reports section path error
5. Run `dokfu generate` twice → identical output (idempotency still holds)
6. Confirm `.claude/CLAUDE.md` is created by `generate`
7. Run `dokfu --root examples/sample doctor` → validates without cd
8. `dokfu changes` on clean tree after one commit → lists last commit's changes (not empty)

## Scope Exclusions
- Terseness enforcement (descoped by user)
- install.py template copy (already works — false positive in refine.md)
- `--config` flag (only `--root` requested)
