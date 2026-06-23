---
mode: agent
description: Enrich
---
# Enrich

Use this prompt to fill documentation gaps for source files that lack pointers, modules, or index entries.

---

Apply the **Enrich** skill.

Run `dokfu doctor` to identify undocumented files. For each file: add a `dok-fu:` pointer comment, create the doc module from `templates/module.md.tmpl` if missing, and add any missing sections. Use only tags from `config/tags.registry.json`. Stay within terseness limits (1-sentence index description, ≤ 3 sentences / ≤ 5 bullets per section, 1-sentence comments). Run `dokfu index` when done.
