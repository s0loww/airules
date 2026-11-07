# Shared-core merge from the Codex port

Date: 2026-11-07. The separate Codex port is an input to this selective
merge; it is not a second maintained source of shared policy. Its imported
baseline is airules 0.12.0 / `05181aa`, recorded in its `UPSTREAM.json`.
Canonical shared content remains in this repository's `core/` and overlays.

## Placement decisions

These changes pass the distribution's input filter: they apply to any stack
and project, and change delegation/reporting decisions independent of a
particular client. They belong in core. Concrete role formats, model-field
precedence, discovery paths, hook payloads and cache settings belong in the
runtime target. No project endpoints, paths, credentials or service state
are imported.

| Owner | Imported or reconciled behavior |
|---|---|
| `orchestrator-economy` | Executor selection follows the target contract. Cache lifetime and price are not universal properties of a resident. Previously established user authorization continues only within its recorded scope. |
| `session-handoff` | A new user-owned linked session needs user authorization. Cross-session messaging needs its existing explicit authorization and a supported mechanism; result return or a file handoff remains the fallback. |
| `session-map` | Read-only workers return bounded evidence; the lead persists it. A report path does not grant a worker write permission. |
| `subagent-pipeline` | Fresh-worker guidance preserves context/cost reasoning without assuming another target's cache lifetime. |
| `subagent-task-templates` | Detailed file reports apply to writing roles; read-only evidence goes to the lead. |
| `subagents-model-routing` | Effort resolution and effective override depend on the target. Read-only role labels do not establish sandbox isolation. Delegation depends on applicable authorization. Calibration samples are not universal bounds. |
| `agents/ROLES.md` and agent template | The registry remains one table. Targets resolve model/effort and native format and describe technical rights enforcement; reporting does not grant read-only roles writes. |
| Four role bodies | Skill paths come from the active catalog/contract; performance analysis keeps a read-only scope without promising unavailable tool restrictions. |
| Root contract template | Skill discovery and behavior-block rendering are runtime-aware; delegation/linked-session authorization and read-only reporting are consistent with the method. Existing template placeholders and project-owned `.airules` bindings are preserved. |

## Retained newer canonical work

The donor's older handoff-receiving section was not copied: a requested
continuation does not need another approval merely because context moved.
Explicit user decisions available in the conversation or trusted runtime
continue to apply; a handoff note alone grants no new authority. Working-tree
divergence is compared and resolved before dependent work, never reset to
recreate the note's snapshot. Independent authorized work may continue.

No OpenSpec, hidden-desktop testing, testing/deployment runner, skill bundle
or overlay content was replaced by this core merge. Existing target-specific
content and uncommitted work outside this scope were left in place.

## Validation boundary

The merge is generic policy text. Renderer, layer, composition and fixture
checks validate its mechanical integration separately. It does not certify
a live model selection, inherited sandbox permissions, hook trust, MCP
connectivity, or 1C execution. Those claims require evidence from the selected
runtime and project.
