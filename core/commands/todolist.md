---
name: /todolist
id: todolist
category: OpenSpec
description: Check tech debt in OpenSpec todo.md files and print it as a table
---

<!-- The todo.md format is defined in the sdd-integrations rule ("todo.md — tech-debt format"): one task = one `## <TaskName>` section; bullets are details of that same task. -->

Collect the recorded tech debt from OpenSpec TODO files and show the result
as a table.

## What counts as a tech-debt source

- Look for `openspec/specs/**/todo.md` files.
- If the user named a capability explicitly — limit to
  `openspec/specs/<capability>/todo.md`; otherwise scan all
  `openspec/specs/*/todo.md`.
- Task format:
  - **one task = one `## <Task name>` section**;
  - bullets inside the section (`- ...`, `- [ ] ...`, `- [x] ...`) are
    details of that same task.
- Task status:
  - if the section contains at least one `- [ ]`, the status is `open`;
  - otherwise, if it contains only `- [x]`, the status is `done`;
  - if there are no checkboxes, the status is `open`.

## Steps

1. Find all `openspec/specs/**/todo.md` (or only the given capability).
2. For each file:
   - Determine the capability as the directory name under
     `openspec/specs/<capability>/`.
   - Parse `## ...` sections as individual tasks.
   - Determine each task's status by the rules above.
3. Show the result as a markdown table with the columns:
   - `Capability`
   - `Status`
   - `Task`
   - `Source`
4. Append a summary:
   - `Total`
   - `Open`
   - `Done`

## Output format

```markdown
| Capability | Status | Task | Source |
|---|---|---|---|
| <capability> | open | <task name> | openspec/specs/<capability>/todo.md |
```

If no TODO files are found — print: `OpenSpec todo.md files were not found.`
