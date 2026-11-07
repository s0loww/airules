---
name: craft-mermaid
description: "Render Mermaid source into a portable Craft-style PNG and inspect its readability. Use when an exported diagram image is needed. Триггеры: Mermaid в PNG, экспорт диаграммы, изображение схемы."
---

# Portable Mermaid images

Use this skill for exported image artifacts. For an ordinary inline diagram,
use the host's existing Mermaid presentation when that is sufficient.
Keep source editable and show the produced PNG, not an assumed client preview.

The included runtime pins beautiful-mermaid 1.1.3 and resvg 2.6.2. It supports
flowcharts, state, sequence, class, entity-relationship and XY diagrams.
Read [references/syntax.md](references/syntax.md) for the selected diagram type.
Keep one useful concept per image; split dense diagrams rather than shrinking text.
Quote labels with punctuation and preserve the requested language and semantics.

## Render with the available capability

If the host exposes `craft_mermaid_render`, use its actual schema. It invokes the
pinned local runtime and reports artifact paths and validation; it does not
install dependencies during a task. Keep input and output in the selected project.

Otherwise resolve this skill's source directory, verify Node and its installed
runtime dependencies, and run the included CLI:

```text
node <skill-dir>/scripts/runtime/render.mjs --input <source.mmd> --out-dir <artifacts> --theme craft-light --json
```

Use craft-dark only when requested. Dependency setup uses the included lockfile;
perform it only within the user's authorized installation scope. A managed
generated copy is not a writable source package. Missing dependencies mean the
renderer is unavailable until setup succeeds, not a reason to invent a success
or silently use a different remote renderer.

Read the JSON result and inspect the PNG with the host's image capability.
Use [references/visual-review.md](references/visual-review.md) to assess labels,
edges, contrast and clipping. Repair syntax/layout while preserving meaning;
stop after two repair attempts and report the remaining limitation.
Deliver the source and PNG, distinguishing structural validation from visual review.
