---
name: 1c-metadata-manage
description: "Create, edit, validate and remove 1C metadata — objects, managed forms, SKD, MXL, roles, EPF/ERF, CF/CFE, subsystems, XDTO, templates — and run infobase and web-publication operations. Use for any change to 1C metadata structure."
---

# 1C Metadata Manage — Skill Dispatch

Use this skill when the task involves **1C metadata structure** (creating, editing, validating, or removing configuration objects, forms, reports, layouts, roles, extensions, XDTO packages) or infobase / web-publication operations.

> **Recommendation.** For any change to metadata XML — prefer this skill (or the `metadata-manager` subagent) over hand-editing `Configuration.xml`, `Form.xml`, `Role.xml` and similar files. The tools handle BOM, encodings, UUID regeneration, ChildObjects ordering and cross-references that are easy to break manually. Direct XML edits are acceptable only for unambiguous one-line fixes (e.g. correcting a synonym typo).

## Writing tools run through the wrapper

Every tool that writes goes through `tools/_common/Invoke-1CEdit.ps1 -Tool <name> <its parameters>`:

- **without `-Apply` it is a DryRun** — a file writer runs, prints the diff and restores the tree; a platform tool (`db-*`, `epf-build`, `web-publish`, …) prints the planned call; a tool with its own `-DryRun` prints its plan;
- **`-Apply` writes**;
- the infobase password goes as `-PasswordEnv <VAR>`; a literal `-Password` is refused;
- a writing script called directly exits `3` with the command to use.

Read-only tools (`*-info`, `*-validate`, decompilers) are called directly or through the wrapper, as convenient. `-Object Справочник.Контрагенты` addresses a target logically instead of by path. Full contract: [edit-preview.md](docs/edit-preview.md).

## Vendor support gate

Writing tools refuse to edit an object that is locked on vendor support ("на замке") in a typical configuration and refuse to delete one still on support — exit `1`, and the refusal is the correct outcome: change it in an extension, or take it off support with `support-edit` only as a stated decision. `SUPPORT_GUARD` in `.dev.env` (`deny` by default, `warn`, `off`). Details: [support-manage.md](docs/support-manage.md).

## Path conventions

Examples use `skills/1c-metadata-manage/tools/...`, relative to the active tool's skills directory (`.claude/skills/...`, `.cursor/skills/...` after installation). Tools read project parameters (`PLATFORM_PATH`, `EXPORT_PATH`, `SUPPORT_GUARD`, `NEW_OBJECT_POSITION`, `PLATFORM_ARGS`, `IBCMD_ARGS`) from `.dev.env` in the project root.

## Dispatch Strategy

Determine task complexity, then choose the execution mode:

### Direct execution — simple / read-only tasks

Use when the task is a **single lightweight query**: checking metadata info, a quick lookup, one validation call. Identify the task domain from the table below, read the corresponding file, and follow its instructions directly.

### Subagent delegation — complex / mutation tasks

Delegate to the **`1c-metadata-manager`** subagent (the `metadata-manager` subagent definition of the active channel) when **any** of the following is true:

- The task **creates, scaffolds, or compiles** metadata (objects, forms, SKD, MXL, roles, EPF, CF, CFE, XDTO, databases)
- The task **edits multiple files** or **spans multiple domains**
- The task involves a **multi-step workflow** (create → edit → validate → fix → re-validate)
- The task requires **reading large domain docs** (load only the domain file relevant to the task)

The subagent already knows how to read the skill docs, execute PowerShell scripts, and validate results. Provide it with the full task description including object names, attributes, types, and any business context from the conversation.

## Task Domain Table

| Task Domain | Keywords | File |
|---|---|---|
| Metadata objects — create, edit, analyze, remove, validate | catalog, document, register, enum, constant, module, attribute, tabular section | [meta-manage.md](docs/meta-manage.md) |
| UUID integrity — duplicate identities in an XML dump | UUID, duplicate uuid, TypeId, ValueId, load failure after generation | [uuid-check.md](docs/uuid-check.md) |
| Managed forms — design, create, edit, analyze, validate | form, Form.xml, UI, elements, commands, events | [form-manage.md](docs/form-manage.md) |
| Form-compile DSL — full JSON DSL for `form-compile`, `--from-object`, presets | form DSL, form-compile, autoCmdBar, columnGroup, form preset | [form-compile-dsl.md](docs/form-compile-dsl.md) |
| Data Composition Schema (DCS/SKD) — create, edit, analyze, decompile, validate | report, DCS, SKD, data composition, data set, query, decompile | [skd-manage.md](docs/skd-manage.md) |
| Spreadsheet documents (MXL) — create, decompile, analyze, validate | MXL, spreadsheet, template, print form, layout | [mxl-manage.md](docs/mxl-manage.md) |
| Roles and access rights — create, analyze, validate | role, rights, RLS, access, permissions | [role-manage.md](docs/role-manage.md) |
| External processors/reports (EPF/ERF) — scaffold, build, dump, validate | EPF, ERF, data processor, external report, build, dump | [epf-manage.md](docs/epf-manage.md) |
| BSP/SSL registration and commands | BSP, SSL, ExternalDataProcessorInfo, registration, command | [bsp-manage.md](docs/bsp-manage.md) |
| Configuration (CF) and dump integrity — create, edit, analyze, validate | configuration, Configuration.xml, CF, missing/orphan objects, ConfigDumpInfo | [cf-manage.md](docs/cf-manage.md) |
| Extensions (CFE) — create, borrow, diff, patch, validate | extension, CFE, borrow, interceptor, patch | [cfe-manage.md](docs/cfe-manage.md) |
| Vendor support state — "на замке", editability, off-support | support, поддержка, на замке, SUPPORT_GUARD | [support-manage.md](docs/support-manage.md) |
| XDTO packages — analyze, create from XSD, export, edit, validate | XDTO, package, XSD, ФабрикаXDTO, namespace, exchange format | [xdto-manage.md](docs/xdto-manage.md) |
| Databases — create, run, load, dump, DT backup | database, infobase, create DB, run 1C, dt, backup, .v8-project.json | [db-manage.md](docs/db-manage.md) |
| Subsystems — create, edit, analyze, validate | subsystem, command interface, ChildObjects | [subsystem-manage.md](docs/subsystem-manage.md) |
| Command interface — edit, validate | CommandInterface.xml, commands visibility, groups | [interface-manage.md](docs/interface-manage.md) |
| Templates/layouts management — add, remove | template, layout, SpreadsheetDocument, HTML template | [template-manage.md](docs/template-manage.md) |
| Help pages — add, manage | help, built-in help, documentation | [help-manage.md](docs/help-manage.md) |
| SSL/BSP subsystems patterns | SSL patterns, standard subsystems, BSP events | [ssl-patterns.md](docs/ssl-patterns.md) |
| Query writing — compose new queries from scratch | write query, build query, query template, ВЫБРАТЬ, ИЗ, СОЕДИНЕНИЕ, virtual tables, batch queries | [query-writing.md](docs/query-writing.md) |
| Query optimization | query, temporary table, join, DCS optimization | [query-optimization.md](docs/query-optimization.md) |
| Web publishing — publish, unpublish, status, stop | web, publish, Apache, web client, webdav, default.vrd | [web-manage.md](docs/web-manage.md) |
| The wrapper — DryRun / `-Apply`, logical addresses, exit codes | Invoke-1CEdit, dry run, preview, -Apply, -Object | [edit-preview.md](docs/edit-preview.md) |
| CF / CFE / EPF binaries without the platform | v8unpack, unpacked sources, obj.bsl, elem.json | `rules/v8unpack-source-structure.md` |

**If the task spans multiple domains**, the subagent will read all relevant docs automatically (or read each one directly for simple tasks).
