---
name: handoff
description: "Write or receive a compact transfer of an active task between sessions, with current artifacts and verification state. Триггеры: передай контекст, хэндофф, продолжение в другой сессии."
---

# Transfer a task between sessions

Use for an explicit handoff or a planned session boundary. Compaction inside the
same session and delegation inside one change are separate operations.

Discover the project's instruction index and load its `session-handoff` policy
when present. It owns the destination, filename convention and resume procedure;
use the existing pipeline handoff format for a transfer between implementation
stages. Resolve these through the available rule index, not a path assumed from
this skill's installation directory.

## Produce a usable transfer

1. Establish the intended next task, current root/worktree and source revision.
   Record relevant staged, unstaged and untracked paths; distinguish this task's
   changes from concurrent work. Use a content fingerprint when evidence depends
   on uncommitted files.
2. Update an already-owned durable artifact when its state changed, then link it.
   Keep the handoff as transport: reference plans, decisions, logs and evidence
   instead of copying their bodies or making a second project memory.
3. State what is done, in flight and unresolved. Include material constraints,
   the source of authorization and actions still awaiting a decision. A saved
   note carries context, not fresh permission.
4. For each relevant check, retain its outcome and the revision/target it covered.
   Preserve failed, interrupted, not-run and unknown states. A pass for one target
   is not a pass for another; a historical pass does not cover later edits.
5. End with the first executable continuation step and prerequisites. If work is
   complete, record completion without inventing a new task. Suggest only the
   rule IDs, roles and artifacts needed for that step.

Use the user's destination when supplied; otherwise follow the project's
temporary-note convention. Read an existing destination before replacing it and
preserve unrelated content. Avoid copying credentials or raw private payloads.
Report the written path and any unresolved evidence gap. This operation does not
publish a message or create a linked session unless that action was requested.

## Receive a transfer

Compare the note with the current root, revision, dirty paths and active project
instructions before using its evidence. Resolve missing or changed prerequisites
at the first dependent action, then continue the already-authorized next step.
Keep domain-specific source, deployed-state and target checks in their owning
project or stack policy. Do not infer a successful mutation from a source diff.

If a concrete detail is missing from compacted context, use
[history-evidence.md](references/history-evidence.md) for bounded retrieval of
original session events when the host exposes that capability.
