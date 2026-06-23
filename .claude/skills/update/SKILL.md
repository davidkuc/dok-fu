---
type: skill
name: update
---
# Update

Synchronize documentation with recent changes in the codebase.

## When to run

Run Update after any batch of source file edits — before committing or after a feature branch lands.

## Steps

### 1. Get the changed files

```
dokfu changes [--since <REF>]
```

This returns a list of source file paths that changed since the given git ref (default: last commit). If git is unavailable, it falls back to the sha256 manifest comparison.

If the list is empty, documentation is up to date. Stop.

### 2. For each changed file

#### 2a. Read the source file

- Locate the `dok-fu:` pointer comment near the top.
- If the pointer is absent, treat the file as unenriched and run the **Enrich** skill instead.
- If the pointer target no longer exists (broken pointer), run `dokfu doctor` — it will identify rename candidates matched by `dokfu_id`. Run `dokfu doctor --fix-pointers` to repair, then reload the file and continue.

#### 2b. Open the linked doc module

Follow the pointer path from the comment. Open `docs/<mirrored-folder-path>.md`.

- Read the `## Sections` block to orient yourself. Each bullet is a source filename.
- Find the H2 section whose `path:` matches the changed source file.
- Identify whether that section needs updating.

#### 2c. Update the affected section

Rewrite only the section whose `path:` matches the changed file. Preserve all other sections verbatim.

Terseness limits: ≤ 3 sentences and ≤ 5 bullet points per section. The `path:` line itself does not count toward those limits.

#### 2d. Update inline code comments

If the change introduces new logic, parameters, or patterns, update or add a 1-sentence inline comment in the source file at the relevant location.

Do not touch comments that are still accurate.

#### 2e. Update frontmatter (if needed)

If the change affects the module's `tags` or `description`, update those fields in the frontmatter. Use only tags from `config/tags.registry.json`.

### 3. Refresh the index

After all affected modules are updated, run:

```
dokfu index
```

This regenerates `docs/index.json` from the current frontmatter of all modules.

### 4. Validate

Run `dokfu doctor` to confirm no broken pointers, unknown tags, or stale index remain. Resolve any reported issues before finishing. If doctor reports broken pointers with rename candidates, run `dokfu doctor --fix-pointers` before finalizing.

## Rules

- Change only what changed. Do not rewrite unaffected sections or comments.
- Never exceed terseness limits.
- Never invent tags not present in `config/tags.registry.json`.
- If `dokfu changes` returns a file that has no doc pointer, switch to the **Enrich** skill for that file.
