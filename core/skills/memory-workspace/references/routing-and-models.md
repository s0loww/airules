# Persistent memory routing and processing models

Use when the recipient enables several memory providers, a project overrides its
default, or the task changes models that extract/index memory. Follow the actual
host schema; the portable method does not require one implementation or server.

## Resolve the project policy

Resolve the recipient default, then the current project's explicit override.
All conversations of that project inherit the result. Derive the project from
the native execution scope and preserve the existing backend namespace mapping;
do not create a new memory just because a different session or model is selected.
Inspect the effective mode and where it came from before dependent operations.
Credentials/endpoints stay in recipient configuration, not portable rules.

Modes can select Cognee, Memoria or both. Treat a selected but unconfigured or
unavailable provider as unavailable; do not remove its project filter or search
globally to produce a nonempty answer. If one of two sources fails, retain the
other source's bounded results with a partial status and the unavailable source
named. A degraded read is not permission to redirect a later write.

For both sources, keep backend, namespace/dataset, record IDs and processing
evidence separate. Raw relevance scores from different retrieval engines are
not directly comparable. Preserve conflicting findings and their dates rather
than silently overwriting one with the other. A graph/document-processing view
can belong to one provider; selecting both does not create a unified graph.

## Explicit write destinations

The read mode does not imply replication. Follow the project's write target or
reviewed target set. A project may, for example, keep operating decisions in
Memoria and source documents/relationships in Cognee. These roles are a recipient
choice, not a mandatory split for all users.

For an explicit write to both destinations, bind the same reviewed content
revision to a logical operation ID and one scoped receipt per backend. Validate
the chosen bindings and authority before dispatch. Retain accepted, unknown,
not-attempted and failed targets separately; do not call the operation atomic.
After an unknown first send, reconcile that target before continuing to another.
A partial success never justifies repeating the successful first write. Changes
to project policy, payload or model-processing profile require renewed review.
Existing memory is not copied, migrated or deleted merely by selecting a mode.

## Choose processing models independently

The conversation model, memory storage and memory-processing models are separate
choices. A local memory server can use a local embedding model and an external
LLM for extracting entities/relationships, or another explicitly supported mix.
An endpoint on loopback does not establish that all inference stays local.

Resolve embeddings and extraction independently from an actual available model
catalogue. A file installed on disk is not proof that a serving runtime can load
it or that it supports the required operation. Retain provider/runtime, model ID,
availability and embedding dimensions when applicable. Distinguish selected
configuration from an applied and tested server profile.

Switching embedding models changes vector identity even when dimensions match;
use the host's explicit reindex/migration path rather than mixing new vectors
into an old index. A successful transport or valid JSON is not evidence of
extraction quality. Test representative language/domain fixtures before relying
on the new processing profile.

External embedding calls can happen during both indexing and search; graph
extraction can invoke an LLM during processing. Keep that routing and potential
provider usage visible. Do not install models, run paid evaluations or ingest
project material just because the user opened the catalogue. Model API secrets
remain with the configured server/provider owner and out of memory content.
