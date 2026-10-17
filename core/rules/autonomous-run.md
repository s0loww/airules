---
description: "Executing an approved multi-day spec without per-phase confirmations: forks closed and recorded, executable gates, unattended decisions ratified. Триггеры: автономный прогон, без подтверждений, ратификация, развилка."
alwaysApply: false
kind: process
---

# Autonomous run

## What it is and when it applies

An autonomous run is a mode in which the lead agent executes an approved
specification **without confirmation of each phase**: it settles forks by
rules agreed in advance, verifies the result by an executable gate and
reports at phase boundaries. Decisions made without a human stay the
human's: they are recorded and brought to ratification.

Apply it when all entry conditions hold and the work is measured in days,
not hours. Do not apply it to a task that closes in one interactive session,
when there is no executable gate, or when the result cannot be isolated from
shared state (no branch, work on live data).

Templates for the artifacts named below — `autonomous-run-templates.md`.

## Entry conditions

The run does not start until all six exist. Each is an artifact, not an
intention.

1. **Specification** for every phase, with acceptance criteria that are
   checked by execution.
2. **Register of open questions with assumptions.** For each question: who
   answers, what it blocks, **the assumption the work proceeds on until the
   answer**, the deadline. A specification resting on an assumption carries a
   reference to the question and an estimate for both answers. The register
   is what lets the run keep going: for most forks the "what we proceed on"
   is there in advance.
3. **Executable gate.** One command giving a machine verdict on everything
   done so far (regression, snapshots, static checks). Without it "green" is
   an opinion.
4. **Isolation.** All work in branches not merged into the main one;
   databases and environments are copies. Every change is marked "draft —
   not approved until ratification". Isolation is what makes "decided it
   myself" admissible: a rejected decision costs a rework in a branch, not an
   incident.
5. **Numbering taxonomy.** One document: which number spaces exist
   (questions, decisions, defects, slices), what each prefix means, how to
   refer to them. Numbers are stable — never reused, never renumbered.
   Without it cross-references fall apart by the fifth day.
6. **Session memory that survives compaction.** The run is one session;
   rules and context are restored after auto-compaction (the rule reminder
   hook, slice handoff files). This holds for the lead agent only: a
   subagent seldom follows a post-compaction reminder, so subagents are kept
   short of compaction (`orchestrator-economy.md`, "Resident agents"). If the
   session breaks, `session-handoff.md` applies — a new session continues
   nothing silently.

## Permission ladder

Three steps; stepping back down is possible at any moment.

| Step | The agent | The human |
| --- | --- | --- |
| 1. Specification | writes specifications, the register and the gate together with the human | decides, approves |
| 2. Phases under confirmation | executes a phase, shows the evidence, waits | confirms each phase; watches how the agent settles forks |
| 3. Autonomy | executes phases in a row, settles forks as below, reports | reads the reports; steps in when they see fit |

**Permission for step 3 is explicit and recorded:** who gave it, when, for
which phases, until which event (for example "until the decision session").

The permission **covers**: commits into isolated branches; running the gate;
creating and deleting the agent's own disposable copies and environments;
applying assumptions from the register; settling forks with a record.

The permission **never covers**, whatever the specification says: merging
into the main branch; pushing and publishing; actions in shared and
production environments; irreversible operations on someone else's data;
sending messages to people on the user's behalf (the questionnaire is
prepared, a human sends it); spending money; widening the agent's own rights
or the permission itself. These limits hold in every mode — an action
outside them is not a fork to settle but a boundary: that line of work stops
with a request.

## A fork: who settles it

A fork is any place where the specification does not say what to do, or says
it wrong.

**The mode decides, not the price of undoing.**

- **Autonomous work** (step 3) — the lead agent settles the fork **itself**
  and records the decision (next section): what was decided, why, what was
  taken as the default, how it shows in the business logic, and a request
  for final ratification. Work continues. This includes a fork that changes
  the composition or order of phases: the lead agent decides; it may have
  the planning role work the re-plan out, but the decision and the record
  are its own.
- **Interactive work** (an operator is present: steps 1-2 and an ordinary
  orchestrator session) — **stop, ask the operator, wait for the answer.**
  Options and a recommendation go into the question; that line of work
  stands until answered.

Three outcomes in autonomous work:

- **The register has an assumption** → apply it and mark the decision
  "default applied, awaits confirmation".
- **No assumption** → choose the option that is **cheaper to undo**, record
  it with the alternative and the price of undoing, and add the question to
  the register after the fact.
- **An assumption from the register is refuted by a check** → choose the
  replacement, and state in the record which assumption was refuted, by
  what, and what replaced it. Never swap one assumption for another
  silently.

There is no numeric threshold on the price of undoing; the price is a field
of the record, and the ratification package is ordered by it.

When a line of work stops at a permission boundary: stop **that** line and
continue the others; diagnose the options on disposable copies, **without
commits**; write the decision request — the fact, the diagnosis with run
numbers, a table of options (what it is, pros, cons and risks, what remains
to be done), a recommendation, the list of what must be decided.

## Decision record

A decision is recorded **at the moment it is made, in the source**
(specification, tasks, slice design) — not reconstructed later from memory.
The ratification package is an assembly of these records.

| Field | Meaning |
| --- | --- |
| Number | stable, per the taxonomy |
| Decision | what was done |
| Alternative | what was rejected |
| Why | the grounds; the register question, if the decision is its assumption |
| Where recorded | file and commit |
| **Who decided** | the user / the agent on a register assumption / the agent without one. Never empty |
| **Impact if rejected** | what to redo and what it costs — concretely, with commits and an estimate |
| Status | answered / default applied, awaits confirmation / open |
| Urgency | blocks release / needed before the decision session / discussion only / can wait |

## Slice evidence

A slice (a work package inside a phase) closes with a handoff file: commits;
the gate run number and its exit code; what was compared with the reference
and the result; static checks as "was N — now N"; **what was not run and
why** (an unavailable tool is named, not passed over); the decisions made in
the slice (numbers); the defects found (numbers); what is left open.

A task status changes **after** the check, never before.

A cheap check comes before an expensive one: syntax and static analysis
before a deployment and a run on the environment. A red gate has a budget of
three fix iterations (`subagent-pipeline.md`, "Red gate budget").

## Reporting along the way

An interim report at every phase boundary and whenever a line of work stops
at a boundary: what is closed (with references to handoff files), new
decisions (numbers, how many await confirmation), new questions, what is
stopped and what it waits for, what comes next. Numbers in a report come
from files and runs, not from memory.

## Ratification

**One register — several views.** Forks are kept in one structured register;
from it two documents are assembled:

- the **ratification package** — for whoever gave the permission: "what was
  decided for you";
- the **questionnaire for addressees** — for external people: "what to
  confirm", in their terms and their language.

Both are **living documents**: answers arrive over weeks and the run does
not wait for them. Therefore:

- versions with a "what is new" section; numbers never change;
- an index with status and urgency; a summary with counters and a "most
  urgent" list;
- for every item — whether it blocks the release or can wait;
- one worked example with numbers that the explanations refer to.

A human sends the documents. The agent enters the answers: the item status,
what changed, which decisions it affects.

## After ratification

Accepted — status "answered"; the "draft" mark is removed from a change when
all its decisions are accepted. Rejected — this is a **change request**: the
estimate from "impact if rejected" becomes a task and is executed in the
ordinary order, not as a quick fix. Until a decision is ratified the change
stays a draft and is not merged, however green it is.

## When the whole run stops

- the gate is red after three fix iterations and there is nothing
  independent left to continue with — a parked slice by itself does not stop
  the run;
- verification became impossible (the environment is lost, a tool is
  unavailable) and further work would be "on trust" — only what is still
  verifiable continues;
- a contradiction is found in the specification that devalues phases
  already done;
- the permission is exhausted (phases, deadline) or the user withdrew it.

A stop is a report with the current state, not silence.

## What must not be done

- settling a fork without recording it (the decision exists only in code);
- replacing a refuted assumption with another without saying so in the
  record;
- writing "done" before the check, or calling "passed" what was not run;
- merging, pushing, publishing — even when "everything is green";
- treating the permission for autonomy as permission for everything not
  forbidden: it covers only what is listed.
