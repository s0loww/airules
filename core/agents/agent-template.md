# Agent definition template

Channel-neutral template for describing a subagent. Roles, tiers and rights
come from `core/agents/ROLES.md`; model selection and delegation rules —
from `core/rules/subagents-model-routing.md`.

## Frontmatter

```yaml
---
name: <role>
description: "<when to call this agent — triggers for the orchestrator>"
tier: <high|medium|low>     # no model here: resolved via model-map at install
tools: <ro|rw>
allowParallel: true         # optional; see semantics below
---
```

`allowParallel: true` marks roles that are safe to run in several parallel
instances (read-only roles and writers with guaranteed non-overlapping write
scopes). The field is **absent** for roles that normally must not be
parallelized on one codebase (implementers sharing state): absence means
"parallel launches require an explicit orchestrator decision", not a hard
technical ban.

## Body

- **Mission** — one line: what the agent does and what it explicitly does
  not do.
- **Inputs** — what the orchestrator must pass in the prompt: working
  context, task boundaries, done criteria.
- **Boundaries** — what the agent is forbidden to do: leave its write scope,
  make final decisions, change the data sources it relies on.
- **Handoff** — the result format: facts with file:line references, list of
  changed files, open questions. The agent's output is working material for
  the orchestrator, not a final decision.
- **Execution discipline** — standard block appended by the installer when
  rendering every agent (text — `core/channels/adapters.md` §4): do the work
  yourself, do not wait for "background" processes, temporary files in
  `var/tmp/`, stop after the final report.
- **Model profile** — appended by the installer after the discipline block,
  per the family of the resolved model (`core/channels/model-profiles.md`).
  Model-specific behavior lives only there, never in the role body.

## Note

When laying the distribution out for a specific channel the installer
replaces `tier` with that channel's model (via
`core/channels/model-map.yaml`) and expands the pseudo-values
`tools: ro|rw` into the channel's real tool names.
