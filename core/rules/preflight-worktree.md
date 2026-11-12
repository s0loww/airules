---
description: "Pre-flight checklist before non-trivial edits, generators or risky automation in a possibly dirty working copy. Триггеры: предполётная проверка, грязные файлы, бэкап, область записи."
alwaysApply: false
kind: process
---

# Working copy pre-flight check

Apply before full-cycle work, metadata/form/rules edits, refactoring,
generators, and risky automation.

## Checklist

1. Classify the task: quick-fix or full-cycle (the boundary — root
   contract, "Work cycle").
2. Check the status of the relevant working copy when it is a git
   repository.
3. Identify unrelated dirty files and do not revert them.
4. Determine the write scope and the files likely to be affected. In a
   session started in its own worktree, the scope is that worktree: other
   working directories (the main checkout, sibling sessions) are read-only,
   and merging or pushing to the main branch waits for an explicit command
   (`session-handoff.md`, "Linked session").
5. Read the project's source-of-truth rules before editing.
6. Create a timestamped backup for rules, metadata XML, forms, generators,
   bulk edits, or risky scripts.
7. Decide whether a wide read-only survey is worth one scouting subagent
   (`subagents-model-routing.md`, "Delegation").
8. Name the planned verification before starting the implementation.

## Backup

Use the project's backup directory (default `.rules-backups/`; set in the
root contract) unless a project rule says otherwise. Attach a manifest
with the original paths and the purpose. Never delete backup files without
an explicit user instruction.

## Output

Keep the summary for the user short: goal, write scope, risks, backup path
if one was created.

## Commits in a shared working copy

Stage only the paths changed for this task, named explicitly in `git add`.
Avoid `git add -A`, `git add .` and broad directory arguments when other
sessions share the checkout: they can absorb another session's work.
Inspect the staged paths and full staged diff before committing; leave
unrelated changes unstaged. If foreign files entered a commit, report them
and agree on recovery before rewriting shared history.
