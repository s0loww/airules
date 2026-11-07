---
description: "OpenSpec integration: working in the openspec/ workspace with specs and change proposals. Триггеры: спецификации, предложение изменений, openspec."
alwaysApply: false
kind: process
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

## Workflow skills and runtime bindings

Use the canonical `openspec-propose`, `openspec-apply-change`,
`openspec-update`, `openspec-sync`, `openspec-archive-change` and
`openspec-explore` skills. Update revises planning artifacts; sync merges
delta specs into main specs while leaving the change active. Neither starts
implementation or deploy. CLI `openspec update` refreshes tool integration
files and is a separate maintenance operation.

When the harness supplies a pinned CLI or an OpenSpec query tool, use that
runtime binding with the current project's selected change/root. Panels and
slash commands invoke these same skills; register one canonical provider
rather than a second competing `opsx-*` skill set. Project policy and access
remain authoritative, including when a runtime UI reports a change complete.

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
| Verification | main agent (closing gate, `verification-matrix`); `tester` only for a new area without an oracle or an independent pass; `code-reviewer` **only on an explicit user request** | gate results; review verdict when requested |
| Documentation and archiving | `doc-writer`, then the `openspec-archive-change` skill | user documentation; deltas merged into `specs/`, change moved to `changes/archive/` |

## todo.md — tech-debt format

Tech debt lives in `openspec/specs/<capability>/todo.md`. Format: one task =
one `## <TaskName>` section; bullets inside the section are details of that
same task (`- ...`, `- [ ] ...`, `- [x] ...`). A task is `open` while it has
at least one unchecked box (or no boxes at all), `done` when all boxes are
checked. The `/techdebt-capture` and `/todolist` commands read and write this
format.
