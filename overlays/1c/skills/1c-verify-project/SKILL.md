---
name: 1c-verify-project
description: "Create or maintain a project-local 1C verification recipe that maps features to real entry points, runner effects and evidence; distinguish live checks from source-only coverage. Триггеры: verify проекта 1С, сквозная проверка, паспорт проверок, актуализировать сценарии приёмки."
---

# A project-local verification recipe

Produce or maintain a reusable recipe for the next session. It composes the
project's real test/deploy mechanisms and our verification pipeline; it adds no
launcher, service, mandatory browser or automatic deployment.

Locate an existing project verification procedure first. Update that owner
instead of creating a second competing recipe. A project-local `verify-<slug>`
skill is one suitable form when the host supports it; an existing runbook plus
scenario/report definitions can serve the same purpose.

## Discover the verification surface

Read the project contract, current acceptance criteria/specifications, testing
profile and existing runners. Resolve rules through the project index or host
rule loader: `verification-matrix`, `test-model`, `testing-1c`, and the relevant
test-design/metadata rules. Read only the configuration needed for the task;
recipes carry configuration references, not credential values.

Map each in-scope feature to its real entry point and observable effect: a form
or command, обработка, scheduled job, API, report or document flow. Distinguish
the feature from the test channel. A successful metadata load does not establish
that a form opens; проведение needs expected движения регистров, not just a clean
return. Mark uncovered capabilities explicitly rather than inferring coverage
from a suite's name.

Record the actual capability bindings: local runner, configured browser/Vanessa,
sanctioned data channel or optional MCP. A facade is one routing arrangement,
not a dependency of the recipe. Confirm each operation exists and inspect its
effects; metadata validation and building a plan are not execution.

## Create or reconcile the recipe

Use [references/recipe-template.md](references/recipe-template.md) for the
information contract, preserving the project's established format. A completed
recipe names real commands/configuration references; unresolved entries remain
explicitly blocked, not executable-looking placeholders.

- **Readiness:** identify the exact ИБ, source revision, applied configuration/
  extensions, platform build and required business identities. An already-ready
  stand can be reused according to its contract. Restore/load/start only when
  needed and authorized; creating a recipe does not authorize those effects.
- **Preflight:** separate offline metadata inspection from operations that start
  processes, read credentials or write reports. Even a runner's `doctor` or
  `deploy-preview` can have such effects. Check the declared channel, session
  freshness and source-to-target match without broadening trust or permissions.
- **Feature checks:** bind acceptance criteria to saved deterministic scenarios
  where available. Interactive exploration supplies observations for this run;
  it does not replace an affected regression gate. Use `1c-business-tests` or
  `1c-ui-regression` when their workflows are needed, not as mandatory wrappers.
- **Evidence:** each run gets a fresh report reference, tested identities,
  expected/actual observations and timestamps. Report source-only, blocked and
  live-verified features separately. Old evidence is historical until its
  source/target applicability is established for the current run.
- **Lifecycle:** name what this run owns, what remains shared, and the supported
  stop/cleanup/recovery procedure. Cleanup is not permission to restore an ИБ or
  stop shared services. A changed/applied target remains changed after a failed
  test unless an authorized recovery actually proves restoration.

Use existing workflow/runners without bypassing their reviewed-code trust,
target/environment guards, plan/report binding or resource locks. File and
server targets have distinct capabilities; a file-only runner is not a server
adapter. Preview and fixture results cannot be presented as live feature proof.

## Prove only what ran

When execution is within scope, follow the written recipe in a fresh permitted
session and exercise the selected acceptance slice. Capture the actual evidence
and lifecycle outcome. If only authoring or offline work is authorized, deliver
the recipe as authored/source-only with the runtime prerequisites stated.

On maintenance, compare the inventory with current entry points and criteria.
Classify differences as recipe drift, product regression or unavailable
environment/channel. Fix the recipe where it is wrong; keep a product failure
visible. Do not claim every feature was rechecked when only a slice ran.

Return the recipe path, feature/status counts, what actually ran, evidence
references, unresolved prerequisites and cleanup/recovery state. Use the
project's existing handoff/memory ownership rules; skill selection does not
create a second session log or authorize commits/publication.
