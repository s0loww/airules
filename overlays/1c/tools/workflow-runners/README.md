# Existing project runner bindings

Offline inspection and fixed PowerShell argv compilation for agent-1c and the
TestEnv unit entrypoint. Node 20+, builtins plus sibling workflow core/profile
gate. Tests: `node --test test/*.test.mjs`. No process/1C/COM/MCP/database/env
access is performed. Only bounded UTF-8 metadata files inside the registered
project are read; symlinks and traversal are rejected.

Binding example (data, not an execution permission):

```json
{
  "schemaVersion": 1,
  "kind": "agent-1c",
  "runnerPath": "tools/agent-1c/agent-1c.ps1",
  "profilePath": "agent-1c.json",
  "sourceKind": "extension",
  "extensionName": "ExampleExtension",
  "exactBuild": "8.3.27.1989"
}
```

`inspectRunnerBinding({root,binding})` checks the actual runner declaration,
profile metadata and hashes fixed runner dependencies. Unit/probe declarations
do not imply a passing run. Old agent-1c command sets remain old; server targets
do not acquire file-only Vanessa/ibsrv support. Source kind/name/build are supplied
facts checked for consistency, not verified against XML/platform/target here.
External INI and environment credential references are never read or resolved.
Inline credentials are rejected by the profile gate; returned metadata does not
include profile contents, credential paths/values or target connection strings.

`closureDigest` covers all regular `.ps1`/`.psm1` files under the agent-1c tool
directory plus the fixed toolchain lock (or fixed RunUnitTests/TestEnv pair for
TestEnv). Traversal and reads are bounded; symlinks are rejected. Other files,
including env/log files, are not opened. `codeClosure.files` records safe relative
paths/hashes; `fingerprintPaths` additionally includes the profile. A newly added
local PowerShell module changes the closure digest. The host must require this
digest in its machine-owned trusted-runner allowlist before execution. There
are no shipped approved digests. Project/model edits cannot grant themselves
trust by retaining a familiar filename or doctor command label. This is not
static proof of arbitrary PowerShell dependency closure: external/dynamic code
loading remains part of code review, and runner invocation stays disabled here.

Agent operations: doctor, analyze, deploy-preview, deploy-apply, unit, test,
test-hidden, serve, stop. All remain `enabled:false` until a host authorizes them.
Deploy apply is supported only by a runner implementing the bound workflow
report protocol; an older runner with only `-Apply` is not sufficient. Doctor writes a
report directory. Analyze launches BSL LS and writes reports. Even deploy-preview
starts PowerShell, reads credential references and writes reports: it is not an
offline/read-only inspection and is never executed automatically.

TestEnv supports only `scripts/RunUnitTests.ps1` + its `scripts/TestEnv.ps1`
dependency. Unit prepares/imports/applies a test database, so it is a metadata-
changing operation requiring isolation and authorization, not a harmless check.
The runner needs additional timeout/nonzero-test/evidence guards. The historical
UI launcher has broad process/lifecycle behavior and manual interaction; neither
RunUITests nor RunAllTests is compiled as an unattended gate.

`compileRunnerCommand({runnerKind,operation,root,runnerPath,profilePath?,pwshPath})`
returns `{command,args,cwd,effects,enabled:false,requiresInspection:true}`.
PowerShell is a trusted absolute registered interpreter. There is no shell
string, ExecutionPolicy bypass, arbitrary extra arguments, bootstrap or alternate
script fallback. `-Apply` is emitted only for the explicit `deploy-apply` operation,
which additionally requires a complete `deployContext` (run/step/source/target/
profile identities, exact build and target path). The host must separately inspect/recheck hashes,
capability support, credentials/target identity and permissions before any future
execution. Compilation alone does not authorize or verify a command.

These are explicit adapters for existing execution protocols, not a universal
script scanner. A hash detects change; it does not prove script trust or safety.

## Bound deploy execution protocol

`inspectDeployBinding({root,binding})` produces a private in-memory context for
the registered root `agent-1c.json`: source/report paths, profile digest, exact
build and concrete target identity. Direct file and server targets in test/development
are supported. Production/env-only identities are rejected. A server requires an
explicit host/port and reference; normalized host case, default cluster port and
reference case form the resource identity without DNS or network calls. No database
or credential file is opened. Target aliases and overlapping source/report/base
paths are rejected so two aliases cannot silently obtain different resource locks.
The returned `targetPath` or `targetServer`/`targetRef` are private execution
context, not UI/report content. Server context has `targetPath:null` and requires
the expanded WorkflowTargetKind/Server/Ref runner protocol.

`compileRunnerCommand({...options,operation:'deploy-apply',deployContext})` binds
`runId`, `stepId`, `sourceDigest`, `targetDigest`, `profileDigest`, `exactBuild`,
`targetPath` through fixed `-Workflow*` parameters. The canonical runner creates
an exclusive fresh `resultDir/workflow-{runId}/{stepId}/result.json` directory.
Before touching the target it checks profile SHA-256, the selected platform
directory and binary version, and the resolved target path or normalized cluster
endpoint/reference. Every platform companion selected through Get-PlatformBinTool
(including ibcmd/ibsrv) has its own exact binary version checked in workflow mode,
so a mixed installation cannot inherit the client executable's version. The protocol adds
`workflow` to the normal report: schemaVersion, identities and monotonic
`mutationState` (`not-applied`, `unknown`, `applied`). Unknown is set before any
target/service mutation; applied is set only after all apply commands finish.
Interrupted/failed cleanup is not treated as a rollback.

`validateDeployReport(report,expected)` requires matching run, step, project,
source, target and profile, plus fresh start/finish timestamps supplied by the
native host. It normalizes assertions without exposing runner messages or
artifacts. Exit zero alone never passes: a single terminal `deploy.apply=ok`,
`mutationState=applied` and absence of error/dry-run steps are required. The host
must also validate actual process termination/exit and freshness of the exclusive
report file. A bound failed probe after apply preserves applied state and fails
the verdict; missing/invalid evidence must remain unknown. This is technical
deploy evidence, not functional acceptance or proof of backup/restore.

Bound preview uses `operation:'deploy-preview'` with the same `deployContext`,
without `-Apply`. Its validator must receive `expected.operation='deploy-preview'`:
only `apply:false`, terminal `deploy.apply=dry-run` and `mutationState=not-applied`
can pass. Preview evidence cannot be reused as application evidence. Legacy CLI
preview without a workflow context remains available, but does not produce a
bound proof for host execution.
