---
description: "Case book: recording a diagnosed failure so the next agent finds it from the symptom, not from the cause. Covers the entry threshold, the Problem / Symptom / Fix / Reference schema, where entries live, and the boundary with the decisions log and the debugging loop. Load after diagnosing a failure that is likely to recur, or when starting a project case book. Триггеры: куда записать разбор ошибки, кейс-бук, симптом и лечение, эта ошибка уже была, типовая грабля, копилка ошибок"
alwaysApply: false
kind: process
---

# Case book

A case book is a **symptom-side index**. Rules are organised by cause — what
is true about a class of code — and are found by topic. A failure arrives the
other way round: from an error message, a hang, an empty result. The person
who has it does not yet know which topic it belongs to, so a cause-side index
cannot be searched at the moment of need.

The case book closes that gap and nothing else. It is not a second rule set.

## What earns an entry

All three at once:

1. **Diagnosed** — the cause is known and the fix was verified, not guessed.
   An open question belongs in the handover, not here.
2. **Likely to recur** — the same failure will hit someone else on this stack
   or this project. A one-off caused by a local mistake teaches nothing.
3. **Not findable from the symptom** — the message, the log or the platform
   docs do not lead to the cause in reasonable time. If the error text already
   names its own fix, an entry adds noise.

A failure that fails any of the three is closed by the fix and the commit
message. Do not build a diary of everything that broke.

## Schema

```text
Problem:   <what is actually wrong, in cause terms>
Symptom:   <what the person sees — message, behaviour, absence of a result>
Fix:       <the working template, minimal and runnable>
Reference: <the owning rule, vendor doc, or issue that carries the full story>
```

`Symptom` is the search key and carries the reader's words, not yours: the
literal error text, the observable behaviour. An entry titled by its cause is
invisible to the person who has the symptom — that is the whole failure mode
this format exists to prevent.

## One copy of the truth

**If a rule already owns the topic, the entry keeps `Problem` and `Symptom`
and points at that rule instead of carrying a fix template.**

A compressed second copy of someone else's rule drifts. The day it
contradicts the original, nobody can tell which one is current, and both look
equally authoritative. The case book routes to the answer; only when no rule
owns the topic does it hold the answer itself.

Same reason in the other direction: when a case turns out to describe a
standing invariant rather than an incident, promote it into a rule and leave
the entry as a pointer.

## Where entries live

**Never in this file, and never in an installed rule.** Installed copies are
manifest-managed and get replaced on update: an in-file journal is either lost
or blocks the sync forever.

| The case is | It goes to |
| --- | --- |
| specific to this project — its data, its integrations, its history | the project case book, kept with the project's own documents |
| generic for the stack — anyone on this technology hits it | the case book of that stack's overlay, **in the distribution repository**, so it reaches every project |
| generic for any stack | a rule in the distribution core, not a case |

**When a memory server is connected**, it is the natural home for the first
row: incidents are exactly the operational layer it exists for, they are
searched by meaning rather than by path, and they are needed from every
machine. The other two rows stay in git — a case that reaches other projects
is reviewed, diffed and shipped, and a blob cannot be reviewed. Route each
entry once and note in the root contract which destination this project uses;
an entry written to both places becomes two half-current copies, which is the
failure this rule exists to prevent.

A project case book is a file the project owns: `docs/cases.md`, or
`cases.md` at the root when the project keeps no `docs/`. Pick it once and
write it into the root contract next to the rule index — an unnamed location
is chosen again by every writer, and entries scatter into files nobody reads.

Two things make it work: it is listed in the root contract so it is loadable
on demand like any rule, and entries are appended newest-last with the symptom
in the heading. Nothing else is required — a case book that needs tooling to
maintain stops being maintained.

## Dead ends are entries too

An approach that was tried and did not work is worth the same record, and it
is not a decision: nothing was chosen between real alternatives, a path was
spent. Without the entry the next agent spends it again — that is the most
expensive kind of forgetting, because the work looks new.

```text
Dead end:  <what was tried>
Why:       <how it failed — the observable, not the theory>
Instead:   <what is used now>
Do not retry unless: <what would have to change for it to be worth another look>
```

The last line is what keeps the entry from becoming a permanent ban: a dead
end is a result under conditions, and conditions change.

## Constructs that look like defects

A third kind of entry, and the one most often missing: code that **looks
wrong and is not**. Nobody hits a symptom here — someone "fixes" it and breaks
something, then the next person fixes it back. Without a record the loop
repeats indefinitely, and each pass looks like an improvement.

```text
Fact:       <what the code does — checkable against the source>
Why:        <why it is built this way>
Do not:     <what breaks if you "correct" it>
Source:     <author's word | reconstructed from code>
```

`Source` is not bookkeeping. **Author's word** comes from someone who knows
the intent and outranks a reading of the code. **Reconstructed from code** is
an inference: it may be incomplete, and it is overturned by new evidence far
more cheaply. Entries without this marker get treated as equally certain, and
the weaker one wins an argument it should have lost.

An entry is worth writing when a construct looks like a defect but is not, or
looks trivial but carries non-obvious meaning. The rule of use is a grep by
module or function name **before** editing in that area and before calling
anything a defect.

The same marker is worth carrying on case entries and dead ends: "verified on
a live run" and "concluded from the logs" are different strengths of claim.

## Boundary with the neighbours

Three rules record things after the fact, and picking the wrong one buries the
entry where nobody looks for it.

| You have | Record as | Where it is defined |
| --- | --- | --- |
| a failure that will hit someone else the same way | case entry | this rule |
| an approach that was tried and abandoned | dead end | this rule |
| a construct that looks like a defect and is not | fact entry | this rule |
| a choice between real alternatives, hard to reverse | decision | `decisions-log.md` |
| the closing of one investigation — hypothesis confirmed, prevention question | post-mortem | `debugging-loop.md`, phase 6 |

They compose rather than compete: a debugging run ends with the post-mortem
question, its structural answer may become a decision, and its symptom may
become a case entry. What must not happen is the same content written into all
three — then every copy is half-current.

## Companion rules

- `debugging-loop.md` — the investigation that produces the diagnosis; its
  phase 6 is where the decision to write an entry is made.
- `decisions-log.md` — the same discipline for decisions, including the
  threshold shape and the ban on editing installed copies.
- `session-handoff.md` — where an **undiagnosed** failure goes instead.
