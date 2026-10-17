---
description: "Handing work between sessions: fork vs compact, the handoff document, taking it over, a linked session in its own worktree. Триггеры: передача сессии, хэндофф, контекст переполняется, связанная сессия."
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
- Quality drops before the hard context limit. Plan the handoff at a phase
  boundary, *before* the window is mostly spent — a handoff written by a degraded session inherits the degradation.
- **A new independent task is a split signal.** When the user brings a task
  that builds on nothing settled in this session, and the context is already
  large or the topic is different — offer a linked session (below) or a
  handoff instead of carrying on here. Every call re-reads the whole context,
  so the cost of a session grows roughly with the square of its length; a
  week of unrelated tasks in one window pays for all of them on every turn
  and ends in compactions that lose the fine state of each.

## Linked session for an independent subtask

Applies only when the environment can start a linked session (a separate
session in its own worktree, visible to the user and reporting back). Without
that mechanism, use a handoff document instead.

**When to offer.** In a coordinating session, a self-contained task appears
that needs its own code edits or its own verification run — and does not need
this session's in-flight state beyond what a brief can carry.

**The brief is self-contained** — the child sees nothing of this session:

1. **Context and base** — project, component/extension, the commit the work
   starts from.
2. **Items** — numbered, each with paths to the modules and routines involved.
3. **Verification scenario** — per item, how to check it (environment, steps,
   expected result).
4. **Constraints** — what not to touch, where not to go (e.g. "no production;
   test environment and edits only after approval").
5. **Reply format** — fixed verdicts per item, e.g. "defect / not a defect /
   not verified".
6. **Session map** — the path to `var/tmp/session-map-<task>.md`, if the
   coordinating session keeps one (`session-map.md`): the child reuses its
   entries after checking their freshness instead of re-reading the sources.
   A child that cannot see local files (a cloud session) gets the needed
   entries as content.

**The child session:**

- writes only inside its own worktree; never `cd` into another working
  directory (the main checkout, a sibling session's tree) — someone else may
  be working there;
- commits to its own branch by itself, without asking: the branch is its
  workspace, and the coordinating session or the user reviews the result
  before anything leaves it;
- when the work is done — or blocked — sends the report to the coordinating
  session by itself, without waiting for a command: verdict per item in the
  brief's reply format, branch and commit, checks run, what was not verified.
  The user should not have to relay it. Address it to the session that
  started this one by the identifier the environment records (its parent
  session id), never by a similar-looking title — sibling sessions on the
  same repository often carry near-identical names;
- merges into the main branch and pushes only on an explicit command. That
  merge is the one exception to the worktree boundary — the main branch lives
  in the main checkout — so first check that checkout is clean, merge
  fast-forward only, and touch nothing else there.

**The coordinating session:**

- records what it started: the session name and its branch;
- treats the child's report as a claim: reviews the diff and re-runs the
  checks before merging;
- checks the child's status and reports before drawing conclusions about
  commits that "appeared" — an unexpected commit on a shared branch is first
  checked against the sessions this one started.

## What goes into the handoff document

0. **Header** — the snapshot the receiving session will compare against:
   `Status: active | blocked | completed`, time written, repository root,
   branch and HEAD, and the working tree at that moment (staged / unstaged /
   untracked paths — paths only, no diff).
1. **Focus** — what the next session is for, one or two lines. If the user
   named it, use their wording.
2. **State of work** — done / in progress / not started, by plan step if a
   plan exists.
3. **Artifacts by reference** — paths, change ids, commit hashes, the
   session map if one exists (`session-map.md`). **Do not
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
  preflight; a handoff does not exempt it. A linked child session runs it too,
  against its own worktree.
- `session-map.md` — the index of subagent and child-session reports that
  a handoff and a linked brief point to.
- `case-book.md` — an **undiagnosed** failure is handed over here; once the
  cause is known and it will recur, it becomes a case entry instead.
