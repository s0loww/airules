---
name: 1c-templates-memory
description: "Find and adapt an existing 1C solution pattern while keeping project decisions and reusable templates separate. Триггеры: шаблон решения 1С, похожая реализация, проверить проектную память."
---

# Reuse an owned solution pattern

Identify the task class and its constraints. Look first for an existing project
implementation or a known template using bounded queries. Consult project memory
through its configured owner when prior decisions or incident history matter.
Template search and memory may be separate services; one does not replace the
other, and a facade is optional.

Read the selected pattern and verify its platform/БСП version, dependencies,
source ownership and extension assumptions. Adapt the smallest relevant part;
do not paste an entire module or adopt a project-specific account/path from a
template. Preserve attribution and applicable notices.

State which pattern was reused and how it fits the current task. A memory note
or old example is not fresh evidence or new permission. Record a durable new
decision through the existing memory policy only when the result warrants it;
use `skill-maintainer` for a proven reusable procedure, not for an unresolved
workaround or every successful lookup.
