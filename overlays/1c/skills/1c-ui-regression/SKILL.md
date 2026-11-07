---
name: 1c-ui-regression
description: "Create or maintain saved, repeatable 1C UI regression scenarios using the project's configured web-client or Vanessa runner. Триггеры: UI-регрессия 1С, автотест формы, сценарий Vanessa, повторяемый тест веб-клиента."
---

# Repeatable UI regression for 1C

Use an existing suite when a user flow needs repeatable protection. A one-off
form smoke or exploratory session remains a focused UI check; it does not
require a new suite. Authoring scenarios and executing them are separate facts.

Load applicable rule IDs through the project index or embedded rule loader:
`test-model`, `test-discipline`, `testing-1c`, and the project's effective UI
testing policy. The existing verification/deploy procedure determines the
target and lifecycle. Skill selection changes neither that policy nor native
permissions.

## Choose the deployed channel

| Channel | Use | Required evidence |
|---|---|---|
| Existing web-client suite | Saved browser scenarios | Verified runner assertions and fresh result artifacts |
| Existing Vanessa suite | Saved thin-client scenarios | Actual executed features, runner/buildstatus outcome and reports |
| Project hidden-desktop runner | Isolated Vanessa execution without taking over the operator's desktop | The hidden-desktop contract in `testing-1c`, including both clients and cleanup |
| Interactive browser or configured QA capability | Discover controls, smoke a form, investigate a failure | Observations for that run; not a substitute for a replayable suite |

Use the runner and driver actually configured for the channel. A configured QA
MCP can support observation or execution, but it is not mandatory and chat-only
actions are not an unattended suite. An unavailable channel stays unavailable;
do not replace hidden-desktop execution with foreground input silently.

## Build the smallest useful scenario

1. Start from an acceptance criterion or reproduced regression. Name the initial
   state, business-role identity, user action and independently expected visible
   result. If the result is only a calculation or движения регистров, put that
   assertion in the cheaper business-test channel instead of forcing a UI test.
2. Read the project's runner configuration, version/lockfile and working tests.
   Extend their helpers and conventions. Missing infrastructure is a separate
   scope decision; do not install browsers, extensions or services as a hidden
   test prerequisite.
3. Derive reusable controls from actual observations and the runner's supported
   APIs. Metadata names identify logical elements, not proven DOM locators.
   Ephemeral accessibility references, screenshot coordinates and generated form
   instance IDs are not durable locators. If a locator cannot be established,
   retain the scenario as a draft with the missing observation stated.
4. Wait for observable application state. Assert the value retained after focus
   leaves a field and after the server responds; a successful input call alone
   does not prove `ПриИзменении` or persistence. Keep cases independent, with
   stable fixtures or per-run owned records and bounded concurrency/licence use.
5. Make the oracle executable: runner assertions, expected/actual values and a
   failure exit status. A test that merely opens the client, lists cases or
   prints a success message has not verified the behavior. Keep permitted
   screenshots/traces and machine-readable case results in a fresh run directory.
   Reconcile selected required cases to executed results; skipped or absent
   required scenarios cannot contribute a passing coverage verdict.

## Execute and reconcile

Confirm the exact ИБ, platform build, configuration/extensions and source
revision before interpreting a result. Reuse granted test-data permissions;
posting, writing, deleting, restoration and application of configuration changes
remain effects of the project runner, not implicit setup privileges.

For hidden-desktop execution, load that section of `testing-1c` before starting:
a hidden window is not desktop isolation, DryRun is not a scenario pass, and a
black screenshot does not invalidate testing-API assertions. Separate visual
acceptance from that channel's deterministic result. Keep support boundaries
for file/server targets and authentication as declared by the actual runner.

Execute only when effective UI policy and the current authorization allow it.
Keep deploy in the established deploy step, never in an unreviewed fixture
hook. Close only this run's sessions/processes and clean only its owned data;
retain original test and cleanup outcomes separately. An interrupted or unknown
mutation requires reconciliation before reuse of the target, not blind retry.

Deliver scenario paths, covered criteria, verified setup/run entry point, tested
source/target state and evidence. Label authored, executed-passed,
executed-failed, blocked or interrupted/indeterminate accurately. Fix a product
defect through the normal pipeline; correct a mistaken locator or recipe without
silently changing the expected business behavior.
