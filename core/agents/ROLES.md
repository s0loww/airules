# Role registry

Canonical registry of generic subagent roles. The model is not hardcoded in
roles or in agent definitions — a role carries only its `tier` and `effort`,
and the concrete model and effort value are resolved via
`core/install/model-map.yaml` at install time.

`tools` legend: **ro** — read/search (no write access); **rw** — the same
plus file writes and command execution.

| role | tier | effort | tools | override | purpose |
| --- | --- | --- | --- | --- | --- |
| explorer | low | low | ro | — | Codebase reconnaissance, search, subsystem map — no edits |
| doc-writer | low | medium | rw | — | User/administrative documentation, guides |
| error-fixer | medium | medium | rw | fast | Fast targeted error fixing, minimal edits without architectural changes |
| developer | medium | medium | rw | — | Code implementation from a ready plan |
| metadata-manager | medium | medium | rw | — | Data/schema structure and configuration work |
| refactoring | medium | medium | rw | — | Refactoring, dead code removal, consolidation |
| tester | medium | medium | rw | — | Testing, behavior verification, deployment to the test environment |
| analytic | medium* | high | rw | — | Analysis, requirements, specifications (no code writing); conditional tier — see "Conditional tiers" |
| planner | high | xhigh | rw | — | Task decomposition, implementation plan, risks, dependencies |
| architect | high | xhigh | rw | — | Change architecture, component design, assembly plan |
| arch-reviewer | high | medium | ro | — | Architecture decision review |
| code-reviewer | high | medium | ro | — | Code review — only on an explicit user request |
| performance-optimizer | high | high | ro | — | Bottleneck hunting, performance analysis; hands edits to developer |

## Effort semantics

`tier` picks *which model* the role runs on; `effort` picks *how much
deliberation* it spends there. The two are separate axes — two roles on the
same tier legitimately differ in effort (`planner` at `xhigh` vs
`code-reviewer` at `medium`), so effort cannot be derived from the tier.

Values are `low | medium | high | xhigh` and are translated by `claude.effort`
in `model-map.yaml`.

Two calibrations worth keeping in mind when editing the table:

- **Heavy multi-file implementation has no role.** `developer` is a
  medium-tier executor for bounded work from a ready plan. Wide, dense,
  cross-cutting implementation stays with the orchestrator — delegating it
  costs more than doing it (`subagents-model-routing.md`, "Delegation").
- **Reviewers sit at `medium` on purpose.** Review precision holds up at low
  effort, which buys a two-speed scheme: a fast pass at commit time, and a
  deliberate `xhigh` pass before a release gate — the latter as a manual
  escalation on a specific run, never as the role's default.

The top effort step (above `xhigh`) is not part of the scale and is never
written into the registry: it is a manual escalation by an
explicit user decision for one hard task.

Role bodies — `core/agents/roles/<role>.md`; agent definitions are generated
by the installer (see `core/install/layout.md`).

## Override semantics

`override` is an optional per-role tier on top of the base one. Currently
one is defined: `fast` — a cheap fast executor for mechanical fixes. If a
the map defines the `fast` tier in `model-map.yaml`, a role with this
override gets it; if `fast` is not defined, the role runs on
its base tier from the table above. This lets a single registry cover both
an extended model set and a minimal one.

## Conditional tiers

For the `analytic` role, the tier depends on input data readiness:

- **medium** tier, `high` effort — the data is prepared in advance;
- **high** tier, `xhigh` effort — the analyst works from raw sources without
  prior preparation (the run is then spec authoring, not summarizing).

The orchestrator decides at launch time **by picking the definition**: the
installer renders a conditional-tier role as a *pair* of agent definitions
from the same role body — `analytic` (base: medium tier, high effort) and
`analytic-deep` (high tier, xhigh effort). No per-run
override mechanics — the upgrade is launching the other definition. The
registry keeps a single row; the `*` marks the conditional pair, and both
definitions appear in the root contract's Subagents table.

## Principles

- Routing is built on the role+tier+effort triple, not on a concrete model
  name.
- Final decisions and result integration are the responsibility of the main
  agent (the orchestrator); a subagent's output is working material, not a
  ready decision.
- ro-roles get no write access under any configuration —
  expanding rights means changing the role, not changing settings.
- Specialization for a concrete technology stack is done with overlays
  (`overlays/<stack>/agents/`). An overlay inherits `tier` and `effort` from
  here and cannot set a model on its own.
