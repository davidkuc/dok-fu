---
mode: agent
description: Update
---
# Update

Use this prompt to synchronize documentation after source files have changed.

---

Apply the **Update** skill.

Run `dokfu changes` to get the list of changed source files. For each file, follow its `dok-fu:` pointer to the linked doc module and update the affected sections and inline comments. Stay within terseness limits. Run `dokfu index` after all modules are updated, then run `dokfu doctor` to confirm no issues remain.
