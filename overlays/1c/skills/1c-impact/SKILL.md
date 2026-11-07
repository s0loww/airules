---
name: 1c-impact
description: "Assess callers, metadata dependencies and downstream consequences of a proposed 1C change. Триггеры: влияние изменений, использования объекта, последствия переименования."
---

# Bound the impact of a 1C change

Establish the changed public contract, object or routine, source root and
extension layer. Follow the project's impact/review policy; this skill supplies
the evidence procedure and does not introduce another numbered gate.

Discover a scoped graph, code index or local search route with `mcp-1c-tools`
when its contract is unknown. A facade is one optional route, not a prerequisite.
Use only the arguments in the returned tool schema. Match the returned project
identity and layer coverage to the selected sources before querying.

Start with direct callers, references, type usages, subscriptions and affected
register movements. Expand transitive paths only where they change the decision.
Confirm important edges in the current BSL/XML files; an index result is a pointer,
not proof of current code or execution order. After a bounded miss or absent index,
search the relevant source paths locally and state the narrower coverage.

Return an impact map: changed contract → confirmed consumers → expected consequence
→ verification case, with file/routine references and layer provenance. Separate
dynamic dispatch, reflection, external callers and unknown coverage from confirmed
edges. A zero-hit query is not proof that removal is safe. Do not rename, remove,
reindex or modify a database as a side effect of this analysis.
