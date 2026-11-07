---
description: "Session map: subagent and child-session reports as files under var/tmp plus an index that survives compaction and goes to linked sessions. Триггеры: карта сессии, отчёт субагента в файл, после сжатия контекста."
alwaysApply: false
kind: process
---

# Session map

A subagent's full report does not belong in the lead context (the root
contract, "Work cycle"): it goes into a file, and the lead session keeps an
index of those files. The index is what survives a compaction and what a
linked session or the next subagent starts from instead of re-reading the
sources.

## Files

- Map: `var/tmp/session-map-<task>.md`. Reports:
  `var/tmp/reports/<task>/<id>-<topic>.md`. Outside git, like a handoff
  document: transport and working knowledge, not an artifact.
- **The map is an index, not content.** Header: task, lead session,
  status (`active | closed`). One line per report:

  ```
  | id | question | file | base | date | verified by lead | used by |
  | 03 | where is X posted | reports/x/03-posting.md | a1b2c3d: src/post/, src/reg/ | 2026-10-16 | hashes matched | lead, linked:fix-x |
  ```

  `base` — commit plus the paths the report covers. `verified by lead` — what
  the lead session checked itself: `hashes matched` / `diff reviewed` /
  `two facts spot-checked` / `not verified`. Never more than was done.
- Every report opens with the same base line — commit and paths — so it can
  be judged without the map.

## Who writes what

- An rw-subagent writes its full report to the path the task names and
  returns a short summary plus that path (`subagents-model-routing.md`,
  "Delegation"; prompt wording — `subagent-task-templates.md`, "Report
  size"). An ro-subagent returns the bounded evidence requested; the lead
  persists it as the report. Do not expand a scout's write permissions just
  to save a report.
- Child sessions and subagents write only their own report files. **The map
  belongs to the lead session**: it alone adds lines, otherwise parallel
  sessions corrupt one file.
- Secrets and personal data are redacted from reports and the map, as in a
  handoff document.

## Using an entry

Before relying on an entry, check it is fresh — one command:

```
git diff --stat <base commit> -- <paths of the entry>
```

Empty output — the entry stands. Any change — the entry is stale: re-check
the facts the decision needs, or re-run the scouting, and update the line.
`verified by lead: not verified` means the report is still a claim
(`subagent-pipeline.md`, "Subagent completion control").

## Passing it on

- **Linked session** — the map path is a separate item of its brief
  (`session-handoff.md`, "Linked session for an independent subtask"), next
  to the base commit; the child reads the entries it needs and checks their
  freshness itself.
- **Handoff document** — the map path goes under "Artifacts by reference".
- **Subagent** — name the report files it needs, not the whole map.
- A cloud session or any environment that does not see the local files gets
  the needed entries as content in the brief, not paths.

## After compaction

Where the rule reminder hook is installed, it names the existing
`var/tmp/session-map-*.md` files after a compaction. The lead session
re-reads its map before re-reading any source: the map says what is already
known and against which base. Without the hook, re-reading is on the lead
session.

## Lifetime

- The map lives until the task is closed. On closing: durable knowledge goes
  where it lives for good — project memory, `case-book.md`,
  `decisions-log.md`; the map and its reports are deleted.
- On the user's "clean up old maps" — list the maps with their status and
  date, delete those the user confirms.
- **Boundary with memory.** The map is the working knowledge of one task. It
  is not a second memory: nothing in it is a source of truth after the task
  closes, and nothing durable may exist only there.
