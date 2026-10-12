# Role registry

Canonical registry of generic subagent roles. The model is not hardcoded in
roles or in agent definitions — a role carries only its `tier` and `effort`,
and the concrete model and effort value are resolved via
`core/install/model-map.yaml` at install time.

`tools` legend: **ro** — read/search (no write access); **rw** — the same
plus file writes and command execution.

| role | tier | effort | tools | override | purpose |
| --- | --- | --- | --- | --- | --- |
| explorer | low | medium | ro | — | Codebase reconnaissance, search, subsystem map — no edits |
| doc-writer | low | medium | rw | — | User/administrative documentation, guides |
| error-fixer | high | medium | rw | fast | Fast targeted error fixing, minimal edits without architectural changes |
| developer | high | medium | rw | — | Code implementation from a ready plan |
| metadata-manager | high | medium | rw | — | Data/schema structure and configuration work |
| refactoring | high | medium | rw | — | Refactoring, dead code removal, consolidation |
| tester | high | medium | rw | — | Testing, behavior verification, deployment to the test environment |
| analytic | medium* | high | rw | — | Analysis, requirements, specifications (no code writing); conditional tier — see "Conditional tiers" |
| planner | high | medium | rw | — | Task decomposition, implementation plan, risks, dependencies |
| architect | high | high | rw | — | Change architecture, component design, assembly plan |
| arch-reviewer | high | medium | ro | — | Architecture decision review |
| code-reviewer | high | medium | ro | — | Code review — only on an explicit user request |
| performance-optimizer | high | high | ro | — | Bottleneck hunting, performance analysis; hands edits to developer |

## Effort semantics

`tier` picks *which model* the role runs on; `effort` picks *how much
deliberation* it spends there. The two are separate axes — two roles on the
same tier legitimately differ in effort (`architect` at `high` vs
`code-reviewer` at `medium`), so effort cannot be derived from the tier.

Both values in the table are **defaults**. The launch can override them: the
orchestrator passes the model and the effort as launch parameters, and those
win over the agent definition (see "Role classes and launch-time override").

Values are `low | medium | high | xhigh` and are translated by `claude.effort`
in `model-map.yaml`.

Calibrations worth keeping in mind when editing the table:

- **Effort above the default is not free quality.** Measured on a real
  implementation task: the same tier one effort step up cost about 70% more
  time and output for the same coverage. Where an executing oracle exists
  (tests, a gate), the executor default is `medium`; raise it for a specific
  run, not in the table.
- **Roles without an oracle get the higher default.** `architect` works where
  the first attempt decides and nothing executes the result; `planner` sits at
  `medium` and is raised to `high` per launch when the plan is the hard part.

- **Main-flow roles sit on the high tier at `medium` effort.** That is the
  default executor of orchestration mode (`orchestration.executor` in the
  model map): it writes fast and correctly, and the links of the application
  area come to it in the impact map. With the mode off, wide, dense,
  cross-cutting implementation still stays with the orchestrator —
  delegating it costs more than doing it (`subagents-model-routing.md`,
  "Delegation").
- **Script and tooling work is not a role but a kind of work** with a fixed
  medium tier: the orchestrator launches the implementing role for it with
  that tier as a launch parameter, whatever the session command names.
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
`analytic-deep` (high tier, xhigh effort). The registry keeps a single row;
the `*` marks the conditional pair, and both definitions appear in the root
contract's Subagents table. The pair predates the launch-time override and is
kept because it makes the choice visible in the Subagents table; a new
conditional case should use the override instead of a second definition.

## Role classes and launch-time override

The registry values are defaults; what a launch actually runs on is decided
in this order, first match wins:

1. **An explicit instruction for the task** ("run this one at `xhigh`") —
   always wins. Effort is the user's lever: some tasks need a step the
   registry would never give by default.
2. **The session command** of orchestration mode
   (`orchestrator-economy.md`), for main-flow roles only.
3. **The registry default** rendered into the agent definition.

| class | roles | where model and effort come from |
| --- | --- | --- |
| main flow | developer, metadata-manager, refactoring, error-fixer, tester | session command, else the registry |
| fixed by kind of work | explorer (reconnaissance), doc-writer, and script/tooling work whoever does it | registry and the `orchestration` block of the model map; the session command does not touch them |
| deciding | architect, planner, analytic, arch-reviewer, code-reviewer, performance-optimizer | registry; changed only by an explicit instruction for the task |

Mechanics: the model and the effort are per-launch parameters of the agent
tool and they override the definition's frontmatter. A **continued** agent
keeps what it was launched with — to change either, launch a new one. The
tool sets effort only when the user or the rules ask for it explicitly, so a
rule that wants a specific effort must name it, not hint at it.

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
