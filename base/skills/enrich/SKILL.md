# Enrich

Detect undocumented parts of the codebase and fill the gaps within terseness limits.

## What "enriched" means

A source file is fully enriched when all three of the following are true:

1. The file contains a `dok-fu:` pointer comment near the top, pointing to its parent module.
2. The parent module (`docs/<mirrored-folder>.md`) exists and has an H2 section for this specific file (with a `path:` line and valid frontmatter).
3. `docs/index.json` has an entry for that module.

## Steps

### 1. Identify scope

Use `dokfu doctor` to get a list of files with missing pointers, missing modules, or missing index entries. Work through that list.

If targeting a specific file or directory, scope the check manually: read the file, inspect for a `dok-fu:` comment, look up the mirrored doc path, check the index.

### 2. Add a code pointer (if missing)

Insert a single comment line near the top of the source file (after any shebang or package declaration, before imports):

```
<comment-token> dok-fu: docs/<mirrored-folder-path>.md
```

All files within the same folder point to the **same module**. Use the correct comment token for the file's extension (from `config/dok-fu.config.json` → `comment_map`).

One sentence only. No extra explanation in the comment itself.

### 3. Create the doc module (if missing)

A module covers a **folder**, not a single file. If `docs/<mirrored-folder-path>.md` does not exist, create it using `templates/module.md.tmpl` as the template.

Frontmatter fields to populate:

- `dokfu_id`: slugified folder path (e.g. `src-auth`)
- `code`: repo-relative path to the **source folder**
- `tags`: one or more tags from `config/tags.registry.json`; reject any tag not in the registry
- `description`: one sentence maximum describing the folder/component; this is the index description

### 4. Add a section for the file (if missing)

Each H2 section in the module documents one specific source file. If the module exists but has no section for this file:

1. Append a new H2 whose header is the **filename**.
2. First line of the section body: `path: <repo-relative-path-to-file>`
3. Then ≤ 3 sentences and ≤ 5 bullet points describing the file.
4. Update the `## Sections` bullet list at the top of the module body.

### 5. Refresh the index

After all files in scope are enriched, run:

```
dokfu index
```

Verify the new entries appear with correct tags and description.

## Rules

- Never invent tags. Use only tags present in `config/tags.registry.json`.
- Never exceed terseness limits: 1 sentence in index, 3 sentences / 5 bullets per section, 1 sentence per comment.
- Do not create a doc module for files in `exclude_globs` (from config).
- If `dokfu doctor` still reports issues after enrichment, re-run and address remaining items.
