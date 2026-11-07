---
name: 1c-repository-manage
description: "Inspect or change a 1C configuration repository through explicit object-scoped operations; distinguish repository publication from Git. Триггеры: хранилище конфигурации, захват объектов, обновить из хранилища."
---

# Work with a configuration repository

Use for a task concerning хранилище конфигурации or an established repository
binding relevant to the changed objects. Git is a separate resource: permission
to commit source files does not itself authorize repository publication.

Read the project contract and discover the actual repository capability or
project runner. Inspect its current schema, supported operations and effects.
A facade is optional. A method name in an old note is not a registered tool.
Use [references/operations.md](references/operations.md) before a repository
operation; it defines the object, lock and result distinctions.

Identify the exact repository, ИБ/configuration or extension, repository user,
source revision and requested objects. Configuration holds identity references,
not credentials in reports. When binding is absent, continue source-only work
where useful and resolve the missing project binding before dependent actions.
Do not create a competing environment file or bind/unbind as incidental setup.

Start with the needed status/history/diff facts. Reading repository state may
still launch the platform, read credentials or create reports; follow the
runner's real effects and native permissions. Source-only inspection is not
proof of a live binding, connectivity or lock ownership.

Before a mutation, establish the authorized operation and exact object scope.
Use the existing reviewed runner with its target, source and report checks.
Preserve project guards, execution locks and cancellation/recovery semantics.
After receiving objects, establish which source files match the updated local
configuration before editing or loading files back. Neither a stale checkout
nor an old report supplies that evidence.

Report operation, per-object outcome, resulting revision and locks still held.
A partial or unknown result remains partial or unknown until reconciled; do
not retry publication or discard changes merely because a command timed out.
Follow the project's existing handoff/verification process instead of adding
another mandatory commit or review gate.
