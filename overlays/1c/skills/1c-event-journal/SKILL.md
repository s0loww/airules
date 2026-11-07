---
name: 1c-event-journal
description: "Inspect relevant entries in the 1C Журнал регистрации with a bounded time/target scope. Триггеры: ЖР 1С, последние ошибки базы, журнал регистрации."
---

# Read Журнал регистрации evidence

Distinguish ЖР from ТЖ. For technical logs use the existing `1c-tj-analysis` skill;
this skill does not prohibit or replace it. Establish the selected ИБ, period,
event/severity and any object/user filter. Start with a small bounded result
(normally a few dozen entries), then narrow or paginate if necessary.

Prefer an available dedicated read-only journal capability. A generic BSL/data
executor requires its real schema, the correct target and a reviewed read-only
query within the user's scope. If only an explicitly configured export/path is
available, use its supported parser. Raw `.lgd`/`.lgp` containers are not assumed
to be pipe-delimited text; do not scan drives or invent a parser/connection.

Report time, severity, event, relevant object and a minimal redacted message,
with target/period/source provenance. Keep missing coverage or unavailable backend
explicit. A journal entry supports an observed symptom; it does not by itself
prove which current source revision or extension caused it. Do not clear logs,
change log settings or install an agent to complete a read request.
