---
description: "Recording stable non-obvious project decisions for future agents without bloating the working context. Триггеры: журнал решений, зафиксировать решение, договорённость, компромисс."
alwaysApply: false
kind: process
---

# Decisions log

Record decisions that are stable, non-obvious, reusable, and likely to
prevent future mistakes.

**Threshold — all three at once** (adapted from mattpocock/skills, MIT):

1. **Hard to reverse** — changing your mind later has a real cost.
2. **Surprising without context** — a future reader would ask "why on earth
   did they do it this way?".
3. **A real trade-off** — genuine alternatives existed and one was chosen.

A decision that fails any of the three is not worth an entry — the code or
the current files already carry it. Explicit "no" decisions (a rejected
alternative with a non-obvious reason, an intentional deviation from the
obvious path) pass the threshold as often as "yes" decisions — record them
so the next agent does not "fix" the deviation back.

Good candidates:

- source of truth choices;
- disabled or untrusted indexes/tools;
- project rules stricter than the standard;
- recurring verification requirements;
- architectural trade-offs accepted by the user;
- rejected alternatives whose rejection reason is not visible in the code;
- domain constraints.

Do not record secrets, personal data, transient observations, or facts that
are cheap to derive from the current files.

## Where to record

- OpenSpec change: `design.md`, `proposal.md`, or `tasks.md`, when the
  decision belongs to an active change.
- Rules source package: update the rule sources in the distribution
  repository (relative path within the repo tree) when the decision should
  guide future agents. Do not hand-edit the installed copies, except for an
  explicit local unmanaged override.
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

Example entry (a template, not a real decision):

```text
Decision: <short statement of the chosen decision>
Reason: <root cause: a failure, a constraint, or an agreement>
Scope: <where it applies — project, class of modules, class of queries>
Verification: <rule/checklist/test where the decision is captured and checked>
```

A decision made **without the user** — by the lead agent in an autonomous
run — is a different record with more fields: who decided, the rejected
alternative, the impact if rejected, the status ("default applied, awaits
confirmation") and the urgency. It is written at the moment of the decision
in the source and later assembled into a ratification package; the fields and
the shape are in `autonomous-run.md` and `autonomous-run-templates.md`. The
threshold above does not apply to it: every such decision is recorded.

Do **not** append entries to this file: the installed copy is
manifest-managed and gets replaced on update — an in-file journal would be
lost or block the sync forever. Entries live in the locations listed under
"Where to record".

## Not a decision

A diagnosed failure that will recur is a **case**, not a decision: it is
recorded symptom-first so the next person finds it from what they see. The
threshold, the schema and the destinations are in `case-book.md`. Writing the
same content into both logs leaves two half-current copies.
