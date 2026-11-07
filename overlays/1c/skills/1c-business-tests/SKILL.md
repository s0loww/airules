---
name: 1c-business-tests
description: "Create or maintain repeatable tests of 1C calculations, data and business behavior using the project's existing verified runner. Триггеры: бизнес-тесты 1С, регрессия проведения, проверить движения, тест расчёта."
---

# Repeatable business tests for 1C

Use this skill when a regression, acceptance criterion or recurring calculation
needs a saved executable check. A focused observation can be sufficient for a
small change; choosing this skill does not introduce a test framework or an
additional pipeline stage.

## Resolve the contract

Load the applicable rules by stable ID through the project's rule index or the
host's embedded rule loader: `test-model`, `test-discipline`, `testing-1c`, and
`unit-tests-1c` for unit coverage. The project verification/deploy procedure owns
execution order and environment details; this skill supplies test design.

Inspect existing suites, fixture helpers, assertions and the actual run command.
Confirm discovery and assertion APIs from working project examples. Pick the
cheapest channel that observes the behavior:

- A pure computation or conversion fits the configured unit engine.
- Запись, проведение, движения регистров, RLS and data exchange need a scenario
  through a sanctioned data or application channel, not a simulated unit test.
- A form opening or reacting to input needs a client/UI check; use
  `1c-ui-regression` for persistent UI coverage when available.

MCP is optional. Use exposed capabilities when configured, or the existing local
runner; neither a facade nor a particular MCP tool name is a prerequisite. If
the required engine/channel is absent, keep authoring within the available scope
and report the missing execution prerequisite. Adding infrastructure is a
separate scope decision.

## Author a useful check

Derive the oracle from the criterion, a worked example or an agreed baseline,
not from the implementation being tested. Record the case ID, input/initial
state, action, expected values and the seam through which they are observed.
Cover the boundary that exposed the regression and the relevant normal case;
reuse the project's agreed test seams and fixture conventions.

For scenario tests, scope records to a unique run marker and record ownership.
Assert the relevant состав/количество движений and dimensions, not merely the
absence of an exception from проведение. A RLS case runs under the intended
business identity; an administrator's success does not establish its rights.
Use `testing-1c` for platform traps, cache/session freshness and ЖР evidence.

## Execute through the project runner

Before execution, establish the exact target, platform build, tested source
revision and applied configuration/extensions. Inspect setup and teardown
effects too: a command called `unit` can prepare or apply an ИБ. Use the existing
authorization and isolation contract; a familiar operation name is not evidence
of a read-only run.

Run only the selected cases through the verified entry point. Deployment or
loading a test extension, if needed and authorized, remains with the project's
single deploy owner. When the workflow executor is used, preserve its target
guards, bound plan/report identities and native permissions. Static profile
validation, dry run and fixture results establish their own limited facts;
none establishes application behavior on a real target.

Require a fresh machine-readable report with discovered/executed case counts,
expected/actual assertions and source/target identity. Zero cases, discovery
errors, timeouts, setup failures and missing reports do not pass. Reconcile the
selected required cases with executed results; a skipped or absent required case
leaves coverage incomplete even if the runner exits zero. Preserve the
original failure if cleanup also fails. A failed test after deployment can leave
the change applied; cancellation is not rollback. Stop unknown execution before
recovery or retry, following the runner's reconciliation contract.

## Deliver

Return saved test paths, the verified run command, covered criteria, actual
result and report reference. Distinguish authored, executed-passed,
executed-failed, interrupted/indeterminate and blocked. Record fixture cleanup
or retained diagnostic artifacts; remove only this run's owned data through the
authorized procedure. Re-run affected cases after a relevant change within the
project's verification budget, without weakening the oracle to obtain green.
