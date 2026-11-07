# Wave 2: 1C capability workflows and Telegram

The donor bundle was inspected for task coverage. These are original, compact
adaptations to the current orchestration and ownership model, not copies of its
tool implementations. Donor distribution rights are not inferred from access to
the installed bundle. No new licence claim is made for donor assets.

## Portable 1C procedures

All thirteen skills live under `overlays/1c/skills`. Their descriptions select
the procedure; their bodies do not bind a host, fixed MCP prefix, endpoint or
installation layout.

| Skill | Procedure and owner boundary |
|---|---|
| `1c-impact` | Bound callers/dependencies and verification impact to selected source and target; no mutation or automatic deployment. |
| `1c-mechanism-map` | Trace entry points, handlers, branches and writes; distinguish source edges from observed runtime order. |
| `1c-code-search` | Use a scoped index or local source search; confirm returned fragments against current source. |
| `1c-meta-info` | Read a metadata passport; reuse `1c-metadata-manage` read-only tooling rather than creating another metadata editor. |
| `1c-form-inspect` | Inspect form XML/module bindings through existing metadata tooling; visual evidence remains a separate operation. |
| `1c-platform-help` | Resolve version/context-sensitive platform and БСП documentation without pretending a signature lookup executes BSL. |
| `1c-templates-memory` | Find a suitable template or established project example; existing memory and skill maintenance retain ownership. |
| `1c-qa-testing` | Build observe–act–assert steps with explicit executed/skipped/unknown results; project QA is independently optional. |
| `1c-form-shot` | Obtain an actual form image through an available project-supported capture path; distinguish live and rendered evidence. |
| `1c-event-journal` | Read bounded ЖР evidence through a real capability or supported export; ТЖ remains owned by `1c-tj-analysis`. |
| `1c-debug-runtime` | Maintain discriminating hypotheses, proposed probes, source/target-bound observations and cleanup evidence. |
| `mcp-1c-tools` | Discover actual current schemas before selecting tools; a visible definition is not proof of health. |
| `onec-check-mcp` | Diagnose separately definition visibility, transport reachability and scoped readiness; configuration changes retain their existing owner. |

The metadata/form skills are thin read-only task routers. The debug workflow
does not replace the verification matrix, testing rules or project runners.
Temporary investigation records are evidence notes, not a second SDD framework.
No automatic reviewer, donor Gate 4 or parallel ASK/PLAN/BUILD lifecycle is added.

## DSH binding

The private adapter `airules-dsh-onec-capability-workflows` supplies two real
composition tools only to the `1c-airules` preset:

- `airules_capabilities` filters the active agent's native tool schemas and
  returns bounded candidates, actual parameter schemas, truncation information
  and pagination. It never executes a discovered tool. Health remains unprobed.
- `airules_debug_case` provides `list/open/status/evidence/close` for a private,
  project-scoped investigation notebook. It records hypotheses and SHA-256
  hashes of selected source/report artifacts, detects stale artifacts and uses
  revision checks for updates. A caller-reported resolved outcome is explicitly
  uncertified.

The host mount provides the notebook service; the composition mount consumes
native tools, system prompt, preset and sandbox services. These tool names are
DSH adapter bindings, not portable aliases for donor `mcp__onec_*` tools.
No `onec_debug_runtime` backend is claimed. The notebook neither edits BSL nor
inserts probes, reads a running ИБ, deploys, reproduces a failure or removes
instrumentation. Those actions use available existing tools and normal project
permissions. Source and applied-target evidence must still be reconciled.

Facade, direct MCP and local fallback are optional paths. Nested facade
capabilities require their own live discovery; neither a schema match nor a
successful wrong-method HTTP response certifies readiness. There is no assumed
SQL API, fixed Docker layout or dependency on a particular QA server.

`onec-init-project` and `onec-install-mcp` are deliberately not copied. Initial
project setup and connection changes route to the existing project settings and
MCP manager. These task skills diagnose capability gaps without creating a
second installer, wizard or connection registry.

`targets/dsh/skills/telegram` documents the existing bridge controls:
Settings → Telegram and `/telegram status|on|off|connect|disconnect|help`.
The bridge keeps its token in CurrentUser-protected storage; the skill does not
import accounts, expose tokens, enable autostart or send test messages.

## Validation boundary

All fourteen skill files pass `quick_validate.py` and the targeted layer scan.
The private adapter has six passing synthetic tests, including actual native
Cordis/defineTool registration, project/preset/sandbox scoping, schema bounds,
hash freshness, update races and path/link rejection. Tests use temporary
fixtures only. No live 1C MCP, QA, COM, deploy, Telegram delivery or project
runner was invoked, and no project source was modified.
