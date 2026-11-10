# Preserve relationships to original evidence

When a continuation depends on why code implements a decision or what verifies
it, retain a small typed reference: code path and optional range, relation
(`references`, `implements`, `verifiedBy`, `related`), original note/document/
source ID, its namespace or owner, and provenance. Use stable source identities
returned by the owner; do not invent backend records or copy their bodies into
a parallel memory or graph.

Bind code evidence to the revision or exact-byte content fingerprint reviewed.
At continuation, recheck the live file. A changed fingerprint makes the claim
stale until reviewed again; missing/inaccessible and unverified due to a budget
remain explicit states. An unchanged fingerprint proves byte identity, not that
the linked claim is true or that a test covered the current environment. A line
range helps navigation but a line number alone is not an evidence version.

If the host exposes a project-scoped reference ledger, inspect its actual
schema and list current metadata before a change. Use its current revision and
native write approval; delegated readers may propose references while the lead
owns durable updates. Never accept a model-supplied foreign root as authority.
Removal deletes only the relation unless a separate authorized action explicitly
changes the owning source. Do not follow arbitrary URLs or fetch backend content
merely because a reference exists. Keep query counts, source reads and pages
bounded and preserve truncation/verification limitations in the handoff.

Without that capability, include the same minimal references and fingerprints
in the existing handoff or decision artifact. Do not create another index simply
to satisfy this procedure. Credentials, copied documents, transcripts and private
reasoning do not belong in reference metadata.
