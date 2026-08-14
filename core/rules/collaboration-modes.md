---
description: "Collaboration modes: exploration, edit, review, OpenSpec, emergency fix. Load when choosing how deep to go on a task or whether to delegate. Триггеры: режим работы, разведка, правка, ревью, экстренный фикс"
alwaysApply: false
kind: process
---

# Collaboration modes

An explicit mode is chosen when the task can be solved cheaper or safer by
changing depth, tooling, or delegation. Modes are aligned with the
`quick-fix` / `full-cycle` triage from the root contract: exploration and
edit are the main full-cycle states, emergency fix is an accelerated
quick-fix.

## Modes

### Exploration

Goal: understand the scope without making edits.

When: unclear requirements, impact analysis, codebase navigation, risk
discovery.

Output: a short map of objects/files, relevant rules and project-profile
tools, risks, recommended next step.

Subagents: the `explorer` role fits (read-only, tier low) — see
`subagents-model-routing.md`.

### Edit

Goal: a minimal change that is safe for the production system.

When: bounded implementation after enough context has been gathered.

Output: changed files, checks performed, residual risk.

Subagents: a writing role (`developer` / `metadata-manager`, tier medium) —
only with a non-overlapping write scope and an expected edit that is clear
in advance.

### Review

Goal: find real bugs, regressions, missed checks, and risky assumptions.

When: the user asks for a review. A risky implementation on its own does not
open this mode — the closing gate of `verification-matrix.md` covers it.

Output: findings first, ordered by severity with `file:line` references;
summary after the findings.

Subagents: an independent reviewer (`code-reviewer` / `arch-reviewer`,
tier high) — on the user's request, for high-risk or wide changes.

### OpenSpec

Goal: keep proposal / design / tasks / specs consistent.

When: feature tracks, architectural decisions, staged implementation.

Output: current status of the change, updated tasks/specs, checks.

Subagents: delegate bounded artifact checks, not the final acceptance.

### Emergency fix

Goal: restore a broken path with a minimal blast radius.

When: syntax / runtime errors, failing checks, urgent regressions.

Output: root cause, minimal fix, verification.

Subagents: avoid, except for a read-only side check that can run in
parallel.

Urgency overrides the non-trivial-bug escalation of the pipeline triage:
restore first with the minimal fix, then route the root-cause work through
normal triage (`debugging-loop.md`, "Scope and scale"). If the minimal fix
itself touches a stage-1 risk escalator (`subagent-pipeline.md`), the
follow-up full-cycle pass is mandatory, not optional.

## Choosing a mode

- If the user only asks a question — start in `Exploration`.
- If they ask to implement or fix — start in `Edit` after minimal
  context.
- If they ask for a review — `Review`.
- If they reference `openspec/` — `OpenSpec`.
- If checks are failing or a production path is blocked — `Emergency fix`.
