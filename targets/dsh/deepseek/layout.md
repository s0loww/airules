# DSH / DeepSeek target layout

This target adapts the shared distribution to DSH. It owns file layout and
runtime switches, not project policy.

## Root instructions

- Render the shared contract, Rule Index and model-profile block to `AGENTS.md`.
- Render recipient and concrete-project facts to `USER-RULES.md`.
- Leave `LLM-RULES.md` project-owned. DSH `/evolve` is its only automatic
  writer; installation uses skip-if-exists and never replaces accumulated
  evolved rules.
- Keep the combined instruction payload below 65,536 bytes.
- Render rule bodies to `.dsh/rules-1c/` and load them lazily through the
  target-specific paths in the Rule Index.
- Do not mirror the rule library into `.claude/rules/` or `.cursor/rules/`.
- `AGENTS.local.md` is reserved for untracked machine-local additions.

Skills render to the native `.dsh/skills/` provider after DSH-specific
frontmatter conversion. `.dsh/agents-1c/` and `.dsh/commands-1c/` are reference
storage expected by the rules deployment diagnostics; native registration of
roles and commands from those paths is not yet confirmed. The published
upstream rules library does not provide `adapters/dsh.yaml`, so this renderer
is a new adapter and must be validated against the installed DSH build before
claiming upstream deployment compatibility.

## Policy ownership

The rendered airules contract is the policy owner for orchestration, rule
routing and verification. Set `ONEC_RULES_AUTO=off` so the bundled 1C rule
router does not inject a second policy system. Keep
`ONEC_FOREIGN_AGENT_RULES=off` by default so old `.claude/.cursor` rules,
skills and commands are not imported as a second project layer.

Compatibility exception: the current bundle can suppress `AGENTS.md` when a
legacy root `.ai-rules.json` records the exact current file hash as an installed
foreign canon. A renderer must detect that exact condition and stop. Resolve
the legacy ownership first; only as a temporary explicit compatibility choice
may the user enable `ONEC_FOREIGN_AGENT_RULES=on`.

Use the project preset `1С Lite`. It keeps the 1C language tooling without the
Full policy contract. The preset is stored in DSH state, not in the project,
so installation ends with a GUI step and a newly created chat. `1С Full` is a
compatibility mode until every overlapping policy plugin and built-in MCP is
explicitly reconciled.

Harness plugins may remain as transports, tool providers and mechanical
guards. A plugin that owns orchestration, handoff or quality policy must be
disabled or reconciled explicitly before rollout.

## MCP

Render a target-specific allowlist from logical capabilities resolved by the
recipient and project profiles. Do not import every server found in the
project `.mcp.json`: the DSH project MCP loader, including `1С Lite`, treats
enabled entries as active rather than honoring another client's selection.

During merge, allowlisted servers are enabled. Unknown existing entries are
preserved but marked disabled; they are not deleted. Endpoints and credentials
remain in local configuration and are never copied into the distribution.

## Roles and skills

Role definitions and skills require a DSH renderer. Claude frontmatter is not
copied verbatim. Until that renderer is implemented, the root contract and
lazy rule library are supported; role/skill installation is reported as
pending rather than silently emitted in an incompatible format.
