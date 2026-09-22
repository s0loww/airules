---
description: "Intent-driven testing: an agent explores the product like a naive user, turns discrepancies into questions, a human ratifies each one, and every ratified invariant is pinned by a deterministic test and recorded with a stable ID. Load before exploratory or acceptance testing through the UI, when recording why a behavior is deliberate, or when a finding must graduate into a test. Триггеры: исследовательское тестирование, агент как пользователь, интент, намерение, ратификация, зафиксировать поведение тестом, баг или так задумано, журнал разрывов."
alwaysApply: false
kind: process
---

# Intent-driven testing

Two oracles work together. **Deterministic tests** gate every change but only
check what someone thought to assert. **An exploring agent** finds what no
assertion covers but is non-deterministic and only advises
(`test-model.md`). Stored **intent** is what connects them: without it the
agent can see what the code *does*, never whether that is deliberate.

## The loop

1. **Explore as a naive user.** Take a real task, find the way through the
   UI and whatever user-facing documentation exists, try to finish it. Do
   not read the source of the feature under test first — it contaminates
   the newcomer view.
2. **Turn discrepancies into questions.** Odd naming, an undocumented
   prerequisite, behavior against common domain practice — record and ask.
   Assume neither "bug" nor "intended".
3. **A human ratifies**, choosing one of four answers per question:

   | Answer | What happens |
   | --- | --- |
   | Ratified | behavior is correct — pin it with a test now |
   | Direction | intended future, today's code may differ — record, no test |
   | Bug | today's behavior is wrong — a test encodes the *right* behavior and fails today |
   | More discovery | reproduce on a cleaner fixture first — nothing is recorded |

   Batch two to four candidates per ratification round.
4. **Pin.** Each ratified invariant becomes a deterministic test. Source
   reading is fair game now. Prefer the cheapest test that pins it — a
   structural assertion often beats a full end-to-end flow.
5. **Record** the invariant in the project's intent registry (below).
   Cosmetic and UX observations are not invariants — they go to the issue
   tracker or a change proposal.
6. **Clean up.** Exploration leaves visible artifacts in the environment;
   mark them for removal the way the product allows. Permanent deletion is
   a user action.

## The rule that keeps it honest

**Never launder a bug into intent.** Intent inferred by an agent from
possibly buggy code is a hypothesis: status `inferred`, and the agent may
only *question* against it, never *fail* against it. Only a human moves it
to `ratified`.

## Intent registry

One file per area, many invariants per file; the location comes from the
project profile. Each invariant carries:

| Field | Content |
| --- | --- |
| ID | `<AREA>-<SUBAREA>-<NNN>`, stable forever |
| Statement | one testable MUST |
| Status | `ratified` · `inferred` · `disputed` · `direction` |
| Ratified by / date | who signed off, when |
| Why | the rationale — the part the code cannot tell |
| Enforced by | the test that pins it, or `pending` |

The two ends link both ways: the test cites the ID in a comment, the
invariant cites the test. An invariant with `pending` is stated, not
guaranteed.

## Ratified bug, failing test

A test that encodes a ratified bug fails today and would block every change
if it ran in the gate. Write it, keep it **out of the gating list** with a
one-line promotion criterion next to it ("promote once X lands"), and mark
the invariant `drafted, fails today`. Whoever fixes the bug promotes the
test — the move into the gate is the proof of the fix.

## Gap log

A long exploration or simulation run keeps a numbered gap log: symptom,
evidence, suspected cause. Read it as **symptom = evidence, cause =
hypothesis**. Before fixing a gap, reproduce it on a fixture and confirm the
mechanism in the source; a gap that does not reproduce is not fixed blind.
Close each gap with a verdict: fixed · by design · not reproduced ·
disputed.
