---
description: "Opt-in batch interview: walk the decision tree, ask the settled frontier in one numbered round with recommended answers. Триггеры: интервью, уточнение требований, гриллинг, вопросы по плану."
alwaysApply: false
kind: process
---

# Decision interview

Adapted from the `grilling` / `batch-grill-me` skills of
[mattpocock/skills](https://github.com/mattpocock/skills) (MIT), converted
to a batch format: questions go out in rounds, not one at a time.

**Opt-in mode.** The base contract stands outside it: routine decisions are
made by the agent, questions are asked only when different readings lead to
materially different work. Enter this mode only when the user asks to be
interviewed ("спроси меня", "давай уточним требования") or agrees to a
proposed interview before a large or ambiguous piece of work.

## The model — a decision tree with a frontier

The subject (a feature, a plan, a migration, a spec) is a tree of decisions.
Some depend on others; a decision is **askable** when everything it depends
on is already settled. The **frontier** is the set of askable decisions at
this moment.

## Round protocol

1. **Build the tree first.** Lay out the decisions and their dependencies
   before asking anything. A question asked before its premises are settled
   produces an answer the user will have to revise.
2. **Ask the whole frontier in one numbered round.** One message, numbered
   questions, so the user answers "1a, 2 — yes, 3 — the second option" in a
   single reply. Do not drip questions one at a time.
3. **Each question carries a recommended answer** with a one-line reason —
   so the user can accept it in one word. Lead with the recommendation.
4. **One idea per question.** Never compound ("should we A, and also how
   about B?"). A question that needs an explainer gets exactly one line of
   context, not a paragraph.
5. **Facts are researched, decisions are asked.** Anything derivable from
   the environment (files, structure, history, project tools) is looked up —
   or delegated to a scout per `subagents-model-routing.md` — never asked.
   Decisions belong to the user; never answer one on their behalf.
6. **Research does not block the round.** A running lookup is an unsettled
   premise: hold back only the questions downstream of it; ask the rest of
   the frontier now.
7. **Recompute the tree from the answers.** New answers settle premises and
   may open new branches; the next round asks the new frontier.

## Completion

The interview is done when the frontier is empty: no askable decision
remains unsettled. Close with a short restatement of the shared
understanding — decisions taken, assumptions recorded — and proceed to the
agreed next step. Do not act on the subject before the user confirms the
restatement.

## Where it plugs in

- `analytic` — the requirements-gathering stage of a spec/PRD.
- `subagent-pipeline.md` stage 2 — resolving plan forks before approval.
- OpenSpec proposal work — settling scope and design questions before
  artifacts are generated.
- `collaboration-modes.md` Exploration — when the exploration goal is to
  understand *intent*, not code.

## Anti-patterns

- A hard limit on the number of questions. Some subjects need three, some
  fifty; the escape hatch is the user saying "enough", not a quota. Too many
  questions usually means an under-specified subject (working as intended)
  or compound/premature questions (fix the questions, not the count).
- Interviewing about facts the environment can answer.
- Asking the frontier one question at a time — a round-trip per question
  exhausts the user's patience on the cheap questions before the important
  ones arrive.
