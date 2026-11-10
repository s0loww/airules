# DSH evidence reference ledger

The portable handoff evidence method requires no runtime or backend. When the
optional native `airules_links` adapter is installed, it uses `list`, `query`,
`add` and `remove` for a bounded project ledger at `.dsh/evidence-links.json`.
It complements native codegraph and Cognee rather than extracting another graph.

Derive project identity and filesystem services from the current registered
agent and sandbox root; never from tool arguments. Readers include read-only
sessions and subagents. Writes require a native execution context, lead writer,
explicit approval over exact reference metadata, current byte revision and native
filesystem CAS. Reject foreign project ledgers, root changes, symlinks, traversal,
protected credential paths and body/credential fields. Recheck source hashes
after approval before writing; removal affects local relation metadata only.

Use stable typed node IDs and directed link IDs for `references`, `implements`,
`verifiedBy` and `related`. The source is a relative code file with optional
range. Targets carry a file or original note namespace/backend/record ID,
document ID or source ID. Retain per-relation source hashes and provenance/time;
never silently refresh old evidence by updating a shared node. Freshness is
`fresh`, `stale`, `missing-or-inaccessible`, or `unverified-budget`; external
references remain `not-fetched` until their owner verifies them.

Bound storage, pages and source reads; bind pagination cursors to filters and
the current revision. Read operations must not write the ledger. The adapter
does not follow URLs, execute commands, copy source bodies, read arbitrary
backends, or establish that a referenced record exists. A hash match does not
prove a test outcome or applicability. Preserve these limitations in reports.
