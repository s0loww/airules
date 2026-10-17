---
description: "Orchestration mode: on the user's command the lead hands execution to a named executor and keeps the statement, decisions and acceptance. Триггеры: оркестрация, исполнитель, резидент, режим экономии."
alwaysApply: false
kind: process
---

# Orchestration mode (switched by the user)

## The command

The user picks the model of the main session. Inside the session a command
decides whether the lead agent executes or orchestrates, and who the
main-flow executor is:

```
Оркестрация: вкл; исполнитель: <модель> <усилие>
Оркестрация: вкл; исполнитель: <модель> <усилие>; резиденты: вкл
Оркестрация: выкл
Оркестрация: статус
```

`<модель>` is a model alias or a tier name known to the model map; `<усилие>`
is a step of the effort scale. The executor may be omitted — the default is
the `orchestration.executor` pair of the model map. The older spellings
`Оркестрация: economy` and `Оркестрация: standard` mean "on with the default
executor" and "off".

On every command the lead agent **echoes the resolved layout** — role, model,
effort for each class below — so the user sees what was understood, and
writes it to the state file `var/tmp/orchestration.json`. After a context
compaction the lead agent re-reads that file before delegating anything: a
command given at the start of a multi-day session is otherwise lost at the
first compaction. Where the rule reminder hook is installed it names the
file after a compaction; where it is not, re-reading is on the lead agent.
The file is the lead agent's own state; subagents do not read it.

The mode does not switch itself on. Where the model map puts the lead agent
on the same model as the `high` tier (the shipped map does), there is no
cheaper class to delegate to by reflex, and delegating on reflex burns the
session window instead of saving it.

## What the command changes

| Class | Roles | With the mode on |
| --- | --- | --- |
| Main flow | developer, metadata-manager, refactoring, error-fixer, tester | run on the executor named in the command — passed as launch parameters, the installed definitions are not touched |
| Fixed by kind of work | reconnaissance; script and tooling work; documentation; re-running ready scripts | keep their own tier (`ROLES.md`, the `orchestration` block of the model map) |
| Deciding | architect, planner, analytic, reviewers | keep the registry default; changed only by an explicit instruction for the task |

Priority, first match wins: an explicit instruction for the task → the
session command → the registry default. The command takes effect **from the
next launch**: an agent already running keeps its model and effort, and
changing either means a new agent with a cold cache.

**Mode off** — the lead agent does dense implementation itself and delegates
reconnaissance and script work (`subagents-model-routing.md`, "Delegation").
**Mode on** — the main flow goes to the executor; the lead agent keeps the
task statement with its impact map, the decisions and the acceptance.

## Division of labor with the mode on

The orchestrator keeps for itself:

- task decomposition and the order of work;
- decisions. A fork the task statement does not settle: in interactive work —
  stop, ask the operator, wait; in an autonomous run — decide and record
  (`autonomous-run.md`). A fork is never handed to a subagent to settle;
- the task statement for the executor: accepted decisions, the impact map,
  the price of one check round (`subagent-pipeline.md`, "Impact map");
- spot-checking reports against primary sources;
- integrating results and the final report.

Delegated:

- exploration, inventory, bulk reading of sources — `explorer`;
- writing code, metadata, documents from a ready task statement — the
  main-flow role, on the executor named in the command;
- mechanical multi-file edits — a bounded worker with a non-overlapping
  write scope;
- running ready scripts and collecting logs — a low-tier executor
  (`script-contract.md`) — but only when the run is part of an iterative
  loop or its output must be digested at volume. A one-shot run of a
  contract script or test suite that writes a machine-readable report is
  cheaper executed directly in the background: the orchestrator consumes the
  one-line verdict and the report path, not the log. Delegate the debug
  loop, not the launch.

Output rule: the orchestrator's own text is minimal — decisions, task
statements, summaries. **With the mode on the orchestrator does not write
file bodies.**

## Mode discipline

- A task statement contains ready decisions: the executor executes, it does
  not invent (format — `subagent-task-templates.md`, transfer between
  stages — the Handoff from `subagent-pipeline.md`).
- Independent tasks run in parallel; while subagents work, the orchestrator
  does not idle and does not duplicate their work.
- Exploration reports are spot-checked against primary sources (a quick
  grep / reading a fragment) before any decision rests on them.
- Review of results is selective (key files, the most contentious
  decisions), not a full re-read: full reading eats up the savings.
- A red gate has a budget of **three fix iterations**, then escalation
  (`subagent-pipeline.md`, "Red gate budget"). The orchestrator does not take
  the work over silently on the second failure.

## Resident agents (off unless the command turns them on)

A resident is a subagent that is not closed after its task but woken for the
next ones. It saves the **discovery** already done — what was read and found
out — not the start-up cost: the system part of a role is the same on every
launch and sits in the cache anyway.

Use one for short follow-ups to ground already covered (a scout answering
"where else is this used?" in two or three tool calls). A whole task of tens
of calls is cheaper on a fresh narrow role that starts from a map: a warm
resident re-reads its entire accumulated context on **every** call.

Rules while residents are on:

- one resident — one model and one effort; neither changes on a wake-up;
- the resident role carries the one-hour prompt cache; without
  it any pause over five minutes rewrites the whole context into the cache
  (the installer sets it on the roles listed in the model map);
- the resident keeps a **map file** as it goes — every task ends with an
  addition to it (what lies where, what was established). A scout without
  write access returns the addition in its report and the orchestrator
  writes it. The map, not the resident's context, is what the next agent
  starts from;
- **recreate it before auto-compaction, never after.** After a compaction a
  subagent seldom re-reads the rules it is told to, and the summary may
  record that it did. Recreate when any of these holds: the context after a
  task exceeds two or three times the role's start-up weight (the size comes
  back with every launch result); the pause exceeded the cache lifetime; the
  topic or the phase changed;
- assumptions and permissions of one task do not carry into the next;
- a scout re-checks files that changed after it read them: its memory is not
  a source of truth.

## Payback of a launch

- Trivial edits (quick-fix per the root contract's "Work cycle" boundary) are not
  delegated: the overhead of launching a subagent exceeds the savings.
- Launch overhead and the payback comparison over the remaining turns —
  `subagents-model-routing.md`, "Delegation". With the mode on the same
  arithmetic holds; the mode only moves the main flow to the executor.
- If a tool-output compression proxy is installed (`tool-output-economy.md`),
  scouting subagents wrap their bulk reads with it — the two economies
  stack; the orchestrator's own spot-checks stay raw (verification, not
  navigation).
- Answering user questions, discussion, and choosing decisions are the
  orchestrator's work; the mode does not affect them.
