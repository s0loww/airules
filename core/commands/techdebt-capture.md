---
name: /techdebt-capture
id: techdebt-capture
category: OpenSpec
description: Record tech debt in openspec/specs/<capability>/todo.md
---

<!-- The todo.md format is defined in the sdd-integrations rule ("todo.md — tech-debt format"): one task = one `## <TaskName>` section; bullets are details of that same task. -->

Record tech debt in the OpenSpec todo file using the project template.

## Rules

1. Target file: `openspec/specs/<capability>/todo.md`.
   - The capability is mandatory. If the user did not specify it — scan
     `openspec/specs/*`, list the existing capabilities and ask which one the
     debt belongs to (or what to name a new one).
2. Entry format:
   - one task = one `## <Short title>` section;
   - inside the section include:
     - `Temporary solution:` (if any);
     - `Production follow-up:` with a `- ...` list.
3. Do not split a single task into several sections when the user described
   one piece of debt.
4. If `todo.md` does not exist — create it with a `# TODO` header, then add
   the task.
5. If a section with the same title already exists — update it, do not
   duplicate.

## Steps

1. Determine the capability (ask if not given) and the target `todo.md`.
2. Read the current file (if it exists).
3. Add or update the task section per the template.
4. Show the user exactly what was recorded and in which file.
