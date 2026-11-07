---
name: technical-debt
description: "Assess existing architectural debt and prioritize its actual maintenance cost and exit conditions. Триггеры: аудит техдолга, незавершённая миграция, параллельные реализации, дрейф контрактов."
---

# Assess architectural debt

Use for a debt audit or review of a concrete debt concern. Start with the agreed
component and project plans. Establish the intended design and actual behavior;
age, duplication or a temporary marker alone does not prove harmful debt.

## Build an evidenced debt item

Look for mechanisms whose cost persists across changes:

- An interrupted migration with old and new paths still requiring maintenance.
- Parallel capabilities whose fixes, semantics or operational state drift.
- A temporary substitute that still runs but has lost its owner or exit plan.
- Conflicting representations of one contract with demonstrated conversion or
  compatibility cost.
- A technology constraint with a verified support limitation or upgrade barrier.

For each candidate record source locations, reachable users/callers, the present
cost or failure mode, and what makes that cost grow. Distinguish an intentional,
supported dual implementation from an abandoned transition. Verify external
support claims from current primary evidence rather than assuming an old version
is unsupported.

Propose the smallest retirement or containment step, dependencies, an owner to
confirm, and an observable exit condition. Compare cost of delay with the proposed
change cost and risk. Use the project's priority scheme; avoid automatic severity
floors based only on the category name.

## Keep the backlog usable

Inspect the existing issue, decision or debt register before writing another item.
Update the owned record when it already represents the same cause. Keep one
finding per shared cause, linking its manifestations and evidence. Separate new
debt introduced by the current change from pre-existing debt within review scope.

Route a concrete vulnerability, test gap or performance regression to its owning
process when it needs specialized treatment. Link the architectural consequence
instead of creating duplicate findings with different labels. Optional cleanup
with no demonstrated ongoing cost is a suggestion, not a blocking defect.

Report findings and uncertainties with a recommended order of work. Recording a
debt item does not authorize refactoring, dependency replacement, live migration
or publication to an external tracker; follow the task's actual write scope.
