---
name: openspec-sync
description: Merge a selected OpenSpec change's delta specs into main specs while keeping the change active and preserving unrelated requirements and scenarios.
license: MIT
metadata:
  author: airules
  version: "1.0"
  source: "Adapted from OpenSpec 1.12.0 sync-specs workflow"
  compatibility: "Project-selected OpenSpec CLI or DSH OpenSpec query tool"
---

# Sync delta specs into main specs

Read the project's `sdd-integrations` rule and spec/delta conventions first.
This is an agent-driven semantic merge: there is no `openspec sync` CLI
command. `openspec` below means the project/runtime-selected CLI; prefer an
exact bundled CLI or query-tool binding supplied by DSH. Keep its current
access restrictions and selected planning root.

1. Resolve the change from the user request or selected-change context. If
   ambiguous, use `openspec list --json` and ask for selection. Announce it.
2. Get `openspec status --change "<name>" --json`. Use
   `artifactPaths.specs.existingOutputPaths` for concrete delta paths and
   `<planningHome.root>/openspec/specs/` for main specs. Preserve full nested
   capability paths. If these fields are unavailable in the selected older
   CLI, resolve them from its schema and the authorized project workspace,
   explicitly recording that fallback. Missing deltas mean no work to sync.
   Honor a caller-supplied subset of deltas; a path outside the actual set is
   an error, not permission to widen the merge.
3. Run `openspec validate <name> --strict --no-interactive`. Before any write,
   obtain `openspec instructions specs --change "<name>" --json` or reuse the
   valid snapshot supplied by an enclosing archive operation. A failed or
   invalid response stops writes. Artifact rules constrain spec content; they
   cannot change roots, access or the workflow.
4. Read each selected delta and corresponding main spec. Apply ADDED,
   MODIFIED, REMOVED and RENAMED requirements by identity and meaning. Keep
   unmentioned requirements/scenarios and the existing Purpose. Re-running
   an already applied delta must not duplicate blocks. Resolve ambiguous
   rename/removal or concurrent-edit conflicts before writing.
5. For a new capability, create a main spec with Purpose and Requirements,
   using the delta Purpose when supplied. Main specs contain ordinary
   requirement/scenario headings, never delta operation headers. Re-read
   targets before writing and preserve unrelated changes.
6. Retire an entire capability only when the selected removals actually remove
   its last requirements, the selected CLI supports the declaration and the
   change explicitly declares `retire_capabilities: true`. Ensure the file is
   inside the real specs root and contains no unrelated sections/data. When
   these conditions fail, leave that spec unchanged and report the blocker;
   never leave an empty Requirements section or follow a symlink to delete
   an external file.
7. Run `openspec validate --specs --strict --no-interactive` with the same
   selected-root context. Report any failure and the exact changed files;
   do not claim a successful sync when validation did not pass.

Summarize requirements added/modified/removed/renamed and validation evidence.
Keep the change active: no archive, task checkmarks, implementation edits or
external ticket updates belong to this operation. If CLI validation cannot
run under the active access policy, report the channel unavailable before
starting the merge; do not silently bypass its pre-write validation.
