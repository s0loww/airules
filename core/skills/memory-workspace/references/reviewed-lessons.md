# Review a reusable finding

Use when a task produces a finding worth preserving, or when an existing finding
may have become outdated. A long chat, a successful tool call or an extracted
graph edge alone does not establish reusable knowledge.

Keep a candidate as a draft in the existing task/session artifact. Capture its
statement, evidence references, observation date and applicability: project,
object/tool version and the condition under which it is true. A delegated agent
can return this candidate; the established orchestrator/writer reviews it.

Review the actual source/test evidence, applicability and non-sensitive content.
Tie the decision to the reviewed text revision. Editing the statement or scope
requires another review. Mark unverified workarounds as limitations; do not turn
them into approved procedures. An explicit expiry or changed source/version can
make an earlier conclusion stale even when its write receipt remains valid.

Choose the destination or explicit reviewed target set through the project's existing ownership:

| Finding | Owner and outcome |
|---|---|
| Verified project fact or limitation | The configured memory backend; retain its source/record receipt. |
| Stable project decision | The project's decision-log owner; memory can link to it. |
| Transferable procedure | Existing or narrowly extended skill through `skill-maintainer`; review the patch. |
| Standing behavior or permission | Its rule owner; a memory note cannot change instructions. |

Search for an existing item before writing. Retain its identity when updating it;
for supersession preserve the old ID, replacement ID and reason rather than
silently erasing contrary evidence. A stale or superseded finding remains
historical evidence and must not be presented as current approved guidance.

Publish only the reviewed revision to the selected owner or target set. When the
project explicitly chooses multiple memory targets, retain an independent receipt
for each; apply the partial/unknown rules in [routing-and-models.md](routing-and-models.md).
A draft, approved
proposal, accepted upload, pending index, created review patch and activated rule
are different outcomes. Reconcile uncertain sends against the same backend;
changing the proposal timestamp or choosing a second backend does not resolve an
unknown first write. Do not introduce another knowledge directory just to track
this lifecycle; use the existing task artifact and owner receipts.
