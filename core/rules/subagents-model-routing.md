---
description: "How to pick the role, tier and model for a subagent. Load when delegating work to subagents, deciding whether a piece of work is worth a launch, or configuring agent definitions. Триггеры: выбор модели, тир, делегирование, роль субагента, окупаемость запуска, экономия контекста, разведчик."
alwaysApply: false
kind: process
---

# Role and model routing for subagents

The single source of truth for roles, tiers and access rights is the
distribution's role registry, rendered at install time into the agent
definitions and the root contract's Subagents table. This rule
describes how to use it; on any discrepancy the rendered registry (agent
definition + Subagents table) wins.

## Model resolution

Role → tier → the model map (an install-time artifact of the distribution) →
model. The model is not hardcoded in the role: the role carries `tier`, not a
model name. The concrete model is substituted by the installer when the
distribution is laid out into the target project. The installer also appends the model-family profile block —
model-specific behavior lives there, not in role bodies.

## Effort

Effort is a **default of the role**, resolved the same way as the model:
role `effort` → `claude.effort` in the model map → concrete value
(`ROLES.md`, "Effort semantics"). It is a separate axis from the tier — same model, more
or less deliberation — so two roles on one tier legitimately differ.

The default can be overridden for one launch, and so can the model: both are
launch parameters and win over the agent definition. Who may override what:

1. an explicit instruction for the task — any role, any step of the scale;
2. the session command of orchestration mode — main-flow roles only;
3. otherwise the role default.

Name the effort explicitly when you pass it: the launch tool applies it only
on an explicit request of the user or of a rule, never on its own judgment.
A continued agent keeps the model and effort it was launched with.

Two axes decide what to ask for, and neither is the size of the task:

- **Is there an executing oracle?** With tests or a gate at hand the executor
  runs at `medium` and lets the oracle find the misses. Without one the first
  attempt decides — that is where the higher tier and effort pay.
- **What does one check round cost?** Seconds — write and run. Minutes (a
  deployment, a full regression) — the orchestrator prepares an impact map
  first (`subagent-pipeline.md`, "Impact map") and names the price of a round
  in the task.

Two things stay outside the registry:

- **The top step** (above `xhigh`, where one exists) is a
  manual escalation by an explicit user decision for one hard task. It is
  never a role default: on that step the result is *worse* than on `xhigh`
  at a higher price, so it buys nothing by itself.
- **Conditional tiers** (currently — `analytic`): the installer renders the
  role as a pair of definitions (`analytic` for prepared data,
  `analytic-deep` for raw-source work); the orchestrator picks the launch
  tier by launching the matching definition. This is the normal mechanism of
  choosing between base tiers, not an escalation.

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
cheaper than a subagent launch ("Payback of a launch" below). What gets
delegated is the iteration: a failed
run hands the *report path* (not the pasted log) to the fixing role, which
owns the run-read-fix loop in its own context.

Script and tooling work — automation scripts, utilities, test harness code —
has a **fixed tier**: the medium one, whatever the session command names as
the main-flow executor (`orchestration.scripts` in the model map). The check
round there costs seconds, and the medium tier closes such work in full.

## Orchestration mode

The user turns the mode on with a session command and names the main-flow
executor in it — `orchestrator-economy.md`. With the mode on, execution goes
to subagents and the orchestrator keeps the task statement, the decisions and
the acceptance. With the mode off, the delegation rules below are the
operating default.

The mode does not switch itself on in the shipped map: `orchestrator` and
`high` are the same model there, so there is no cheaper class to fall back to
by reflex.

## Rights discipline

ro-roles have read and search only. Rights must not be extended on the fly:
if a task needs writes, take an rw-role of the appropriate tier instead of
temporarily raising the rights of an ro-role.

## Delegation

The criterion is the cleanliness of the lead context, not the size of the
work: delegate what needs raw material to reach a conclusion and does not
need it afterwards (searches, surveys, logs, diffs, transcripts,
reconciliations, facts across many files); keep what you reason over (dense
implementation, live iteration, decisions, the dialogue with the user). The
mechanism table — the root contract, "Work cycle".

**Payback of a launch.** A launch costs a fixed overhead: root contract,
lazily loaded rules, agent definition and tool schemas. Measured on installed
roles: about 16 thousand tokens for a read-only role and 20 thousand for a
writing one once the memory server is narrowed to two tools; a role without
a tool list starts near 40 thousand. Calibrate against your own numbers.
Every call of the lead session re-reads its context, so compare over the
turns that remain, not the task alone:

- doing it yourself ≈ raw volume read × remaining turns;
- delegating ≈ launch overhead + report size × remaining turns.

Example: 60 thousand of raw reading, 20 turns ahead — 1.2 million yourself
against 16 thousand + 3 thousand × 20 = 76 thousand delegated. Near the end
of a session (one or two turns left) the same reading is cheaper done
yourself. Under ~5 tool calls the work is yours whatever the arithmetic says.

- **The report is short.** A summary within the size the task sets (default:
  up to ~300 words) plus the path to the full report in a file
  (`session-map.md`). The full text never comes back through the context.
- **Spot-check proportionately.** Re-check the one or two facts the decision
  rests on — a grep, a fragment read, a hash. Re-reading the whole report or
  its sources gives the saving back. "A report is a claim"
  (`subagent-pipeline.md`, "Subagent completion control") still holds; this
  sets its volume, not whether it applies.
- Do not launch a subagent to re-check what an executing gate already
  verifies: the implementing subagent runs its own test loop. An independent
  pass is the orchestrator's call for a regulated area or a disputed
  acceptance (`subagent-pipeline.md`, "Tests run inside the implementing launch").
- If one subagent can close the task, launch one. Unprompted, at most 2–3
  independent scouts run in parallel; a fan-out of workers is a deliberate
  decision, not a reflex.
- Heavy multi-file implementation is **not** a delegation case by default:
  it is dense, cross-linked, and cheaper done directly than specified,
  handed over and reconciled. Orchestration mode reverses this default on the
  user's command: the main flow then goes to the named executor with an
  impact map.
- A fan-out of parallel reviewers or workers over one question is launched
  **only on the user's command**. It is the tool for claims that must be
  checked against a source independently — more deliberation in one pass
  does not protect from an error all passes would share.
- A coordinating session (linked sessions running from it) sends its heavy
  reading to subagents by default; its own context is for correspondence,
  decisions and accepting results. Child sessions follow the same rules.

Task decomposition, final decisions and result integration stay with the
orchestrator.

**Why search goes to a low tier.** Not for the token price: it keeps the
orchestrator's context clean. Directory walks, grep output and dead-end
reads do not belong in the lead session — they push out what the orchestrator
actually reasons over and are re-read on every later turn.
