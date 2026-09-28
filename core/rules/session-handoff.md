---
description: "Handing work over between agent sessions: when to fork a fresh session vs compact the current one, what goes into the handoff document, where it lives and how a new session takes it over. Load when a task outgrows one context window, the user asks to continue elsewhere, or a session starts with a handoff on offer. Триггеры: передача сессии, хэндофф, новая сессия, продолжить с handoff, контекст переполняется, компакт."
alwaysApply: false
kind: process
---

# Session handoff

Adapted from the `handoff` skill of
[mattpocock/skills](https://github.com/mattpocock/skills) (MIT). This rule
covers handover **between sessions**; the Handoff block **between
implementing subagents** inside one change is defined in
`subagent-pipeline.md` — same discipline (inventory, not retelling),
different scope.

## Fork vs continue

- **Handoff forks.** A handoff document seeds a *fresh* session with a clean
  window. Use it at a phase boundary, or when the current window has
  degraded past useful work.
- **Compaction continues.** Summarizing the current context keeps the same
  session going. Acceptable between phases; **do not compact mid-phase** —
  finish the phase or hand off at its boundary. A compaction loses exactly
  the fine-grained state a phase in flight depends on.
- Quality drops long before the hard context limit: past roughly the first
  half of the window ("smart zone", on the order of 100–150k tokens on
  current large models) reasoning gets dull. Plan the handoff *before* the
  edge — a handoff written by a degraded session inherits the degradation.

## What goes into the handoff document

0. **Header** — the snapshot the receiving session will compare against:
   `Status: active | blocked | completed`, time written, repository root,
   branch and HEAD, and the working tree at that moment (staged / unstaged /
   untracked paths — paths only, no diff).
1. **Focus** — what the next session is for, one or two lines. If the user
   named it, use their wording.
2. **State of work** — done / in progress / not started, by plan step if a
   plan exists.
3. **Artifacts by reference** — paths, change ids, commit hashes. **Do not
   duplicate content that already lives in artifacts** (specs, plans,
   workspace documents, commits, diffs): the handoff points, it does not
   retell. Duplicated content drifts from its source and the next session
   trusts the stale copy.
4. **Locked decisions** — one line each, with the reason; the next session
   does not reopen them without the user.
5. **Open questions** — unresolved items, each with what is blocking it.
6. **Suggested loads** — which rules from the Rule Index, which roles and
   which project-profile tools the next session will most likely need.
7. **Verification state** — each check that ran: what, against which
   revision (HEAD plus the dirty paths it covered), result. A check that did
   not run is listed as not run, never folded into "done".

## Where it lives

- Write to the project's temporary directory as
  `var/tmp/handoff-<YYYY-MM-DD>-<topic>.md` — **not** into the repository
  tree. The name is a contract: the session-start hook looks for exactly this
  pattern. A handoff is transport, not an artifact:
  committed handoffs rot into a second, stale source of truth.
- Redact secrets and personal data before writing: the file may outlive the
  session and be read outside the original context.
- If the work state belongs in a durable artifact (a plan step done, a
  decision made) — record it there first, then reference it from the
  handoff. The handoff must never be the only carrier of a durable fact.

## Receiving a handoff

A fresh session may be told at start that handoff documents exist (the
session-start hook lists non-completed ones). That notice is an offer, not a
task.

- **Never pick one up silently.** Ask the user whether to continue from it;
  with several candidates, ask which — do not choose by recency.
- **Compare, do not restore.** Check branch, HEAD and the working tree against
  the header. On any divergence, report it and let the user decide. Never
  `checkout` / `reset` / `stash` / `clean` to recreate the snapshot — the
  difference may be the user's own work since then.
- **Reuse verification only on a match.** A recorded result stands only if
  HEAD and every path it covered are unchanged; otherwise re-run the check.
- **A handoff authorizes nothing.** Approvals given in the earlier session —
  destructive steps, scope extensions, publishing — do not carry over; confirm
  them again. Locked decisions stay locked; permissions do not.
- Once the work is picked up (or abandoned), set `Status: completed` in the
  old document so the hook stops offering it.

## Companion rules

- `subagent-pipeline.md` — the in-change Handoff block between subagents;
  its anti-patterns (retelling, "see the files above") apply here verbatim.
- `decisions-log.md` — where locked decisions get recorded durably.
- `preflight-worktree.md` — the receiving session still runs its own
  preflight; a handoff does not exempt it.
- `case-book.md` — an **undiagnosed** failure is handed over here; once the
  cause is known and it will recur, it becomes a case entry instead.
