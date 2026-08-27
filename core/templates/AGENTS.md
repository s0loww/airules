# Agent contract — {{PROJECT_NAME}}

> Root contract: "how to work". Project facts ("what we work with") live in
> `openspec/project.md` (the passport). Reply and code language — as accepted
> by the project team: {{LANGUAGE_POLICY}}. The contract itself is written in
> English; the instruction language does not dictate the reply language.

## Project

- Project ID: `{{PROJECT_ID}}`
- Stack: `{{STACK}}`
- Source of truth: `{{SOURCE_OF_TRUTH}}` — finally authoritative; indexes and
  RAG are navigation only, confirm facts against the source of truth.
- Source root: `{{PRIMARY_CODE_DIR}}`
- Object name prefix (if applicable): `{{PREFIX}}`

## Base rules

- Verify references and current state before making claims about the repo.
- Changes are minimal, reversible, strictly on task. Do not rewrite others'
  changes and do not write outside the assigned scope.
- Do the task as asked, in the stated scope. Make routine calls yourself;
  ask only when different readings lead to materially different work. If the
  request looks wrong or a better approach exists — say so in one sentence
  and continue as asked. Do not narrow, widen or reshape the task silently.
- Stop before destructive, production, credential, paid-external and
  scope-expanding actions — do not run them without explicit approval.
- Report skipped, blocked, failing or unverified work plainly.
- Do not claim a check that was not performed.
- If the rtk proxy is installed (`rtk --version` succeeds), prefix high-volume
  read-only commands (git log/diff/status, ls/tree/find, grep, test runs) with
  `rtk`; what never to wrap and recovery — `rules/tool-output-economy.md`.

## Work cycle

- **Quick-fix:** short plan → edit → local check → compact report.
- **Full-cycle:** clarify the goal → gather context → success criteria →
  minimal edit → verification → report.
- **Boundary:** a task is full-cycle when any of these holds — more than
  ~20 changed lines, more than one module, any data-structure/schema
  change, any architectural impact, any non-trivial bug. Risk escalators
  that force full-cycle even for a small edit are listed in
  `rules/subagent-pipeline.md`, stage 1. When in doubt, full-cycle wins.
- **Delegation is the exception, not the default.** Hand a subagent only
  large, genuinely independent, parallelizable work — a wide multi-file
  survey, a separate stream with its own write zone. Do not delegate what you
  would finish yourself in a few tool calls. Do not use subagents to check or
  re-check your own work. One subagent closes the task — launch one, not
  several. Keep the launch count low.

## Rule Index (lazy loading)

Rule bodies live in `rules/` and are read via Read **when they match the
task**. Do **not** preload rules — neither in bulk "for context" nor as a
list at session start. Context starts minimal; a rule is loaded only when it
is relevant to the current task. The same goes for skills (read at
invocation) and agent definitions (read only when delegating).

Rows are grouped by genre, which says *when* a rule is needed (the
description says what it is about): **invariant** — holds for every edit of
that kind of file, read it before writing the first line; **case** — symptom
→ fix, read when the symptom appears; **recipe** — task → procedure, read
when starting that task; **process** — how to run the work itself;
**router** — points at its neighbours.

{{RULE_INDEX}}

Skills resolve to files: `.claude/skills/<skill-name>/SKILL.md` is the
dispatcher (with `docs/` and `tools/` beside it). Subagents have no Skill
tool — when a prompt or agent definition names a skill, read it at that
path; never search for it with shell commands.

## Routing mini-table

A hint for "what to use for which task"; the rule is still loaded via the
Rule Index at the moment it applies, never preloaded.

| Trigger (words) | Rule (`rules/…`) | Role |
| --- | --- | --- |
| script, automation, DryRun/Apply, data migration / скрипт, миграция данных | `script-contract` | developer |
| delegation, subagent, model or effort choice / делегирование, субагент | `subagents-model-routing` | (orchestrator) |
| token economy, expensive orchestrator model / экономия токенов | `orchestrator-economy` | (orchestrator) |
| long command output, compression proxy, rtk / длинный вывод команд | `tool-output-economy` | (any) |
| spec, behavior change, proposal, OpenSpec / спека, предложение | `sdd-integrations` | analytic / architect |
| refactoring, duplicates, dead code / рефакторинг, дубли | {{DOMAIN_ROUTES}} | refactoring |
| check, review, verification / проверка, ревью | `verification-matrix` | code-reviewer |
| tests, regression test, mocking / тесты, регрессия, моки | `test-discipline` | developer / tester |
| work mode, scouting vs edit, emergency fix / режим работы, разведка | `collaboration-modes` | (orchestrator) |
| debugging, bug, error reproduction / отладка, баг | `debugging-loop` | error-fixer |
| session handoff, new session, context limit / передача сессии, хэндофф | `session-handoff` | (orchestrator) |
| requirements interview, decision elicitation / интервью, уточнение требований | `decision-interview` | analytic |
| {{DOMAIN_TRIGGER}} | {{DOMAIN_ROUTES}} | {{DOMAIN_ROLE}} |

Rows carrying the `DOMAIN_ROUTES` placeholder are filled by the domain
overlay when the stack is confirmed (route source — the overlay README's
routing section, or the overlay rules' descriptions). When installing
**without** an overlay the installer replaces that placeholder with `—`
(the row remains a role hint without a bound rule) and removes the
all-placeholder domain row entirely — the verification step requires zero
unfilled placeholders. An overlay that ships its own debugging adaptation
appends it to the debugging row next to `debugging-loop` instead of
replacing it (the adaptation takes precedence for stack tasks).

## Subagents

Role → tier + effort → channel model and effort value — resolved at install
time from the distribution's role registry and channel model map;
model-family behavior blocks are rendered into the agent definitions.

| Role | tier | effort | Channel model |
| --- | --- | --- | --- |
{{AGENTS_TABLE}}

- Delegate bounded independent work (scouting, a separate edit, review);
  decomposition, final decisions and result integration stay with the
  orchestrator. Selection and delegation rules — `subagents-model-routing`.
- Do not trust scouting subagents' reports blindly — spot-check key facts
  against the source of truth.

## MCP

- **Order (routing):** {{MCP_ORDER}}
- **Excluded:** {{DISABLED_MCP}}
- The source of truth is `{{SOURCE_OF_TRUTH}}`; MCP and RAG are navigation,
  confirm facts against the source.

## Output

Result first. List changed files and checks performed. Do not reveal hidden
reasoning — give a compact conclusion, evidence, next step.

## Output discipline

Effort controls how much the agent deliberates, not how much it writes —
length is set here, not by the effort tier.

- Keep answers focused and short. Caveats and disclaimers stay brief; the
  bulk goes to the answer itself. Asked to explain — give the top-level view
  unless a detailed walkthrough was requested.
- Before the first tool call, say in one sentence what you are about to do.
  While working, post a short update only on a real finding or a change of
  direction. On completion lead with the result: the first sentence answers
  "what happened" or "what was found", details come after.
- Match the size of a written document to the task: cover the substance
  without filler, duplicate summaries, or boilerplate. This applies to files
  written to disk — specs, reports, analyses — as much as to chat.
- Correct an earlier statement only when the error changes code, conclusions
  or the user's decisions. State the correction briefly and move on; fix
  small slips that change nothing silently.

<tone_preference>
Answers are reasonably brief.
</tone_preference>
