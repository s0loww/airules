## Codex runtime contract

Read project instructions through `AGENTS.md` and the available file tools.
Rules remain lazy; installed skills are discovered in `.agents/skills/`.
Former project commands are converted to named skills. No tool named `Read`,
`Skill` or `AskUserQuestion` is assumed: use the current client's interfaces.

Custom agents live in `.codex/agents/*.toml`. Explicit model and effort in
their TOML take precedence over launch arguments. Main-flow roles therefore
omit both fields; resolve the requested pair from the installed routing table
and pass it on every supported launch. Fixed-role definitions retain their
configured pair. For a requested override, choose a definition whose fixed
fields do not contradict it. A continued agent retains its launch settings.

Custom agents inherit parent permissions and MCP configuration. A role's
read-only instruction is a behavioral constraint, not an independently
enforced sandbox. Use separately permissioned sessions when hard isolation
is required; never claim a per-role tool allowlist or read-only sandbox was
created by these TOML files. Memory writes remain with the lead agent.

Claude cache settings and model-family prompt blocks are not emitted.
Model mappings are configurable defaults, not measured equivalence or proof
of account availability. Native client policy and explicit user instructions
remain authoritative.

Hooks need review and trust in the actual client. Installing hook files does
not enable trust. After compaction, re-read the named rule bodies, session map
and orchestration state. No hook changes sandbox settings or grants permission.

MCP is optional and project-configured. Use the explicitly selected direct
servers or facade available in the session; a facade is not required. Do not
copy credentials, host configuration or connection state into a distribution.

Portable document, Office and diagram skills describe procedures. Resolve
their engine and tool names against this client's actual capabilities. The
DSH-specific `airules_*` tools are not created in Codex by copying a skill.
Report an unavailable runtime instead of invoking a made-up tool or silently
downloading a replacement. Preserve resource licenses and project paths.

User-owned chats and messages to other chats require explicit authorization.
Use bounded subagents or file handoffs for ordinary independent work. Handoff
notes do not grant new authority. Do not create native goals or schedules
unless the user explicitly requests them.
