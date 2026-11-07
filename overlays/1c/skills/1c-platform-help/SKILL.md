---
name: 1c-platform-help
description: "Resolve a 1C platform or БСП API, format or standard against version-relevant primary documentation. Триггеры: справка платформы 1С, метод БСП, формат XML 1С."
---

# Resolve a platform contract

Identify the platform build, execution context and БСП version where relevant.
Phrase one narrow question: method signature, context availability, type/property,
file format or required standard. Search available documentation/БСП capabilities
or the installed primary reference; discover the route only when unknown.

Use the returned signature and version, not a remembered argument list. When
local documentation is absent or insufficient, use a host-supported primary-source
lookup and identify its version limits. Keep an inference or example separate
from a documented guarantee. Project wrappers and actual source may impose
additional constraints, but do not rewrite the platform contract.

Return the relevant contract, applicability and source reference with a minimal
example if it resolves the question. Documentation lookup does not execute BSL,
install software or prove a change works in the project's applied ИБ.
