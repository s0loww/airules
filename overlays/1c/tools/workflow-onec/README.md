# 1C workflow metadata gate

Offline domain adapter `onec.profile` 0.1.0 for the universal workflow core.
Node 20+, builtins and the sibling universal core contracts module only.
Run tests with `node --test test/*.test.mjs`.

`validateOnecProfile(profile, { sourceKind, extensionName, exactBuild })` validates
the deployment-relevant subset of an existing agent-1c profile and returns only
normalized assertions/capability statuses. It does not validate every field of
the full agent-1c schema. Inline credentials are rejected; credential references
are not resolved. Metadata validation opens no filesystem, environment, XML,
network, process, COM or database. Adapter `fingerprint()` reads only its own
module bytes and hashes them with its canonical descriptor; it rereads those
bytes on each call to detect adapter changes after planning.

Source kind/name and exact build are explicit facts supplied by the caller.
The gate checks their consistency; it does not discover XML identity or verify
the installed executable/actual target. A broad versionPrefix requires a separately
pinned full build. Cluster targets reject ibcmd. Production metadata is accepted
for planning and marked productionAuthorizationRequired; no execution is enabled.

Unit/probe/Vanessa are `declared` only when corresponding profile fields exist;
this does not prove tool availability or successful tests. The existing generic
Vanessa implementation is file-only, so its server capability is `unsupported`.
An absent Vanessa section stays `not-configured` despite runner defaults.

`createOnecProfileAdapter()` exposes operation `validate-profile` using the core
`assertions` validator. It is an offline gate, not a deploy adapter. Existing
project runners and their lifecycle/backup/authorization requirements remain
unchanged. No MCP connection, facade, local platform or database is required.
