---
name: 1c-code-search
description: "Locate a BSL routine, behaviour, literal or module structure in the correct 1C source contour. Триггеры: найти код 1С, найти процедуру, поиск по смыслу."
---

# Locate current BSL evidence

Resolve the active roots, configuration/extension and identifier or behaviour to
find. Follow the project's source-search and freshness policy. Available MCP
indexes can reduce navigation cost; neither a facade nor a particular server name
is required. Use `mcp-1c-tools` only when the route/schema is unknown.

Choose the smallest query that can locate the fragment: exact symbol or literal
for a known name; semantic search for behaviour; module structure before loading
a whole module. Use the actual tool's selectors and pagination, with a returned
project identity matched to the roots. Never copy a selector from another server.

Read the current file/routine for any conclusion or edit. If the index is absent,
stale, outside the relevant layer or gives a bounded miss, search the scoped BSL
paths locally and explain the coverage difference. Do not scan unrelated drives
or assume an empty index proves the code is absent.

Return exact paths/routines and a short explanation of the match. Distinguish
current source, indexed metadata and applied runtime state. Searching does not
trigger a deploy or an index rebuild.
