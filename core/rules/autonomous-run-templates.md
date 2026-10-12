---
description: "Templates for the artifacts of an autonomous run: the register of open questions with assumptions, the decision record and the ratification package, the question for an external addressee, the slice handoff. Load when writing any of these documents. Триггеры: шаблон реестра вопросов, запись решения, пакет ратификации, вопрос адресату, вопросник, передача среза"
alwaysApply: false
kind: process
---

# Autonomous run — templates

The rule is `autonomous-run.md`; this file holds only the shapes. Write the
documents in the language of their reader.

## 1. Register of open questions with assumptions

```markdown
# Open questions
Status, version, date. Channel and deadline for answers to blocking questions.

| ID | Question | To whom | Blocks | Assumption (what we proceed on) | Deadline | Source |
|---|---|---|---|---|---|---|
| OQ-33 | <the question, with the options named> | <role of the addressee> | <specification, reference data> | <the option taken until the answer> | <date> | <law, form guide, file> |
```

With a register in place: a specification resting on an assumption carries
in its header a reference to the question and an estimate for both answers.
An answer opposite to the assumption: before the specification is approved —
a revision before development; after — a change request with an estimate.

## 2. Decision record

In the source, at the moment of the decision:

```markdown
> **D-W1-3 (orchestrator, <date>, awaits ratification):** <the decision in one sentence>.
> Alternative: <what was rejected>. Grounds: <why; OQ-NN if it is a register assumption>.
> If rejected: <what to redo, the estimate>.
```

In the ratification package (the assembly):

| No | Decision | Alternative | Why | Where recorded | Who decided | Impact if rejected | Status | Urgency |
|---|---|---|---|---|---|---|---|---|

Package header: what was done and on what grounds; the state by phase
(branch, head, state); the gate result; counters "asking to ratify — N" by
section; "awaiting external answers" by addressee, with deadlines. Sections:
decisions by phase → amendments to the plan → **decision requests** (lines of
work stopped at a permission boundary) → side findings (defects, platform
traps) → blocked by external answers.

## 3. Question for an addressee

```markdown
### A1. <Topic> (OQ-33)

**Status:** answered | default applied, awaits confirmation | open

**Question.** <what exactly must be answered>
- <option 1> — this is how it is now.
- <option 2>
- <option 3>

**Why we ask.** <what must be decided and why now; why the agent cannot decide it>

**How it sits in the business logic.** <where the question stands in the process; which
documents, accounting and reporting it touches; what the system does now; numbers — from
the worked example>

**What the answer affects.** <for each option: what changes, what stays; the risk of
leaving it open; whether it blocks the release>

**To whom and urgency.** <addressee; blocker | before the session | discussion | later; deadline>

**Sources.** <files, register codes>

> **To send (<the addressee's language>):** <the ready wording>
```

For a decision request the list of options is replaced by a table

| Option | What it is | Pros | Cons and risks | What remains to be done |
|---|---|---|---|---|

preceded by the **fact** (what was refuted or hit) and the **diagnosis**
(what was checked, on what, run numbers), and followed by a
**recommendation** and a numbered "please decide" list.

Questionnaire header: the state of the project; "how to read a question";
the status legend; "what is new in this version"; the worked example with
numbers; the index (No, to whom, topic, urgency, status); the summary
(counters, the most urgent by addressee, version history).

## 4. Slice handoff

```markdown
# <Phase>: handoff after <slice> (<change>)
Branch, working copy, what it was started from. Nothing pushed, nothing merged.
Built before ratification: every decision below awaits it.

## Commits
| Slice | Commit | Gate run | Result |
|---|---|---|---|
| B6 | <hash> | <run id> | exit 0; <N> fixtures |

## Checks
- Gate: <exit code, number of fixtures, comparison with the reference — identical / which
  lines differ and why>.
- Static: <check> — <was N, now N>.
- **Not run:** <what and why>.

## Decisions of the slice
<numbers; one line and the status for each>

## Findings
<defects and traps, with numbers>

## Deviations from the specification
<what was done differently and why; what of it goes to ratification>

## Open
<what is left; what it waits for>
```

This is the same genre as `session-handoff.md`, used inside one session: the
next slice starts from the file, not from what the context still holds.
