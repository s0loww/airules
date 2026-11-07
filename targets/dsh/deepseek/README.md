# DSH / DeepSeek target

The target currently provides a staging renderer. It builds and verifies a
candidate tree outside the target project; it does not apply files, change MCP
configuration or restart DSH.

```powershell
python targets/dsh/deepseek/render.py render `
  --source <distribution-root> `
  --project <project-root> `
  --profile s0lo `
  --bindings <ignored-project-bindings.json> `
  --output <fresh-staging-directory> `
  --dsh-bundle <dsh-1c-bundle> `
  --skip-mcp `
  --skip-skills
```

The output contains:

- rendered `AGENTS.md` with the DeepSeek profile;
- `.dsh/rules-1c/` with target-relative links;
- `.dsh/skills/` with DSH-native project skills;
- a managed-file manifest;
- a render plan and a secret-free MCP plan;
- `USER-RULES.proposed.md` for review only.

`USER-RULES.md`, `LLM-RULES.md`, `AGENTS.local.md`, `.mcp.json` and `.dev.env`
are never copied or replaced by this staging command. The exact DSH instruction
renderer is used when `--dsh-bundle` is supplied; omission or truncation is a
hard failure.

Rules-only apply and rollback are available, but require an explicit project
name confirmation, a backup root and explicit adoption of an existing unmanaged
`AGENTS.md`. MCP mutation and native agent registration remain pending. Until
the full path is integration-tested, `target.json` stays `experimental/pending`.
Use `--skip-skills` for the first rules-only rollout when a project already has
higher-priority `.agents/skills` with colliding names.

After explicit review, `--accept-skill-collisions` marks those exact
higher-priority directories for backup and removal during `apply`, allowing the
new `.dsh/skills` copies to become active. `--replace-user-rules` stages the
path-rewritten `USER-RULES.md`; without it the renderer emits a proposal only.
