# Enrich

Detect undocumented parts of the codebase and fill the gaps within terseness limits.

Format specification: `dok-fu\base\FORMAT.md`

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

## Scripts

| Command | Purpose |
|---|---|
| `dokfu doctor` | Identify files with missing pointers, modules, or index entries |
| `dokfu doctor --fix-pointers` | Repair broken pointer comments for rename candidates |
| `dokfu index` | Rebuild `docs/index.json` after enrichment |

## What "enriched" means

A source file is fully enriched when all three of the following are true:

1. The file contains a `dok-fu:` pointer comment near the top, pointing to its parent module.
2. The parent module (`docs/<mirrored-folder>.md`) exists and has an H2 section for this specific file (with a `path:` line and valid frontmatter).
3. `docs/index.json` has an entry for that module.

## Steps

### 1. Identify scope

Use `dokfu doctor` to get a list of files with missing pointers, missing modules, or missing index entries. Work through that list. If `dokfu doctor` reports rename candidates (broken pointer with a `dokfu_id` match), run `dokfu doctor --fix-pointers` first — these are not documentation gaps, they are pointer repairs.

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

Section links use relative file paths. Example: `[filename.py](src/component/filename.py)` where the path matches the `path:` field of that section.

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
