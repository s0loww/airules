---
description: "OpenSpec integration. Load when working with the openspec/ workspace (specs and change proposals). Триггеры: спецификации, предложение изменений, артефакты, воркспейс openspec"
alwaysApply: false
---

# SDD integration — OpenSpec

[OpenSpec](https://github.com/Fission-AI/OpenSpec) is the only SDD
framework supported in this distribution. Other SDD frameworks (Memory
Bank, Spec Kit, TaskMaster, etc.) are **not** supported — do not generate
or update artifacts for them, even if the corresponding folders or MCP
servers happen to be present in the project.

## Canonical sources

The workspace structure, the spec format, the delta format, and the full
workflow are described in the workspace itself — do not duplicate them
here:

| Topic | File |
|------|------|
| Workspace structure, commands, update policy | [`openspec/README.md`](../openspec/README.md) |
| Spec format and conventions for `openspec/specs/` | [`openspec/specs/README.md`](../openspec/specs/README.md) |
| Change proposal structure and delta format for `openspec/changes/` | [`openspec/changes/README.md`](../openspec/changes/README.md) |

Read these files before writing or editing OpenSpec artifacts.

## Subagent → OpenSpec artifact mapping

Each subagent is responsible for specific OpenSpec artifacts. The table
defines where each subagent is allowed to write.

| Subagent | Reads | Writes |
|----------|--------|-------|
| **analytic** | existing `specs/` for context | `changes/<id>/proposal.md`, new entries in `specs/` (via deltas) |
| **planner** | `specs/`, `changes/<id>/proposal.md`, `design.md` | `changes/<id>/tasks.md` |
| **architect** | `specs/`, `changes/<id>/proposal.md` | `changes/<id>/design.md` |
| **arch-reviewer** | `changes/<id>/design.md`, `proposal.md`, `specs/` | review notes (no artifact writes) |
| **developer** | `specs/`, active `changes/<id>/` | code; updates `changes/<id>/specs/` deltas and checks off items in `tasks.md` |
| **metadata-manager** | `specs/`, active `changes/<id>/` | data structure/schema; spec deltas under `changes/<id>/specs/` for new/changed schema objects |
| **refactoring** | `specs/`, active `changes/<id>/` | code; updates deltas only when observable behavior changes |
| **performance-optimizer** | `specs/` (non-functional/perf requirements) | recommendations only (no artifact writes — a read-only role; edits go to `developer`/`refactoring`) |
| **error-fixer** | active `changes/<id>/` | code; usually no spec changes (a bug fix preserves the intended behavior) |
| **tester** | `specs/` (scenarios), `changes/<id>/tasks.md` | test results, checkmarks in `tasks.md` |
| **code-reviewer** | `specs/`, `changes/<id>/specs/` deltas | review verdict against the requirements (no artifact writes) |
| **doc-writer** | `specs/`, `changes/archive/` | user documentation derived from specs |

## Phase → subagent mapping

The default `propose → apply → archive` workflow maps onto subagents as
follows:

| Phase | Lead subagent(s) | Result |
|------|------------------------|-----------|
| Requirements | `analytic` | `proposal.md` + initial deltas in `changes/<id>/specs/` |
| Design | `architect` (optional review by `arch-reviewer`) | `design.md` |
| Planning | `planner` | `tasks.md` |
| Implementation | `developer`, `metadata-manager`, `refactoring`, `error-fixer` (`performance-optimizer` advises read-only) | code + updated deltas + checked-off `tasks.md` |
| Verification | `tester`; `code-reviewer` **only on an explicit user request** | test results; review verdict when requested |
| Documentation and archiving | `doc-writer`, then the `openspec-archive-change` skill | user documentation; deltas merged into `specs/`, change moved to `changes/archive/` |

## todo.md — tech-debt format

Tech debt lives in `openspec/specs/<capability>/todo.md`. Format: one task =
one `## <TaskName>` section; bullets inside the section are details of that
same task (`- ...`, `- [ ] ...`, `- [x] ...`). A task is `open` while it has
at least one unchecked box (or no boxes at all), `done` when all boxes are
checked. The `/techdebt-capture` and `/todolist` commands read and write this
format.
