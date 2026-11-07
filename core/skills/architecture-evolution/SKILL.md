---
name: architecture-evolution
description: "Assess a design or substantial change for compatibility, migration and preservation of existing behavior. Триггеры: ревью архитектуры, эволюция системы, совместимость, миграция."
---

# Review how a system can evolve

Start with the requested change, the project's current architecture and its real
callers or data consumers. Identify the behavior intended to change and the
contracts intended to remain. Apply the project's existing architecture and
review process; this skill does not introduce a reviewer after every edit.

## Examine the transition

- Trace the changed boundary: interfaces, persisted formats, error behavior,
  configuration and ordering assumptions. Include callers outside the edited
  component when evidence shows they depend on it.
- Compare proposed module ownership and dependency direction with the current
  design. A different pattern needs an explained trade-off, not rejection merely
  because it is new. Reuse a capability when it fits; identify the transition
  owner when a replacement must coexist with it.
- For data relocation, identify where new writes go, how existing records move,
  how old readers behave, and when old state can be retired. For an interrupted
  transition, establish the state from which it can resume and the evidence of
  completion. Do not assume a source-code rollback reverses migrated data.
- In a refactor, compare observable behavior before and after: boundary cases,
  failures, side effects and caller expectations. Separate intentional behavior
  changes so reviewers can assess them as changes rather than cleanup.
- Test extensibility against a concrete nearby use case supported by the task
  or project roadmap. Avoid speculative extension points with no likely consumer.

## Deliver a decision the owner can use

For a conflict, name the affected contract, a concrete failing transition or
caller, its impact and a compatible migration or bounded alternative. Record
what must be decided before implementation and what can remain incremental.
Use existing evidence and relevant contract tests; missing access stays an
explicit coverage gap.

Keep prospective design risks separate from existing debt. Record an existing
debt finding through the project's debt owner instead of repeating it in several
review dimensions. An accepted compatibility compromise remains visible with
its reason and exit condition; this review does not authorize the migration.
