---
description: "How to pick the role, tier and model for a subagent. Load when delegating work to subagents or configuring agent definitions. Триггеры: выбор модели, тир, делегирование, роль субагента."
alwaysApply: false
---

# Role and model routing for subagents

The single source of truth for roles, tiers and access rights is the
distribution's role registry, rendered at install time into the channel
agent definitions and the root contract's Subagents table. This rule
describes how to use it; on any discrepancy the rendered registry (agent
definition + Subagents table) wins.

## Model resolution

Role → tier → the channel model map (an install-time artifact of the
distribution) → channel model. The model is not hardcoded in the role: the
role carries `tier`, not a model name. The concrete channel model is
substituted by the installer when the distribution is laid out into the
target project. The installer also appends the model-family profile block —
model-specific behavior lives there, not in role bodies.

## Effort

Effort is a **property of the role**, resolved the same way as the model:
role `effort` → `channels.<channel>.effort` → channel value (`ROLES.md`,
"Effort semantics"). It is a separate axis from the tier — same model, more
or less deliberation — so two roles on one tier legitimately differ.

Two things stay outside the registry:

- **The channel's top step** (above `xhigh`, where a channel has one) is a
  manual escalation by an explicit user decision for one hard task. It is
  never a role default: on that step the result is *worse* than on `xhigh`
  at a higher price, so it buys nothing by itself.
- **Conditional tiers**, explicitly described in `ROLES.md` (currently —
  `analytic`): the orchestrator picks the launch tier and effort by the
  condition described there (readiness of the input data). This is the normal
  mechanism of choosing between base tiers, not an escalation.

Sweep effort on your own tasks when adopting a new model family — carried-over
defaults are the usual reason a routing table underperforms. Sweep for
latency and interactivity; where the session runs on a subscription rather
than metered tokens, effort is not a cost lever.

## Reasoning stays internal

Never ask a subagent to reveal its internal reasoning ("show your thinking",
"explain your chain of thought step by step"). On some Claude families such
requests trip the reasoning_extraction refusal category and can derail the
run; on every family the useful artifact is a concise rationale plus
tool-backed evidence — exactly what the Handoff format already requires. The
same applies in reverse: agents report rationale and evidence, not raw
reasoning (the model-profile block of the agent definition).

## The script rule

Writing and changing scripts is a task for medium/high-tier roles; executing
an already written and verified script and collecting logs is a task for a
low-tier executor.

Reason: an executor on a light model, when hitting an error, tends to "fix"
input files and invent failure causes instead of reporting the error as a
fact. So the executor gets copies of the input files, and its report is
checked against the real logs rather than trusted as a retelling.

One-shot runs are the exception: launching a ready contract script or a
test suite that writes a machine-readable report costs the orchestrator
only the compact verdict — running it directly (in the background) is
cheaper than a subagent launch (see the payback rule of thumb in
`orchestrator-economy.md`). What gets delegated is the iteration: a failed
run hands the *report path* (not the pasted log) to the fixing role, which
owns the run-read-fix loop in its own context.

## Orchestrator economy mode

If the main agent's model belongs to the channel's `orchestrator` tier **and
that tier is a class above `high`**, or the user enables the mode explicitly
— `orchestrator-economy.md` applies: execution goes to subagents on channel
tiers as much as possible, the orchestrator keeps decisions, specs and
verification.

Where a channel maps `orchestrator` onto the same model as `high` (the lead
agent *is* the heavy implementer), the automatic trigger does not fire and
the mode stays manual — the delegation rules below are the operating default
instead.

## Rights discipline

ro-roles have read and search only. Rights must not be extended on the fly:
if a task needs writes, take an rw-role of the appropriate tier instead of
temporarily raising the rights of an ro-role.

## Delegation

Delegate only large, genuinely independent, parallelizable work — a wide
multi-file survey, a stream with its own write zone. Everything else the
orchestrator does itself.

- Do not delegate what you would finish in a few tool calls: the launch
  overhead exceeds the work (payback rule — `orchestrator-economy.md`).
- Do not use subagents to check or re-check your own work.
- One subagent closes the task — launch one, not several. Keep the launch
  count low; a fan-out of workers is a deliberate decision, not a reflex.
- Heavy multi-file implementation is **not** a delegation case by default:
  it is dense, cross-linked, and cheaper done directly than specified,
  handed over and reconciled.

Task decomposition, final decisions and result integration stay with the
orchestrator. Scouting subagents' reports are not trusted blindly — key
facts are spot-checked against the primary sources.

**Why search still goes to a low tier.** Not for the token price: it keeps
the orchestrator's context clean. Directory walks, grep output and dead-end
reads do not belong in the lead session — they push out what the orchestrator
actually reasons over. This is the one case where a cheap launch pays for
itself regardless of the volume of work.
