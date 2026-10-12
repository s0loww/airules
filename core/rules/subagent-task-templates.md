---
description: "Ready-made bounded prompts for delegated subagents; the concrete model of a role is resolved at install time from its tier. Load when delegating a bounded task to a subagent. Триггеры: промпт субагенту, шаблон задачи, делегирование, ограниченный воркер."
alwaysApply: false
kind: process
---

# Subagent task templates

Use together with `subagents-model-routing.md`. Keep delegated work bounded,
self-contained and useful while the main agent continues non-overlapping
work. The tier of each role comes from the role registry (rendered into the
root contract's Subagents table); the concrete model is substituted
by the installer.

**Mandatory first line of every subagent prompt:** "Do the work yourself with
your own tools; do not launch other agents and do not wait for background
processes — you have none; temporary files go to `var/tmp/`; finished the
final report — stop." The full discipline block is rendered into every
agent definition at install time; in the prompt this one line is enough. Known
failure without it: the subagent "launches a background task" and waits
forever for a notification that never comes.

**Mandatory closing elements of every prompt:**

- **Stop rules** — when to stop and report instead of continuing: scope
  grows, write zones conflict, verification fails unexpectedly, required
  context is missing, or the task would require a destructive / production /
  paid external action.
- **Output contract** — the report ends with success-criteria status (met /
  not met, point by point) and cleanup status (cleaned / blocked with
  reason / not applicable).

The short templates below carry a condensed form of both; the full worker
contract at the end spells them out — use it for any implementation stream
bigger than a trivial bounded edit.

## explorer-impact

Role: `explorer` (tier per ROLES.md). Scope: read-only.

```text
Read-only impact analysis. Working copy: <path>. Find all local references
to <object/routine/field>. Text/local search first; project code search —
navigation/context only, if available. The source of truth for the current
code is the local project source. Do not edit files. Stop and report if the
scope turns out materially wider than <expected area>. Return: files with
line references, call/usage categories, risky dependencies and gaps; state
what was not covered.
```

## explorer-patterns

Role: `explorer` (tier per ROLES.md). Scope: read-only.

```text
Read-only pattern search. Working copy: <path>. Find existing
implementations similar to <task>. Prefer the local source of truth and the
project rules. Do not edit files. Return: the 3-7 best examples with
paths/lines, which pattern to reuse and what not to copy.
```

## metadata-scout

Role: `metadata-manager`, read-only (tier per ROLES.md). Scope: read-only.

```text
Read-only metadata/form scouting. Working copy: <path>. Inspect <metadata
object/form/layout> using the local XML/code of the project as the source of
truth. Do not edit files. Return: object structure, form
elements/commands/events, related modules, validation risks and the proposed
write zone.
```

## worker-bounded-edit

Role: `developer` / `metadata-manager` / `error-fixer` (tier per ROLES.md;
`error-fixer` uses the `fast` override where the map defines it).

Scope: write only the explicitly assigned files.

```text
Bounded implementation. Working copy: <path>. You are not alone in the
codebase; do not revert or overwrite edits outside your scope. Edit only:
<files>. Implement <specific change>. Follow the project rules. Run the
relevant local checks if available. Stop and report if the scope expands,
verification fails unexpectedly, or required context is missing. Return:
changed files, summary, checks run, success-criteria status, any unresolved
risk, cleanup status.
```

## reviewer-risk

Role: `code-reviewer` / `arch-reviewer` (tier per ROLES.md). Scope:
read-only.

```text
Independent review. Working copy: <path>. Review the current change for
bugs, regressions, missed checks and project-rule violations. Do not edit
files. Optimize for coverage: report every finding with a severity and a
confidence, including uncertain ones — filtering is my pass, not yours.
Return findings first with file:line references, grouped confirmed /
possible, then test gaps and residual risk.
```

## smoke-check

Role: `tester` or `explorer` (tier per ROLES.md). Scope: read-only unless
command execution is explicitly assigned.

```text
Smoke check. Working copy: <path>. Confirm that <feature/rule/tool> is
discoverable and works through the standard entry points. Do not edit files.
Return the exact commands or tool calls, the observed result and pass/fail.
```

## worker-full-contract

Role: any implementing role (tier per ROLES.md). Use for implementation
streams bigger than a trivial bounded edit, and always when several workers
run in parallel.

```text
Bounded worker stream.

Task: <task id, or "ad-hoc: <reason>">
Working copy: <path>. You are not alone in the codebase; do not revert or
overwrite edits outside your scope.

Goal:
<specific finished outcome>

Success criteria:
- <observable result 1>
- <observable result 2>
- Verification evidence is reported with exact commands and outcomes.

Write zone: <allowed files/directories only>
Read-only boundaries: <may inspect but not change; or "none">

Impact map (5-15 nodes the task really touches; not exhaustive):
- <file :: routine or object> — change | check: <what to do>
- ...
- Differs from the sample in: <what the sample did not have to touch; or "no sample">
- Price of one check round: <deployment + smoke, minutes>
- Before the first deployment search the name-keyed lists by the name of a
  neighbouring entity and check every occurrence.

Context to use:
- Files or docs to inspect first: <paths and why>
- Upstream Handoff: <included verbatim below / none>

Verification:
<commands and expected evidence>
You carry the test loop yourself: cheap check → deployment to the test
environment → targeted test → full regression. A red gate has three fix
iterations (a fix plus a re-run of the same gate; syntax failures do not
count); after the third, stop and report.

Stop rules:
Stop and report if scope expands, write zones conflict, verification fails
beyond the iteration budget, required context is missing, or the task would require
destructive actions, production/live mutations, deploys anywhere but the
assigned test environment, force-push, paid external calls, or writes
outside the assigned zone.

Output:
- If another implementing subagent continues this change after you: open the
  report with the Handoff inventory block (exact format in
  `subagent-pipeline.md`) — artifacts, public surface, open stubs, locked
  decisions. The parent passes it on verbatim, so it is the next subagent's
  only inventory; anything you leave out, it will rediscover by reading files.
- Summary; files changed; verification evidence.
- Success criteria status, point by point.
- Risks, blockers, residual gaps.
- Cleanup status: cleaned, blocked with reason, or not applicable.
```
