---
description: "Wiring a form event handler into the form XML. Load when adding, renaming, or removing an event hook (`OnOpen`, `BeforeWrite`, …) on a 1C managed form. Триггеры: добавить обработчик события формы, ПриОткрытии, ПередЗаписью, обработчик не вызывается, событие не зарегистрировано."
alwaysApply: false
kind: recipe
---

# **IMPORTANT!** — don't forget to add the event hook to the form XML file.
The file is usually named `Form.xml` in the parent directory of the module code.

Event hooks in XML look like:

```xml
<Events>
	<Event name="OnOpen">ПриОткрытии</Event>
	<Event name="BeforeWrite">ПередЗаписью</Event>
	<Event name="OnCreateAtServer">ПриСозданииНаСервере</Event>
</Events>
```

Common form events (this is a **non-exhaustive subset** — the platform exposes dozens of form, item, and table events):

| XML Event Name | Russian Handler Name | Description |
|----------------|----------------------|-------------|
| `OnOpen` | `ПриОткрытии` | Client, when form opens |
| `OnClose` | `ПриЗакрытии` | Client, when form closes |
| `BeforeWrite` | `ПередЗаписью` | Client, before write |
| `AfterWrite` | `ПослеЗаписи` | Client, after write |
| `OnCreateAtServer` | `ПриСозданииНаСервере` | Server, form creation |
| `BeforeWriteAtServer` | `ПередЗаписьюНаСервере` | Server, before write |
| `OnWriteAtServer` | `ПриЗаписиНаСервере` | Server, during write (inside the transaction) |
| `AfterWriteAtServer` | `ПослеЗаписиНаСервере` | Server, after write |
| `OnReadAtServer` | `ПриЧтенииНаСервере` | Server, when reading object |

Do not confuse the form's client event `AfterWrite` / `ПослеЗаписи` with the
object-module event `ПриЗаписи` — they live in different modules and fire at
different moments.

The value inside the `<Event>` tag is the name of the handler procedure in the form module.
Every handler named in `Form.xml` must exist in the module exactly once, with
the compilation directive of its event (`&НаКлиенте` for client events,
`&НаСервере` for `…AtServer`): a missing procedure fails when the event fires,
a duplicate fails compilation.

## Getting the full event list

For the complete and authoritative list of available events, do **not** rely on this table. Use:

- `bsl_scope_members` with `member_type="events"` and the relevant context (e.g. `"УправляемаяФорма"`, `"ПолеФормы"`, `"ТаблицаФормы"`, `"КнопкаФормы"`).
- A layout-inspection tool on a similar existing form (structural form tool, or reading the form's XML) — every wired-up event is listed under each element with its handler name.
- `docinfo` / `docsearch` against the platform documentation for the specific form-item type.
- The project's form-search tool, or a semantic code search over the project profile, to locate canonical examples that already use the event you need.

Concrete tool names per category come from the project's MCP profile (root contract `AGENTS.md`).
