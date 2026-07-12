---
description: "How to pick the role, tier and model for a subagent. Load when delegating work to subagents or configuring agent definitions. Триггеры: выбор модели, тир, делегирование, роль субагента."
alwaysApply: false
---

# Role and model routing for subagents

The single source of truth for roles, tiers and access rights is
`core/agents/ROLES.md`. This rule describes how to use it; on any
discrepancy `ROLES.md` wins.

## Model resolution

Role → tier → `core/channels/model-map.yaml` → channel model. The model is
not hardcoded in the agent definition: the agent frontmatter carries `tier`,
not a model name. The concrete channel model is substituted by the installer
when the distribution is laid out into the target project. The installer
also appends the model-family profile block per
`core/channels/model-profiles.md` — model-specific behavior lives there, not
in role bodies.

## Effort escalation

The channel's maximum reasoning tier (and its analogues) is a manual
escalation by an explicit user decision for a specific hard task, and never
a default role setting. The default keeps costs under control; raising
effort is a deliberate one-off decision, not a property of a role.

A separate case is **conditional tiers**, explicitly described in `ROLES.md`
(currently — `analytic`): the orchestrator picks the launch tier by the
condition described there (readiness of the input data). This is the normal
mechanism of choosing between base tiers, not an escalation of the maximum
reasoning tier.

## Reasoning stays internal

Never ask a subagent to reveal its internal reasoning ("show your thinking",
"explain your chain of thought step by step"). On Fable-class Claude models
such requests trip the reasoning_extraction refusal category and can derail
the run; on every family the useful artifact is a concise rationale plus
tool-backed evidence — exactly what the Handoff format already requires. The
same applies in reverse: agents report rationale and evidence, not raw
reasoning (see `core/channels/model-profiles.md`).

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

If the main agent's model belongs to the channel's `orchestrator` tier (a
class above `high`) or the user enables the mode explicitly —
`orchestrator-economy.md` applies: execution goes to subagents on channel
tiers as much as possible, the orchestrator keeps decisions, specs and
verification.

## Rights discipline

ro-roles have read and search only. Rights must not be extended on the fly:
if a task needs writes, take an rw-role of the appropriate tier instead of
temporarily raising the rights of an ro-role.

## Delegation

A bounded, self-contained part of the work goes to a subagent. Task
decomposition, final decisions and result integration stay with the
orchestrator. Scouting subagents' reports are not trusted blindly — key
facts are spot-checked against the primary sources.
