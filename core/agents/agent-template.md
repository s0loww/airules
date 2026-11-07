# Agent definition template

Template for describing a subagent. Roles, tiers, efforts and
rights come from `core/agents/ROLES.md`; model selection and delegation rules
— from `core/rules/subagents-model-routing.md`.

## Frontmatter

```yaml
---
name: <role>
description: "<when to call this agent — triggers for the orchestrator>"
tier: <high|medium|low>     # no model here: resolved via model-map at install
effort: <low|medium|high|xhigh>   # resolved the same way; the target defines override precedence
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
  rendering every agent (text — `core/install/layout.md` §4): do the work
  yourself, collect command completion, writing roles keep temporary files
  in their own subfolder of `var/tmp/`, stop after the final report.
  Read-only roles return bounded evidence for the lead to persist. When a memory server is connected
  the block gains one more item: search and read only, writing goes through
  the orchestrator.
- **Model profile** — appended by a matching target after the discipline block,
  per the family of the resolved model (`core/install/model-profiles.md`).
  Model-specific behavior lives only there, never in the role body.

## Note

This frontmatter is the source format. The selected target renders its native
agent format, resolves model and effort through its model map, and explains
how role scope is enforced. Emit native tool allowlists only where supported;
an inherited permission set is not a separate read-only sandbox.
