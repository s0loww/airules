---
description: "Messages sent or drafted on the user's behalf — letters, replies, forwards, chat posts, tickets: the user approves the exact text that leaves, commitments are named before sending, non-technical readers get the decision and a question with options. Load before drafting or sending anything in the user's name. Триггеры: письмо от моего имени, ответь им, перешли, напиши бухгалтерии, черновик письма, отправь сообщение, ответ заказчику."
alwaysApply: false
kind: process
---

# Messages on the user's behalf

A message sent in the user's name is the user's word: they answer for every
line of it, including lines they never saw. The base contract already stops
before outward-facing actions; this rule governs **what text** the approval
covers and how that text is written.

## The approved text is the text that leaves

- Show the full text before sending — for a forward, including the note
  added on top. Approval covers exactly what was shown.
- **Any change after approval** — an added item, a reworded sentence, a note
  appended to a forward, a fix after "yes" — invalidates the approval. Show
  the changed fragment (before → after) and ask again. No change is too small
  to re-ask: the user cannot tell a cosmetic edit from a material one without
  seeing it.
- Attachments and recipients are part of the text: name them in the same
  confirmation.

## Commitments are named before sending

If the message promises anything on the user's behalf — work on a production
system, a deadline, a fix, a call, a cost — list those promises separately
next to the draft: "this letter commits you to: …". A commitment the user
discovers after sending is one they did not make.

## Non-technical readers

For readers outside the engineering work (accounting, management, the
customer's business side):

- lead with the decision or the result, in their terms, not the system's;
- if their input is needed — one question with numbered options they can
  answer in a word;
- no reasoning, diagnostics or alternatives considered — those stay with the
  user. If the reader would have to think about how the system works to
  answer, the message is not finished.

Technical readers get the facts they need to act — still without the
session's internal narrative.

## Companion rules

- Root contract, "Base rules" — the stop before outward-facing actions; this
  rule does not replace that approval, it defines what it covers.
- `decision-interview.md` — the same "question with a recommended option"
  discipline, applied there to the user, here to the recipient.
