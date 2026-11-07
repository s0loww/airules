---
name: mcp-1c-tools
description: "Discover the actually exposed 1C capabilities and their schemas without assuming a facade or donor server names. Триггеры: какой MCP нужен, найти инструмент 1С, неизвестный метод."
---

# Route through the current capability surface

Use when the operation or its schema is unknown. A known scoped tool can be used
directly; do not rediscover the whole catalog on every call.

Inspect the current agent's available tool catalog or its supported discovery
tool. Prefer a bounded list of candidate routes and actual parameter schemas.
Visible definitions are not a health probe or proof that a backend is configured;
keep discovery separate from performing the requested operation.

Choose the requested capability: code search, metadata, impact, platform docs,
templates/memory, QA, capture, journal or runtime diagnostics. A facade, direct MCP,
local source tool or project runner can serve the same need. Read the selected
route's live schema, verify project/target scope and layer coverage, then perform
the bounded operation under native permissions. Nested facade methods require
that facade's own discovery; a top-level tool name does not establish its internals.

Do not substitute a neighbouring project's index, invent selector arguments or
equate no visible schema with a stopped server. Use `onec-check-mcp` for diagnosis.
If no route exists, state the missing capability and the supported local/manual
fallback. This skill does not install servers or save connections.
