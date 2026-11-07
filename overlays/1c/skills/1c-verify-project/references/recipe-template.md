# Project verification recipe template

Use the sections that fit the project's existing format. Replace sample fields
with verified bindings before treating a procedure as runnable. A missing binding
is recorded as blocked with its owner/prerequisite, not guessed.

## Scope and configuration references

- Project capability or acceptance slice being checked.
- Source directories/revision and configuration/extension identity.
- Testing profile reference; target identity/environment and exact platform build.
- Granted execution scope, effective UI policy and intended business-role users.
- Required capability bindings and supported file/server/authentication boundary.

Keep actual endpoints, local paths, credential references and fixture data in
the project's designated local configuration. A distributed generic recipe must
not contain another project's values. Credential values/authentication state
belong neither in the skill nor in committed evidence.

## Operations and lifecycle

| Phase | Verified entry point | Inputs/config reference | Effects | Readiness/evidence | Owner |
|---|---|---|---|---|---|
| Inspect | Existing metadata/profile inspection | Applicable profile/source | Declared actual effects | Target/tool capability facts | Project-defined |
| Prepare, if needed | Existing build/deploy/restore procedure | Reviewed runner and target binding | Processes, report writes and any target mutations | Source/applied identities, bound report | Single deploy owner |
| Check | Existing suite or permitted client/data channel | Selected criteria and fixtures | Read-only or enumerated mutations | Executed cases and expected/actual values | Test owner |
| Cleanup | Existing run-scoped stop/cleanup procedure | Owned run/session/data identifiers | Declared cleanup effects | Completed or retained artifacts/errors | Lifecycle owner |

Do not turn the table into an invented generic command interface. Some projects
have no prepare phase for the selected slice; others require explicit loading
of a test extension. Record the existing procedure and its real conditions.

## Feature inventory

| Feature / criterion | Real entry point | Observable expected effect | Channel / case ID | Source/applied identity | Status | Evidence / prerequisite |
|---|---|---|---|---|---|---|

Use status meanings consistently:

- **authored:** a recipe/scenario exists, execution not established;
- **source-only:** the relevant code/metadata was inspected, not exercised live;
- **live-verified:** the real entry point ran with the stated identity and evidence;
- **failed:** execution produced an actual expected/observed mismatch;
- **blocked:** a named prerequisite or authorization is missing;
- **interrupted/indeterminate:** execution or mutation state cannot be established.

An empty inventory is incomplete. Counts of all statuses must reconcile to the
in-scope feature inventory. An unavailable channel is not silently replaced by
source inspection or by a fixture simulation.

## Run record

- Unique run/report reference and time window.
- Exact selected cases; discovered/executed counts and runner exit/result status.
- Source/configuration/extension/target identities and relevant role/session state.
- Expected/actual observations and bounded sanitized evidence references.
- What was not run and why; historical evidence kept separately from this result.
- Target mutation state, owned lifecycle artifacts, cleanup outcome and any
  retained lock/recovery prerequisite.

Preserve the original test failure when cleanup also fails. A deploy report
establishes only what that protocol proves; a passing preview or unchanged
fixture establishes no live application behavior. Recovery has its own evidence
and does not rewrite an earlier failed run into a pass.
