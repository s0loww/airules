---
name: 1c-mechanism-map
description: "Explain a 1C mechanism as an evidence-linked map of entry points, handlers, subscriptions and data writes. Триггеры: как работает механизм, карта механизма, цепочка обработчиков."
---

# Map a 1C mechanism

Take one business question and identify its source contour and extension layers.
Use `1c-code-search` to find entry points and `1c-impact` when dependency traversal
is needed. Reuse already verified scope rather than searching a neighbouring index.

Build a compact tree of entry point → procedure/handler → condition → next action
or register write. Confirm important nodes by reading current BSL and subscription
XML. Distinguish a static reference from an observed runtime transition; source
order alone does not establish the ordering of independent subscriptions.

For each confirmed node give the file, routine and decisive evidence. Label
unresolved branches and ordering as hypotheses, with the smallest observation
that would distinguish them. Include the base/extension owner for overridden code.

Use a text tree by default. A diagram may clarify a complex map when an existing
diagram tool is available; lack of a renderer does not block the explanation.
Mapping is source analysis, not authorization to reproduce a live transaction,
edit the configuration or start background indexing.
