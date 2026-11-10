# DSH adapter for project memory

The portable `memory-workspace` skill uses available capabilities. The DSH target
can expose an `airules_memory` tool through its separately installed integration;
the rulepack and this document do not register that tool by themselves.

Read the current tool schema and status before a call. Determine the selected
native project session, effective backend and dataset/filter before searching or
writing. Tool action names and payload fields belong to the installed adapter.
Do not guess them from Cognee examples or assume direct Memora MCP calls use the
same contract. Native permissions, project configuration and tool ownership remain
authoritative. In the current adapter, call `airules_memory` with `action:status`
before its first dependent operation and use the actual descriptor to confirm
the supported actions below.

| Action | Current adapter meaning |
|---|---|
| status | Effective availability, configuration and processing capability |
| documents | Documents in this project's derived dataset |
| recall | Bounded CHUNKS retrieval using `query` and optional `topK` |
| remember | Upload `text` with optional `title`; returns a receipt, not completed indexing |
| process | Separate extraction/indexing request, with `confirm:true` and configured local processing capability |
| task | Inspect the returned `taskId`; reconcile pending or uncertain outcomes |
| graph | Bounded server graph for this project |

The tool derives session, root and dataset from the native executing agent; do
not supply or invent model-controlled scope fields. Native write approval is
required for mutations. `confirm:true` conveys the requested action, not a bypass
of that approval or proof of a local model. The backend is disabled by default;
enabling a connection is recipient/machine configuration, not a skill side effect.

The settings page submits write/processing requests into the selected native chat
so approval is audited inside a real turn. `submitted:true` means only that the
request was queued; it does not prove an upload or processing started. Such a
request can invoke the selected chat model. The queued `expectedRevision` binds
the adapter configuration; a changed connection requires renewed review rather
than silently using a different backend. Credentials remain in a private machine
file and are not returned by the settings API or supplied as tool arguments.

Search/read and graph results retain source IDs, project/dataset scope, bounds and
processing state. A write receipt or pending job remains unresolved until the
adapter returns completion evidence. If an adapter offers local fallback, report
that storage location separately. Opening settings is not authorization to ingest
project files, start processing or copy existing memory between backends.

Bindings, network addresses, model choices, credentials and existing memory stay
in recipient/project configuration. No Cognee server, MCP facade, routing
precedence or migration is required by the portable skill. Read/write capabilities
and their delegation follow the current orchestration contract.
