# DSH adapter for specialized 1C operations

This target contract describes the independently registered
`airules_onec_specialized` tool. The portable skill instructions do not assume
it exists. Discover its current schema and status before choosing a call;
installed Markdown or a project binding alone does not register an executor.

The tool declares domains `repository`, `ai-merge`, `v8unpack` and actions
`status`, `history`, `diff`, `plan`, `run`, `result`, `cancel`. Operation support
comes from the returned capability and configured runner, not this list of
action names. Element/XBSL work remains text/project-tool routing; this plugin
does not supply an Element compiler or deployment service.

## Bindings and effects

Project bindings live in `.dsh/onec-specialized.json`, schema version 1.
Repository report references, local merge inputs and binary input/output paths
are project-relative. They do not contain an MCP endpoint or credentials.

| Binding | Meaning |
|---|---|
| repository reports | Saved status/history/diff report references; reading them is not a live repository query |
| repository runner | Versioned Node or PowerShell runner with source hash and declared operation/write-operation lists |
| runner driverConfigPath | Optional Node bridge binding to `.dsh/onec-specialized-driver.json`; the bridge and its declared script/interpreter/dependency evidence must match the saved plan |
| repository allowForce | Separate project permission for exceptional force/discard; never set automatically to make a call pass |
| aiMerge baseline/current/vendor | Three source inputs for local artifact/hash comparison and a proposal |
| v8unpack input/output | Binary source and new output workspace for the configured supported runner |

The runner must also be trusted on the machine. UI configuration, a matching
file hash or a session access mode alone does not grant execution. Existing
native permissions, approval and subprocess sandbox policy remain authoritative.
No MCP facade is required; this adapter does not create one.

The optional driver configuration adapts an already installed repository script
or binary codec to the versioned runner protocol. It is not an alternate command
line or an authorization bypass. Project-relative script/dependency hashes and
the explicitly configured interpreter are checked; changed dependencies stale
the plan. Execution still depends on the host's actual confinement capability.
An unavailable native sandbox is a capability failure, not permission to launch
an unconfined fallback or automatically raise the session's access mode.

The control/status and saved-report actions are not live repository queries.
For a live status query, a configured trusted runner must declare the repository
`status` operation; build its operation plan and execute that saved plan through
`run`. Report the distinction even when a saved report can be read successfully.

## Plans and execution

`plan` records the requested domain/operation and source/target identities.
Repository lock/update/commit/unlock require an explicit object list. Commit
requires a meaningful comment. Force requires the project allow flag plus
per-call `confirmForce`; forced unlock additionally distinguishes discard with
`confirmDiscardChanges`. Concrete parameter support is checked against the
current registered schema.

`run` consumes a saved `planDigest` and a `requestId`. It does not accept an
ad-hoc command line as a substitute for the reviewed plan. The configured
runner protocol reports the actual outcome and affected identities. Use
`result` and supported reconciliation for partial/unknown outcomes; do not
retry a publication or reconstruct success from one process exit code.
Cancellation does not itself prove that a shared target was restored.
The result must match the invocation's run ID, plan digest and request digest;
an exit code without that bound result is not a successful operation.

Local AI merge comparison produces artifact/hash differences and an extension
proposal from bounded local file groups and three-way hashes. Its support state
remains `not-inspected`: the adapter does not supply the donor's metadata/support
parser. It does not parse every opaque binary format, perform MergeCfg,
apply a CFE or prove compatibility of a live configuration. Binary extraction
or a local runner success likewise does not establish platform acceptance.
Only separately authorized and actually executed checks support those claims.
Ordinary-form MCP codecs, when available, are discovered separately; registering
this adapter does not register those codecs or install v8unpack.

Fixture runners exercise the protocol in disposable workspaces. Their reports
are evidence about the adapter, not evidence of a working repository connection,
loadable CF or live ИБ behavior.
