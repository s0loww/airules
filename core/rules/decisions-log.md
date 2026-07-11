---
description: "How to record stable project decisions without bloating the working context. Load when a stable non-obvious decision needs to be recorded for future agents. Триггеры: журнал решений, зафиксировать решение, договорённость, компромисс"
alwaysApply: false
---

# Decisions log

Record decisions that are stable, non-obvious, reusable, and likely to
prevent future mistakes.

Good candidates:

- source of truth choices;
- disabled or untrusted indexes/tools;
- project rules stricter than the standard;
- recurring verification requirements;
- architectural trade-offs accepted by the user;
- domain constraints.

Do not record secrets, personal data, transient observations, or facts that
are cheap to derive from the current files.

## Where to record

- OpenSpec change: `design.md`, `proposal.md`, or `tasks.md`, when the
  decision belongs to an active change.
- Rules source package: update the rule sources in the distribution
  repository (relative path within the repo tree) when the decision should
  guide future agents across all channels. Do not hand-edit installed
  channel copies, except for an explicit local unmanaged override.
- Project knowledge store: global, critical, stable, non-derivable facts
  for humans and future handover.
- Documentation: `docs/decisions/*`, if the repository keeps ADR-like
  documents.

## Format

Short entries:

```text
Decision: <what was chosen>
Reason: <why>
Scope: <where it applies>
Verification: <how to know it still holds>
```

## Recorded decisions

This section is maintained in the target project. Example entry (a
template, not a real decision):

```text
Decision: <short statement of the chosen decision>
Reason: <root cause: a failure, a constraint, or an agreement>
Scope: <where it applies — project, class of modules, class of queries>
Verification: <rule/checklist/test where the decision is captured and checked>
```
