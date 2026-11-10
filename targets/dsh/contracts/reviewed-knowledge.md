# DSH reviewed knowledge adapter

The portable memory/skill ownership method is implemented separately from the
optional DSH adapter. The rulepack does not register tools or create a knowledge
directory. Original session events and backend records remain data; a model-
supplied object claiming `approved` is not trusted authority.

The native adapter can carry proposal objects in the existing session journal.
It must resolve the stored proposal by ID, derive lead-writer identity and
project scope from the executing agent, bind actions to its current revision,
and use native write approval. Review checks evidence, applicability and
non-sensitive content; approval covers exactly that content hash. Delegated
agents can return drafts, while durable writes retain the orchestrator owner.

The lifecycle is draft, review, approved; stale/superseded are retained historical
states. Only an unexpired approved revision can yield a publication plan. Select
the effective project's configured Memoria/Cognee write owner or explicit reviewed
target set for a finding, or a reviewed airules patch for a transferable
rule/procedure. The publisher follows the same routing policy as the memory tool;
it must not bypass Memoria-only selection by sending to a previously configured
Cognee connection. No automatic mirroring or backend retry.

Before dispatch the adapter must atomically claim an operation in the existing
native journal as outcome-unknown. The operation identity binds proposal revision,
destination, project and content hash independently of a retry timestamp. After
native permission/expiry recheck, use the selected scoped backend only. An
uncertain send stays unresolved until evidence from that destination reconciles
it. For multiple explicit destinations retain separate target intents/receipts
under the same logical content operation; partial success is not atomic success,
and an unknown first send leaves later destinations not-attempted. Accepted
content is not proof of searchable processing.

An airules patch binds a relative canonical source path and expected target byte
revision. Use native filesystem/CAS rights and root/symlink containment. Creating
a review artifact is not applying, activating, committing or publishing rules.
Installed/generated copies are not the maintained owner.

History recall uses native read-only current-session events, bounded pages and
stable IDs, excluding private reasoning, injected summaries, recursive recall and
foreign/inherited scope. A returned fragment and an empty truncated search have
different evidential value. No model-controlled root or session authority.

Skill comparisons use three isolated arms: current, previous, no skill. Fresh
sessions/workspaces and explicit sandbox/environment/model/tool budgets prevent
cross-arm contamination. Deterministic fixture checks remain distinct from paid
model acceptance. Read the installed tool descriptor; the portable skill does
not guess DSH operation names or silently start a provider request.
