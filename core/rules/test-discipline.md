---
description: "What makes an automated test worth keeping: agreed seams, red-green slices, mocks only at boundaries, oracles that lie. Триггеры: тесты, регрессионный тест, моки, ложно-зелёный."
alwaysApply: false
kind: invariant
---

# Test discipline

Adapted from the `tdd` skill of
[mattpocock/skills](https://github.com/mattpocock/skills) (MIT). Applies when
the project has — or is adding — an automated test suite; concrete runner
names come from the project profile. Where no suite exists, the
`verification-matrix.md` gates remain the only bar and this rule is not a
reason to introduce one uninvited.

## What a good test is

A test verifies **behavior through a public interface**. The implementation
may change wholesale; the test should not. A good test reads like a
specification of what the code promises, not like a mirror of how it is
written today.

## Seams — where tests go

A **seam** is an interface where behavior can be exercised without editing
the code at that place. Tests live at seams; choosing them is a design
decision, not a by-product of writing tests.

- **Test only at pre-agreed seams.** In the full-cycle pipeline the seams
  are named in the stage-2 plan and approved together with it. Standalone —
  confirm before the first test: *"what is the public interface, and which
  seams do we test?"*
- Prefer existing seams over new ones; prefer the highest seam that still
  gives a deterministic signal; the fewer seams, the better.
- Rationale: everything cannot be tested. Pre-agreeing seams lands the
  effort on critical paths and hard logic instead of scattering it over
  every edge case.
- Wanting to test *behind* the interface is a signal the module has the
  wrong shape — raise it, do not tunnel through.

## The loop

- **Red before green.** Watch the test fail before making it pass; a test
  that never failed proves nothing.
- **Vertical slices.** One test → one piece of implementation → repeat. Each
  next test reacts to what the previous cycle taught.
- Refactoring is a separate pass after green, inside the plan's scope — not
  a step of the red-green loop and not an excuse to rewrite neighbors while
  the suite is passing.

## Anti-patterns — each with its tell

1. **Implementation-coupled test** — mocks internal collaborators, tests
   private routines, or verifies through a side channel (reads the data
   store directly instead of calling the interface). *Tell: the test breaks
   on a refactor that did not change behavior.*
2. **Tautological test** — the expected value is computed the same way the
   code computes it, so the test passes by construction and can never
   diverge from the code. *Expected values come from an independent source
   of truth: a known-good literal, a worked example, the spec.*
3. **Horizontal slicing** — writing the full test list first, then the whole
   implementation. The tests verify *imagined* behavior and freeze the test
   structure before the implementation is understood.

## Oracles that lie — false green and false red

Each item below is a way a suite reports the wrong verdict while every test
"works".

- **A check that cannot fail.** Every validation rule, guard or assertion
  helper gets a *mutant* — a deliberately broken input on which it must
  fail. A rule without a mutant is unverified: it may be dead from birth
  (wrong key, wrong path, wrong case) and pass everything.
- **A trusted in-process validator.** A validator built into the runtime is
  admitted into acceptance only after it agrees with an external reference
  validator on a set of corrupted samples. Output files are always checked
  against the reference, and the first real output goes through it as early
  as possible.
- **Outcome without path.** When a result can be produced by several
  branches (a disjunction, alternative triggers), each branch gets its own
  scenario, and the test asserts *which* branch fired, not only that the
  result exists. A branch no data exercises is reported as *not verified*.
- **No exception ≠ success.** An operation that finished without an error
  is checked by its effect: the count and content of what it wrote, key
  references actually filled.
- **Empty ≠ none.** An empty result from a query or a service may be a
  swallowed error. Validate the query first and get a non-empty answer on a
  known-positive control before reading emptiness as "no data".
- **Silenced errors.** When the code under test logs failures instead of
  raising them, the run's verdict includes the error log for the run's time
  window: any error there fails the run, even if every functional check is
  green.
- **Admin-only runs.** Behavior that depends on permissions is run under
  each target role, not only under an administrator. Access restriction is
  checked quantitatively — the restricted user sees strictly fewer rows,
  and a specific forbidden record is not readable.
- **Fixture defect read as product defect.** Before filing a failure as a
  product bug, check the fixture: generated values against type, length and
  schema; the type of an assigned value against the target field. A
  generator of synthetic data passes the same schema check as the product.
- **Shared state.** A test changes nothing outside its own fixture, or
  reverts what it changed; an unavoidable order dependency is declared in
  the suite, not remembered. Queues and buffers are drained before a run.
  On a shared environment, arrange, act and assert run in one server call —
  data vanishing between steps is first explained by another consumer, not
  by a defect.
- **Stale caches and pre-fix objects.** After changing settings or code,
  reset the runtime's cached values and test on objects created *after* the
  change; objects processed before it keep their old outcome.
- **Reading instead of running.** Behavior of a generated query, a report
  or a template is asserted by running it on control data at the
  boundaries, never by reading its text.

## Mocking

- Mock **only at system boundaries**: external services, clock and
  randomness, and stores for which the project profile provides no test
  instance.
- Do not mock your own modules or internal collaborators — that couples the
  test to the implementation (anti-pattern 1).
- If a mock needs conditional logic inside, the interface is wrong: prefer
  one specific operation per entry point over a generic call-anything
  surface.

## Regression tests for bug fixes

The source of a regression test is the **minimised reproduction** from
`debugging-loop.md` (phase 5). The correct-seam requirement — and the rule
that the *absence* of a correct seam is itself a finding to record, not to
paper over — lives there.

## Companion rules

- `verification-matrix.md` — soft gate D runs the affected tests as part of
  the closing gate.
- `test-model.md` — which channel a test runs through and whether its
  verdict gates or advises.
- `debugging-loop.md` — where the reproduction that seeds a regression test
  comes from.
- `subagent-pipeline.md` — the stage-2 plan is where seams get named and
  approved.
