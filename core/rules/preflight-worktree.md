---
description: "Pre-flight checklist before non-trivial edits in a potentially dirty working copy. Load before full-cycle work, metadata/form/rules edits, refactoring, generators, or risky automation. Триггеры: предполётная проверка, рабочая копия, бэкап, грязные файлы, область записи"
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
4. Determine the write scope and the files likely to be affected.
5. Read the project's source-of-truth rules before editing.
6. Create a timestamped backup for rules, metadata XML, forms, generators,
   bulk edits, or risky scripts.
7. Decide whether light subagents can run parallel exploration or review.
8. Name the planned verification before starting the implementation.

## Backup

Use the project's backup directory (default `.rules-backups/`; set in the
root contract) unless a project rule says otherwise. Attach a manifest
with the original paths and the purpose. Never delete backup files without
an explicit user instruction.

## Output

Keep the summary for the user short: goal, write scope, risks, backup path
if one was created.
