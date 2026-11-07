---
name: 1c-form-inspect
description: "Inspect a managed 1C form's elements, data bindings, commands and handlers before changing it. Триггеры: структура формы 1С, привязки формы, обработчики формы."
---

# Inspect a managed form

Identify the owning object, form, source root and extension. Read the current
form XML and relevant module through an available inspector or the read-only
procedures of `1c-metadata-manage`. The latter remains the owner of modifications,
DSL compilation, UUID handling and form validation.

Map the requested UI feature to its element, data path, command and handler.
Check declared attributes/types and existing naming conventions before proposing
an edit. Use a version-appropriate schema or platform reference when a property
or XML structure is uncertain; do not infer it from a screenshot alone.

Return a bounded element/binding map with exact XML and module references.
Separate source structure from what is actually rendered in an applied client.
For visual evidence use `1c-form-shot`; for repeatable behaviour use the project's
UI test procedure. Inspection does not open a live form, modify XML or apply an
extension automatically.
