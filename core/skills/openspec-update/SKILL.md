---
name: openspec-update
description: Revise an existing OpenSpec change's planning artifacts after a scope or design decision, without implementing code or refreshing CLI integrations.
license: MIT
metadata:
  author: airules
  version: "1.0"
  source: "Adapted from OpenSpec 1.12.0 update-change workflow"
  compatibility: "Project-selected OpenSpec CLI or DSH OpenSpec query tool"
---

# Update a change's plan

Use this workflow when the user asks to revise an existing change. Read the
project's `sdd-integrations` rule and OpenSpec workspace guidance. The request
authorizes the specified planning edits; clarify only decisions whose meaning
or scope cannot be inferred. Implementation uses `openspec-apply-change`.

Here `openspec` means the CLI selected by the project/runtime. When DSH supplies
an exact bundled CLI or query tool, use that binding. Respect the current
access mode; an unavailable shell does not authorize a global install or npx.
**Do not run `openspec update`: that command refreshes tool instructions and
integrations, not the change's plan.**

1. Resolve the change from the request or selected-change context. If ambiguous,
   list active changes with `openspec list --json` and ask which one to revise.
   State the selected change.
2. Get `openspec status --change "<name>" --json`. Follow the active schema and
   returned planning root/change root. Prefer concrete
   `artifactPaths.<id>.existingOutputPaths`; never write to a glob output path.
   With an older CLI, resolve files from the local change/schema instructions
   and say which fallback was used. Stay inside the authorized planning root.
3. Read the affected artifacts and their dependencies. Use
   `openspec instructions <artifact-id> --change "<name>" --json` when their
   rules/template are needed. Reconcile the edit in both directions: a task or
   design change may alter proposal/specs as well as later artifacts.
4. Edit only relevant existing planning artifacts. Preserve completed-task
   evidence; explain any task reopened by the revised decision. Report missing
   artifacts separately and create them only if the requested scope includes
   completing the plan. Preserve unrelated user changes and re-read a file
   before writing when another actor may have changed it.
5. Run `openspec validate <name> --strict --no-interactive` and refresh status
   when that CLI access is available. If access restricts work to Markdown,
   read the installed schema/templates, edit allowed Markdown only and report
   CLI validation as deferred. A deferred check is not a passing check.

Report changed artifacts, decisions, remaining gaps and validation results.
Leave main specs, implementation code, deployment and archive untouched. If
the revised plan requires code changes, identify them as the next apply scope.
