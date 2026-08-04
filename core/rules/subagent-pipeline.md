---
description: "Formalized stage discipline for a non-trivial change: plan → implement → spec-conformance review → optional code review → verification gate, with a mandatory Handoff format. Stages fix the order and gates; whether a stage is delegated follows the delegation rules. Load for any full-cycle task. Триггеры: конвейер, субагент, полный цикл, передача между этапами."
alwaysApply: false
---

# Subagent pipeline — full-cycle flow

**When to load this file:** any full-cycle task (the quick-fix / full-cycle
boundary lives in the root contract, "Work cycle"). For a quick-fix the
pipeline is overhead: a direct edit + syntax check is enough.

**Stages vs delegation.** The pipeline prescribes the *order of stages and
their gates* — it does not mandate delegation. Whether a stage is delegated
or done by the main agent is governed by the delegation rules
(`subagents-model-routing.md` damper, `orchestrator-economy.md` when
active): stage headers name the fitting role *for when the stage is
delegated*. In particular, heavy multi-file implementation may deliberately
stay with the main agent (the role registry's calibration) — the stage
order, its responsibilities and its gates apply unchanged to whoever runs
the stage.

**Companions:** `subagents-model-routing.md` (delegation and role routing),
`subagent-task-templates.md` (bounded prompts), `verification-matrix.md`
(closing gate).

The pipeline is adapted from subagent-driven development practice and joined
with the role registry `core/agents/ROLES.md` (bodies — `core/agents/roles/`).

## Why a fixed pipeline

Without a fixed pipeline the main agent tends to:

- start writing code before the plan is checked;
- skip structural verification because "the code is small and obvious";
- merge spec-conformance checking and routine quality review into one blurry
  review and miss both.

The pipeline removes these failure modes by separating **what to build**
(planner), **how to build** (developer), **spec conformance** (parent's
structural review), the optional user-requested code review, and the final
verification gate.

## The pipeline

```
[user request]
      │
      ▼
┌─────────────────────────────┐
│ 1. Triage                   │  main agent
│    quick-fix vs full-cycle  │
└──────────────┬──────────────┘
               │ full-cycle
               ▼
┌─────────────────────────────┐
│ 2. Plan                     │  planner (or architect) —
│    plan.md / tasks.md       │  or main agent, per delegation rules
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ 3. Implementation           │  developer (or metadata-manager) —
│    code + metadata edits    │  or main agent, per delegation rules
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ 4a. Spec-conformance review │  main agent (cheap, structural)
│     does it match the plan? │
└──────────────┬──────────────┘
               │  passes
               ▼
╭ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ╮
  4b. Code quality review        OPTIONAL — only when the user
      style, anti-patterns,      explicitly asks for review.
      standards                  Delegate → code-reviewer.
                                 Otherwise skip; stage-5 gates 2/3
                                 already cover routine quality.
╰ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ╯
               │
               ▼
┌─────────────────────────────┐
│ 5. Verification gate        │  main agent
│    verification-matrix      │
└──────────────┬──────────────┘
               │  pass
               ▼
        hand over to the user
```

## Rules per stage

### Stage 1 — Triage (main agent)

Apply the triage boundary of the root contract ("Work cycle"): only
**full-cycle** tasks enter the pipeline. If the task is a quick-fix — edit
directly and go to stage 5 with minimal verification (syntax check only).
Two bypass paths sit outside both modes: tasks touching **docs only**
(Markdown / rules / docs) skip the pipeline and code validators — use the
`verification-matrix.md` row "Docs/rules/playbook only"; tasks authoring
**OpenSpec artifacts with domain facts** also skip the pipeline but must
ground every domain fact in project sources (code, structure, data), not in
memory — `sdd-integrations.md` names the canonical artifacts.

If the user asks for a small change that **looks** like a quick-fix but
touches a transactional path, a public export of a shared module, code that
adapts or overrides extended base behavior, an event subscription / scheduled
job / access-restriction rule, or metadata coupled to existing behavior
(rename / delete / immediate use, changes to access restrictions / indexing /
fill validation) — escalate to full-cycle. **Isolated metadata additions** (a
new independent data store / defined type / enumeration / constant /
standalone attribute, with no affected consumer in the same change) stay on
the quick-fix path. When in doubt, full-cycle wins.

### Stage 2 — Plan (planning role — or the main agent, per "Stages vs delegation")

When delegating, pick by the shape of the task:

- **`analytic`** — when a written PRD / specification / domain study is needed
  before any plan. Output: written analysis, no code.
- **`explorer`** — for wide read-only mapping before the plan: locating
  related modules, metadata, entry points, dependencies and callers.
- **`architect`** — for new subsystems, multi-module designs, integrations or
  extension boundaries. Output: an architecture document with module
  boundaries and data flow.
- **`arch-reviewer`** — when an architectural design already exists and needs
  validation before implementation.
- **`planner`** — for everything else that fits one feature: produces a
  numbered task list.

The plan must satisfy the acceptance criteria before stage 3:

- Each task is small enough for an eager junior with no project context:
  usually 1 file / 1 routine / ≤ ~20 changed lines per task.
- Each task names exact file paths and exact routine names — no "update the
  related modules".
- Each task has a verification step (syntax check, a tool query, an
  assertion, manual reproduction).
- Risks and rollback are explicit, especially for metadata changes (UUID
  stability, data-store writes and migrations, role permission grants).
- The plan is reviewed by the user. User approval is a hard gate; do not move
  to stage 3 without it.

For projects on the OpenSpec workflow the plan lives in
`openspec/changes/<change-name>/tasks.md`, the design in `design.md`. The
pipeline does not replace OpenSpec — it plugs into the **apply** phase.

### Stage 3 — Implementation (implementing role — or the main agent, per "Stages vs delegation")

When delegating, pick by the shape of the task:

- **`developer`** — bulk code changes across modules, shared modules,
  server / client routines.
- **`metadata-manager`** — when the bulk of the change is in metadata: new
  objects, forms, reports, layouts, roles, extensions, nested tables,
  attributes.
- **`refactoring`** — dead-code cleanup, deduplication, extraction across
  many modules.
- **`performance-optimizer`** — when the explicit task is to optimize a slow
  query / loop / transactional write / report.
- **`error-fixer`** — fixing runtime / syntax errors without architectural
  rework. Runs the `debugging-loop.md` method inside (a stack overlay may
  supply its platform adaptation of the same loop).

The implementing subagent is bound by the stage-2 plan. Out-of-plan changes
("while we're here") are forbidden — if the developer notices a real defect
orthogonal to the plan, it must report it to the parent, not silently fix it.

The implementing subagent is responsible for:

- editing code / XML;
- running its own syntax check on every touched module before handover;
- preserving module headers, regions and the project code style (the
  dev-standards rule — a stack rule, if an overlay is installed);
- removing only those imports / variables / routines that **its own** changes
  made unused — never pre-existing dead code;
- reconciling the diff against the plan, file by file;
- producing a structured **Handoff** block (see "Stage 3 — Handoff between
  implementing subagents" below) whenever another implementing subagent will
  continue the same change.

### Stage 3 — Handoff between implementing subagents

When stage 3 is split across several implementing subagents within one change
(typical chain: `metadata-manager` builds stubs and metadata, then
`developer` fills the bodies; or `developer` writes the bulk and
`refactoring` consolidates), the parent **must** prevent the downstream
subagent from re-reading what the upstream already produced. Re-reading
bloats the downstream context, costs minutes per file, and is a recurring
failure mode of informal chains.

The mechanism is a fixed-format **Handoff** block that every upstream
implementing subagent places at the top of its final report, that the parent
passes on verbatim, and that the downstream subagent treats as the
authoritative inventory.

**Mandatory Handoff format (produced by the upstream subagent at the very top
of its final report):**

```text
## Handoff (for the next subagent)

### Artifacts
- <full repo path> — <one-line role> [stub | done | edited]
- ...

### Public surface
- <ObjectName>.<RoutineName>(<params>) → <return type> — <one-line purpose>
- <Metadata.Object> — <attribute / nested table / form name>: <type / role>
- ...

### Open TODOs / stubs (for the next subagent)
- <file>:<region or routine> — <what to implement> — <signature hint, if pre-agreed>
- ...

### Locked decisions (do not revisit without approval)
- <decision> — <one-line rationale>
- ...

### Open questions raised
- <CONFUSION-id> — <one-line summary> — <status: resolved / pending>
```

The block is **not** a marketing summary but a machine-readable inventory.
Keep every line short (≤120 chars), one fact per line, no prose paragraphs
inside the block.

**Parent responsibilities:**

- When calling the next implementing subagent on the same change, the parent
  **must** include the upstream Handoff block verbatim in the new subagent's
  prompt under the heading `## Upstream Handoff`. No retelling, reformatting
  or selective omission — retelling is the main source of drift between
  stages.
- If the parent has its own additional instructions (extra constraints, new
  user feedback), they go in a separate section **after** `## Upstream
  Handoff`, not mixed into it.
- The parent does **not** rewrite the artifacts in its own prompt prose — the
  Handoff is the inventory.

**Downstream subagent responsibilities:**

- The downstream subagent **must** read the `## Upstream Handoff` block first
  and treat `### Artifacts`, `### Public surface` and `### Locked decisions`
  as authoritative. Rediscovering them by reading files is forbidden.
- The downstream subagent **must not** do broad file reads or duplicate
  context gathering via tools (module structure, metadata details, form
  markup, parsing helpers, `Glob`) on objects / files already listed in the
  Handoff "for context" or "to check". A targeted call is allowed **only**
  when a specific detail needed for the current edit is missing from the
  Handoff (e.g. an exact UUID, the exact TODO-marker line inside an existing
  region, the full attribute list of a nested table that the upstream reduced
  to `<attribute / nested table …>`). Before such a call the subagent names
  in one sentence which detail is missing and why the Handoff alone is not
  enough.
- The downstream subagent **must** preserve `### Locked decisions` unless the
  user (not the parent) explicitly allows a revision. If a locked decision
  turns out to block a correct implementation — raise a `CONFUSION`, do not
  silently override.
- The downstream subagent adds its own Handoff block at the top of **its**
  report if yet another implementing subagent is expected; otherwise its
  report goes straight to stage 4a.

**Anti-patterns:**

- The downstream subagent opens `Read` on every file from `### Artifacts` "to
  load context" — the inventory **is** the context.
- The parent retells the Handoff in its own words "to keep it short" —
  retelling erases exactly the precision the format exists for.
- The upstream produces a Handoff that only says "see the files above" — this
  defeats the purpose; the Handoff must list the artifacts and the public
  surface, not point at the diff.
- The upstream embeds prose explanations into `### Locked decisions` — keep
  the one-line rationale; long discussion goes into the report body, not the
  inventory.

### Stage 4a — Spec-conformance review (main agent, cheap)

The main agent leads this stage — **not** a subagent. It is a structural
check, not a code review.

Checklist:

- Every plan task is done; none silently skipped.
- No file outside the plan was edited (check `git diff --name-only`).
- Names, parameter types, return types of new public routines match the plan.
- New / removed metadata objects match the plan; UUIDs preserved on edits,
  not regenerated.
- Module headers (return/parameter comment blocks per the dev-standards rule,
  if a stack overlay is installed) are present on new public routines.

If something fails — return to stage 3 with the exact delta. If the optional
4b applies — do not start it until 4a is clean. This is a cheap gate; running
4b before 4a wastes the reviewer on a structurally wrong implementation.

### Stage 4b — Code quality review (delegate to `code-reviewer` when applicable)

Two hard constraints from the role registry and `subagents-model-routing.md`:

- The `code-reviewer` role runs **only when the user explicitly asks for a
  code review**. Auto-triggering after every edit is forbidden.
- For tasks without a review request the parent still runs static analysis
  and style review itself at stage 5 — enough for routine work.

**Fail fast before delegating**: resolve the review base and confirm the
diff is non-empty *before* spawning the reviewer. A bad ref or an empty diff
must fail at the parent — not inside a subagent that was already paid for.

When the user asks for review, the subagent looks at:

- anti-patterns from the anti-pattern and platform-solutions rules (stack
  rules, if an overlay is installed);
- platform standards via the project profile's reference tools;
- linter warnings via the style-review tool;
- query patterns, transactional safety, lock granularity, transaction
  boundaries.

The subagent reports **every** issue with a severity (critical / major /
minor) and a confidence; it does not drop uncertain findings. The parent
filters in a separate pass: critical blocks handover, minor is
informational, low-confidence items are judged or discarded here — not
silently suppressed inside the reviewer.

**Two speeds.** Review precision holds up at the role's default effort, so a
fast pass is worth running whenever a review is requested mid-work. Reserve
an escalated-effort pass for the run right before a release gate — that
escalation is a per-run decision, never the role's default (`ROLES.md`,
"Effort semantics").

### Stage 5 — Verification gate (main agent)

Run the closing gate from `verification-matrix.md`. For full-cycle tasks this
is non-negotiable.

## Subagent completion control

The orchestrator owns the lifecycle of every launch:

- Every subagent prompt starts with the line "do the work yourself, do not
  wait for background processes" (see `subagent-task-templates.md`) — this
  prevents the known "waiting for a background agent" failure.
- On receiving a report, the orchestrator verifies the subagent actually
  **finished**: the result matches the Definition of done of its task and is
  not a promise ("started", "waiting", "will send later"). A promise-report =
  a failure.
- A subagent that returned a failure or hung waiting is restarted with ONE
  direct message: "wait for no one, finish the work yourself, start by
  checking the actual state"; a second failure — stop it forcibly and do the
  work with another role or yourself.
- A long-running subagent with no intermediate signs of work (no new files,
  logs, state changes) is a candidate for forced stop, not for waiting.

## Pipeline anti-patterns

- **Skipping stage 2** "because the change is small" — if it is small, it
  should have been a quick-fix at stage 1.
- **Letting the implementing subagent re-plan** — if the plan turned out
  wrong, go back to stage 2, do not let stage 3 silently rewrite it.
- **Running the optional 4b before 4a** — wastes the reviewer on a
  structurally wrong implementation.
- **Auto-triggering `code-reviewer`** — explicitly forbidden without a user
  request.
- **Parallelizing stage 3 by default** — metadata is densely cross-linked;
  parallel subagents on the same configuration tend to corrupt UUIDs and
  break references. Parallelize only when subtasks are provably independent
  (e.g. one new report + one new shared-module function with no shared
  metadata).
- **"I'll fix this lint while I'm in the file"** at stage 3 — edits are
  surgical; report, do not fix.

## When to deviate

The pipeline is the default for full-cycle tasks. Deviate only with an
explicit reason:

- pure documentation changes — `doc-writer` directly, no plan / development /
  review;
- pure UI runs against an existing build — `tester` directly;
- pure architecture review with no code change — `arch-reviewer` directly.

Document the deviation in the handover summary so the user can check it.
