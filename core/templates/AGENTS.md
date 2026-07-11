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
- Stop before destructive, production, credential, paid-external and
  scope-expanding actions — do not run them without explicit approval.
- Report skipped, blocked, failing or unverified work plainly.
- Do not claim a check that was not performed.

## Work cycle

- **Quick-fix:** short plan → edit → local check → compact report.
- **Full-cycle:** clarify the goal → gather context → success criteria →
  minimal edit → verification → report. Delegate only bounded independent
  work to subagents.

## Rule Index (lazy loading)

Rule bodies live in `rules/` and are read via Read **when they match the
task**. Do **not** preload rules — neither in bulk "for context" nor as a
list at session start. Context starts minimal; a rule is loaded only when it
is relevant to the current task. The same goes for skills (read at
invocation) and agent definitions (read only when delegating).

{{RULE_INDEX}}

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
| work mode, scouting vs edit, emergency fix / режим работы, разведка | `collaboration-modes` | (orchestrator) |
| debugging, bug, error reproduction / отладка, баг | {{DOMAIN_ROUTES}} | error-fixer |
| {{DOMAIN_TRIGGER}} | {{DOMAIN_ROUTES}} | {{DOMAIN_ROLE}} |

Rows with `{{DOMAIN_ROUTES}}` are filled by the domain overlay when the stack
is confirmed. When installing **without** an overlay the installer replaces
`{{DOMAIN_ROUTES}}` with `—` (the row remains a role hint without a bound
rule) and removes the all-placeholder domain row entirely — the verification
step requires zero unfilled placeholders.

## Subagents

Role → tier → channel model (`core/agents/ROLES.md` +
`core/channels/model-map.yaml`); model-family behavior blocks are rendered
into agent definitions from `core/channels/model-profiles.md`.

| Role | tier | Channel model |
| --- | --- | --- |
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
