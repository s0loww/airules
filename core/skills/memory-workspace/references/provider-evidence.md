# Reconcile memory evidence

Use this reference for an uncertain write, asynchronous processing, multiple
providers or a graph whose meaning is unclear. Backend tool names and payloads
must come from their current registered schema.

| Observation | Safe interpretation and next action |
|---|---|
| Search hit | Prior observation; open its record/source and check applicability before relying on it. Preserve project and record identity. |
| Upload accepted with task/receipt ID | Content was accepted; poll the supported status operation. Do not announce successful indexing yet. |
| Timeout after submitting content | Outcome is unknown. Reconcile using the receipt, exact source identity or supported idempotency mechanism. Do not submit the same fact to another provider as a retry. |
| Existing related fact | Compare evidence, scope and revision. Use a supported update or typed lineage operation when authorized; similarity alone does not prove duplication or contradiction. |
| No result | No hit within this query/scope/index state. Check pending processing and coverage before claiming that the knowledge does not exist. |
| Bounded graph | Only the returned snapshot is visible; record limits and truncation. An extracted semantic relationship is not proof of a code call or dependency. |
| Remote unavailable, local file updated | Local preservation succeeded; remote preservation did not become confirmed. Keep this distinction in the receipt/report. |

Cognee-style datasets/documents and processing jobs commonly separate content
ingestion from graph/index creation. Discover the selected server's actual
supported states and dataset-scoped API; a client-calculated dataset identifier
does not establish server authorization.

Memora-style records may expose typed links, updates and source lineage. Read the
actual relation type and referenced records rather than treating every edge as
an inferred fact. A digest summarizes selected records; it is not a new source of
truth and does not prove exhaustive recall.

Keep model extraction, retrieval and tool availability distinct. Do not infer
that a local deployment is using local LLM/embedding models. Follow the configured
data destination and current task authorization for content processing; this
skill does not select accounts, import keys or initiate a migration.
