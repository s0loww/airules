---
description: "Per-task MCP tool playbooks (writing code, review, refactoring, error fixing, performance, forms, integrations, documentation, XML metadata, platform-version comparison)"
alwaysApply: false
kind: process
---

# Tool Usage by Task — Playbooks

Each playbook below names **tool categories**, not concrete servers. The concrete tool name behind every category is resolved from the project's MCP profile in the root contract (`AGENTS.md → Tooling`). Start with the project's playbook / routing helper to confirm the current routing before a task.

**Tool categories used below:**

- **metadata structure** — inspect a metadata object's passport, attributes, structure, XSD schema.
- **code search** — find BSL by behaviour (semantic), by exact identifier / literal (fulltext / grep), or by routine name.
- **call graph** — callers / callees, call hierarchy, change-impact / dependency tracing.
- **code templates** — reusable implementation templates.
- **standard library** — БСП (SSL) subsystem / helper search.
- **platform documentation** — verify a built-in type / method by exact name or by description.
- **ITS standards** — methodology and standards lookup.
- **syntax check** — static syntax, logic/performance, and style/standards analysis of BSL.

> Concrete tool names for each category — from the project's MCP profile (root contract `AGENTS.md`). Where the profile exposes two navigation routes — (a) structural metadata/code index and (b) live-code / call-graph — use whichever is available; prefer the structural index for object passports and the live-code route for fresh post-commit code and precise call graphs.

## Subagent Preflight

For Full-cycle tasks, read `subagents-model-routing.md` and make a subagent-decision before the main analysis:

- delegate a bounded sidecar task to a generic `explorer` / `worker` on a lighter model when this saves budget and does not block the critical path;
- keep the work local when it is a Quick-fix, immediate blocker, tightly coupled, high-risk, or requires final frontier-model judgment;
- when spawning, specify bounded responsibility, read/write scope, source-of-truth boundaries, model override, and expected output.

Good sidecars: initial indexed source search, RAG navigation, impact lists, pattern gathering, smoke checks, and independent review.

For collaboration modes, preflight, context packs, decisions, and verification depth, read:

- `collaboration-modes.md`
- `preflight-worktree.md`
- `context-packs.md`
- `decisions-log.md`
- `verification-matrix.md`

## MCP-first search — quick first-pick

For any 1C **project-source** search (code, metadata, usages, call chains, structure, forms) MCP project-index tools come **first**; `Grep` / `Glob` are the last resort, gated by an explicit "what was tried" note.

| Need | First call (category) | If empty — next |
|---|---|---|
| Current MCP routing | project playbook / routing helper | project profile / `AGENTS.md` |
| BSL code by behaviour / description | code search (semantic) | code search (hybrid) → code search (grep) |
| BSL code by exact identifier / literal | code search (fulltext) | code search (grep) → only then `Grep` |
| Routine by name | code search (function, exact) | code search (function, grep) → `Grep` |
| Understand a metadata object | metadata structure (object passport) | metadata structure (details) |
| Metadata by name / structure | metadata structure (search) | metadata structure (names only) |
| Metadata by Russian description / synonym | metadata structure (description / business search) | metadata structure (search) |
| Usages of an object | call graph (usages / objects-using) | call graph (dependencies, reverse) |
| Impact of a change | call graph (impact trace, downstream) | call graph (dependencies, single-level) |
| Call graph (callers / callees) | call graph (call-chain, callers/callees) | call graph (method call hierarchy) |
| Module structure overview | metadata structure (module structure) | form layout (for forms) |
| Form layout | form layout (inspect) | form search |
| Canonical pattern / template | code templates (+ standard library for БСП) | — |
| Platform API verification | platform documentation (by name / by description) | platform documentation (help search) |
| ITS standards | ITS standards (search → fetch every relevant doc) | — |

**Response gate.** When a result involved `Grep` / `Glob` on project source, add one short line naming the MCP attempts that fell short, e.g. *"Tried code search (exact) and code search (grep), both empty; fell back to `Grep` for the literal `<...>`."* `Grep` / `Glob` are legitimate first picks only for non-indexed targets (`.md`/`.json`/`.yaml`, rule/command sources, `openspec/`, logs, build output, or a file already read this session).

## Writing New Code

0. **No source for the object in the working copy?** Export it from the
   infobase first — `getconfigfiles.md`. Editing against a stale or absent
   source is how a change silently lands on top of someone else's.
1. **code templates** — find similar implementations.
2. **metadata structure** — full passport of the target metadata object (structure, forms, dependencies, code, roles).
3. **code search** — review existing patterns in the configuration.
4. **code search (function)** — find an existing procedure/function by name for reuse.
5. **metadata structure (module structure)** — overview of the module you intend to edit.
6. **metadata structure** — verify metadata structure and attribute types.
7. **platform documentation** — verify built-in functions by exact name, or search by description.
8. **standard library** — find reusable БСП functions.
9. **syntax check** — verify syntax, then logic/performance defects, then style / ITS-standards compliance.

## Code Review

1. **code search** — verify pattern compliance.
2. **call graph (impact / dependencies)** — impact analysis of the change.
3. **call graph (call-chain / hierarchy)** — BSL call chains, callers/callees.
4. **metadata structure** — correct metadata usage.
5. **platform documentation** — verify method/property existence, or search by description.
6. **syntax check** — style and ITS compliance, then bugs and performance issues.
7. **ITS standards** — cross-check against standards.

## Architecture Design

1. **metadata structure** — passport of key metadata objects and existing structure.
2. **call graph (impact / dependencies)** — dependency map across usage, movement, and call relations.
3. **call graph (objects-using)** — find all objects referencing the given one.
4. **code search** — existing architectural patterns.
5. **call graph (call-chain / hierarchy)** — code coupling and call chains.
6. **code templates** + **standard library** — compare with proven templates and standard subsystems.
7. AI architectural hints — treat as a hint, not authority; verify every claim.

## Error Fixing

1. **syntax check** — syntax errors, then logic and performance issues.
2. **code search (function)** — locate the failing procedure/function.
3. **code search** — related patterns (full body of a specific routine when supported).
4. **metadata structure (module structure)** — module context around the error.
5. **call graph (call-chain / hierarchy)** — how the error propagates through the call chain.
6. **platform documentation** — verify function/method names, or fallback by description.
7. **metadata structure** — verify metadata names and attributes.
8. AI targeted fix — treat output as a draft, re-validate.

Follow the four-phase loop in `systematic-debugging.md`; this playbook lists the tool categories per phase.

## Performance Optimization

1. **code search** — locate slow patterns (semantic queries like "медленный запрос", "цикл по выборке").
2. **call graph (call-chain / hierarchy)** — identify hot call chains.
3. **call graph (impact / dependencies)** — objects that cause cascading issues (pure code paths).
4. **metadata structure** — verify indexes and metadata structure.
5. **syntax check** — bottleneck / performance static analysis.
6. AI optimization — treat as a draft; re-validate with syntax check.
7. **code templates** — optimized templates and known patterns.
8. **ITS standards** — performance standards.

## Refactoring

1. **metadata structure** — passport of the object being refactored.
2. **call graph (impact / dependencies, downstream)** — what breaks on change.
3. **call graph (call-chain / hierarchy, callers)** — all callers before signature or export changes.
4. **call graph (usages)** — every type reference before renaming/removing.
5. **code search** — every code pattern related to the object.
6. **code search** (broad, post-refactor) — verify that no old references remain.
7. **syntax check** — validate the result (bugs, then style / ITS).

## Generating / Modifying Metadata XML

1. Use the `1c-metadata-manage` skill or `1c-metadata-manager` subagent for XML mutations whenever feasible.
2. **metadata structure (names only)** — similar objects as examples.
3. **metadata structure (XSD schema)** — schema for the target metadata type.
4. Write / modify XML against the schema and examples; generate unique UUIDs and update `Configuration.xml` / child ordering when required.
5. **XML verification** — validate against XSD; fix errors. If no schema validator is exposed in the session, fall back to the project metadata validation scripts (compile/load smoke) and report the fallback used.
6. See `metadata-xml-workarounds.md` for the recurring XML traps.

## Form Analysis and Generation

1. **form search** — similar existing forms in the configuration.
2. **form layout (inspect)** — structure of the found form (elements, bindings, commands, events).
3. **metadata structure (names only)** — metadata objects for XML references.
4. **metadata structure (XSD schema for `Форма`)** — schema of `Form.xml`.
5. Generate `Form.xml` based on examples and schema.
6. **XML verification** — validate `Form.xml` against XSD.
7. **1c-metadata-manage** skill (form-manage) — compilation and validation.

Domain rules: `forms.md` (router) → `forms-add.md`, `forms-events-add.md`, `form-module.md`, `form-reserved-names.md`.

## Integrations

Use this playbook when writing HTTP services / clients, REST integrations, file or message-queue exchanges, webhooks. Domain rules — `integrations-add.md`.

1. **standard library** — check for ready-made БСП subsystems ("Интернет-поддержка пользователей", "Обмен данными", "Получение файлов из Интернета", "Цифровая подпись").
2. **code templates** — integration templates (HTTP request, JSON parsing, signed payloads, retry policy).
3. **code search (semantic)** — existing integrations in the configuration ("HTTP запрос", "отправка JSON", "парсинг ответа").
4. **platform documentation** — verify platform types by exact name (`HTTPСоединение`, `HTTPЗапрос`, `ЧтениеJSON`, `ЗаписьJSON`, `ЗаписьXML`, `ЧтениеXML`), or fallback by description.
5. **metadata structure (XSD schema)** + **XML verification** — when the contract is XML with a known XSD.
6. **ITS standards** — long-running operations, secure password storage, asynchronous external components.
7. **code search (function)** + **metadata structure (module structure)** — locate or extend the integration common module.
8. After implementation: **syntax check** (syntax → logic/performance → style/ITS).

## Documentation

1. **code search** — find code to document.
2. **metadata structure** — metadata structure.
3. **metadata structure (module structure)** — list of procedures/functions.
4. **platform documentation** — by exact name, or search by description.
5. **platform documentation (help search)** — existing help articles.
6. **ITS standards** — methodological articles.

## Comparing Platform Versions

1. **platform documentation (version diff)** — what changed between versions.
2. **platform documentation (version-specific search)** — documentation for a specific version.
