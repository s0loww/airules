---
name: 1c-meta-info
description: "Read a 1C object's type, attributes, tabular parts, forms and ownership before reasoning about its structure. Триггеры: паспорт объекта 1С, реквизиты объекта, найти по синониму."
---

# Establish a metadata object's identity

Resolve a qualified object name or Russian synonym in the selected source
contour. Record configuration/extension ownership, canonical identity and source
version. Reuse a returned identity instead of guessing another service's name
format or argument names.

Inspect only the sections needed: type, реквизиты and their types, табличные
части, forms, commands, predefined data, register dimensions/resources or owners.
Discover available metadata routes when needed; otherwise use the existing local
metadata-info procedure in `1c-metadata-manage` without its writing operations.

Confirm significant facts against current XML when an index may be stale. An
object passport is not validation of references, behaviour or the deployed ИБ.
For a change, hand off to the existing metadata owner rather than creating a
parallel editor or hand-writing a second XML transformation.

Report the identity, requested facts, source references and unknown coverage.
Do not expose credentials or infer live data from metadata declarations.
