---
description: "Orchestrator economy mode: the lead agent on a model class above the channel tiers delegates execution to subagents as much as possible, keeping decisions and verification for itself. Load when the session runs on an orchestrator-class model or the user enables economy mode. Триггеры: режим экономии, оркестратор, делегирование, дорогая модель"
alwaysApply: false
---

# Orchestrator economy (pluggable mode)

## When the mode is on

- **Automatically** — the lead agent's model belongs to the `orchestrator`
  tier of the current channel's `core/channels/model-map.yaml` (a class
  above `high`): its tokens are several times more expensive than the
  channel tiers.
- **Manually** — the user enables it with a phrase ("режим экономии" /
  "economy mode") or with a line in the root contract:
  `Оркестрация: economy`.
- **Disabling** — `Оркестрация: standard` or an explicit user instruction;
  the lead agent is then free to do the work itself under the usual
  delegation rules (`subagents-model-routing.md`).

## Principle

Orchestrator tokens are the most expensive resource of the session. In
economy mode the lead agent **does not do anything itself that a
channel-tier role is capable of doing**: it thinks, decides, and verifies;
subagents do the reading and writing.

## Division of labor

The orchestrator keeps for itself:

- task decomposition and the order of work;
- architectural decisions; decision forks go to the user, not to a
  subagent;
- specs for subagents (with all accepted decisions inside);
- spot-checking reports against primary sources;
- integrating results and the final report.

Always delegated:

- exploration, inventory, bulk reading of sources — `explorer` (low);
- writing files, code, documents from a ready spec — `developer` /
  `doc-writer` / the specialized role of its tier;
- mechanical multi-file edits — a bounded-worker with a non-overlapping
  write scope;
- running ready scripts and collecting logs — a low-tier executor
  (see `script-contract.md`).

Output rule: the orchestrator's own text is minimal — decisions, specs,
summaries. **The orchestrator does not write file bodies. Do not do
yourself what gets delegated.**

## Mode discipline

- A spec for a subagent contains ready decisions: the subagent executes,
  it does not invent (format — `subagent-task-templates.md`, transfer
  between stages — the Handoff from `subagent-pipeline.md`).
- Independent tasks run in parallel; while subagents work, the
  orchestrator does not idle and does not duplicate their work.
- Exploration reports are spot-checked against primary sources (a quick
  grep / reading a fragment): light models hallucinate — verification is
  mandatory before making decisions based on a report.
- Review of results is selective (key files, the most contentious
  decisions), not a full re-read: full reading eats up the savings.
- Escalation: if a subagent failed twice on a clear spec — the
  orchestrator does it itself; a third iteration costs more than doing it
  directly.

## Applicability boundaries

- Trivial edits (quick-fix level from `collaboration-modes.md`) are not
  delegated: the overhead of launching a subagent exceeds the savings.
- Answering user questions, discussion, and choosing decisions are the
  orchestrator's work; the mode does not affect them.
- Savings grow with volume: the more files are read and written, the more
  strictly the mode applies.
