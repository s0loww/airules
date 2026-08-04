---
description: "Verification matrix by change type and the closing full-cycle gate. Load when deciding which checks to run before declaring a change done. Триггеры: проверка, верификация, гейт сдачи, что проверить."
alwaysApply: false
---

# Verification matrix

Use the smallest set of checks that matches the real risk. If a check cannot
be performed — say why and name the residual risk. Concrete tool names are
supplied by the project profile; below they are described as categories.

| Change type | Minimal checks | Add as risk grows |
| --- | --- | --- |
| Docs/rules/playbook only | loader/routing smoke if routing changed | — |
| Quick-fix in code | syntax check of the changed module | static logic analysis if logic changed |
| Code logic | syntax check + static analysis + affected automated tests (when a suite exists) | deeper review for shared modules, queries, transactions |
| Query / data access | local impact search + syntax + static analysis | review of query parameters, derived-view filters, callers |
| Metadata (XML) | schema/tool validation when available | load/open the object on a test environment when feasible |
| Form (XML/module) | markup/event inspection + form validation when available | UI smoke / opening the form |
| Integration / XML / JSON | check against schema/sample/reference payload | retry/error/security review |
| Refactoring | caller/usage impact + syntax/analysis | wider impact search across dependents |
| OpenSpec artifacts | `openspec validate` or the project equivalent | verify tasks/specs/design stay consistent |
| Platform playbook/routing | list and read the rules, the tool profile's routing self-check when one exists, smoke script | run across affected profiles when the project defines several |

## Escalation

- Shared module, transaction, data store, or query: add impact analysis.
- Metadata/forms: use metadata tools and validators when available.
- User scenario: add manual / UI smoke if tooling allows.
- High-risk change: the closing gate below **is** the bar — tighten it
  (impact analysis, a deeper validator pass) rather than adding a reviewer.
  An independent `code-reviewer` runs on an explicit user request only
  (`subagent-pipeline.md`, stage 4b).

## Closing gate — full-cycle change

The matrix above picks the right *set* of checks by change type. This section
adds the *order and stop criteria* for any non-trivial change before declaring
it "done". Hard gates run in order; each has an explicit pass/fail criterion
and a bounded retry budget.

### Hard gates

1. **Syntax** — every affected module through the project's syntax check
   tool. Pass: zero `error`-level items. Retry budget: 1 call by default, up
   to 3 only if the previous run returned a substantive defect. Style-only
   linter noise does not justify a retry.
2. **Logic and performance** — static analysis of every affected module,
   always *after* gate 1 passes. Pass: no `critical` / `error` items.
   In-scope `warning`s (introduced by your change) — fix; pre-existing ones
   outside the scope — leave (surgical edits). If results are
   non-deterministic on identical code — take the strictest set and stop, do
   not loop.
3. **Style and standards** — style/review analysis of every affected module
   after gate 2. Pass: no `error` items. Intentional warnings — suppress with
   a targeted linter marker and a one-line reason; blanket suppressions are
   forbidden.
4. **Impact analysis (only if the public surface changed)** — may be skipped
   only for fully internal changes (a private routine of a non-exported
   module; a form-module routine without export; a comment / linter-marker
   edit). Otherwise list callers and dependents. Use the call graph and
   cross-search tools of the project profile; then verify against the local
   source of truth. If no call graph is available, record in "Risks":
   *"Impact analysis degraded — call graph unavailable; dependents listed by
   source-of-truth search, not a recursive graph"*. For metadata changes
   include forms/modules/queries that touch the object. Silently breaking a
   dependent is a defect; skipping the gate without recording it is a defect.
5. **Metadata (XML) (only if XML was edited)** — validate every changed file
   with the metadata tools / project validation scripts (form validation,
   compile/load smoke where available). If a separate XSD schema validator is
   available in the session — run it too; otherwise state the fallback
   validation used. For a form file additionally confirm the form opens in
   the platform's native designer without warnings, when feasible.

### Soft gates — as applicable

- **A. Reproduction case (debugging tasks)** — re-run the phase-1 feedback
  loop from `debugging-loop.md` on the original, unminimised scenario after
  the fix; the symptom is gone. Document it in the summary. Remove all
  temporary debug log writes, value dumps, breakpoints, hardcoded test
  values (search by the debug tag — `debugging-loop.md`, phase 4).
- **B. Plan conformance (any written plan / OpenSpec apply / chat-approved
  plan)** — every step done, none silently skipped; diff reconciled per file
  (`git diff --name-only`); no file outside the plan edited without
  justification; `tasks.md` checkboxes and `changes/<id>/specs/` deltas match
  reality.
- **C. Explicit user code review (only when the user asks)** — call the
  `code-reviewer` role; close critical/major before handover. Do **not**
  trigger the reviewer automatically — gates 2-3 already cover the routine
  bar.
- **D. Automated tests (only when the project has a test suite)** — the
  tests affected by the change pass. A bug fix additionally carries a
  regression test at a correct seam, built from the minimised reproduction —
  or the absence of a correct seam is recorded in "Risks"
  (`debugging-loop.md`, phase 5). New tests follow `test-discipline.md`: no
  tautological or implementation-coupled tests, seams pre-agreed in the
  plan. Do not introduce a test suite into a project that has none as a side
  effect of a change.

### Handover summary — what the user sees

After the gates pass the report contains: (1) **What was done** — 1-3 lines,
no preamble; (2) **Changed files** — each path in backticks, one line;
(3) **Context sources** — for non-trivial code/metadata changes the sources
actually used (templates, project code, metadata, platform/standards docs);
(4) **Risks** — real ones only, including the gate-4 degradation record
verbatim; (5) **Leftovers** — noticed but unfixed defects. Omit empty
sections. Do not restate the request, do not list invoked tools, do not add
empty "structural" sections.
