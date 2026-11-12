# Codex project target

This target reads the current common project layer, selected recipient profile,
canonical `core/` and stack overlay directly. It has no private copy of shared
rules or skills. DSH-only skills do not enter this target.

| Artifact | Installed location |
| --- | --- |
| Instructions and lazy rule index | `AGENTS.md`, `rules/` |
| Shared and stack skills | `.agents/skills/<name>/` with resources and notices |
| Converted project commands | `.agents/skills/<command-id>/SKILL.md` |
| Custom agents | `.codex/agents/<role>.toml` |
| Explicitly selected MCP servers | managed block in `.codex/config.toml` |
| Lifecycle hooks | `.codex/hooks.json`, `.codex/hooks/` |
| Project-owned facts and checks | `.airules/project-context.md`, `.airules/testing-contour.md` |

The default `public` profile requires no facade or memory server. Connections
are selected by bindings and contain environment references, never inline
credentials. Empty MCP bindings do not create or replace `config.toml`.

## CLI

Python 3.11+ and the standard library are sufficient. Run from the distribution:

```sh
python targets/codex/render.py render --source . --project <project> --bindings <reviewed-bindings.json> --profile public --output <fresh-candidate>
python targets/codex/render.py verify --output <fresh-candidate>
python targets/codex/render.py plan --project <project> --candidate <fresh-candidate>
python targets/codex/render.py apply --project <project> --candidate <fresh-candidate> --backup-root <backup-root> --confirm APPLY_CODEX
python targets/codex/render.py rollback --project <project> --backup <receipt-directory> --confirm ROLLBACK_CODEX
```

Render never writes the project. Apply checks the entire plan before writing;
existing unmanaged instructions/roles/skills conflict. Existing project context
and OpenSpec content remain project-owned. A project MCP file may be extended
only with a new, disjoint managed block; unrelated original bytes are preserved.
Updates replace only files whose current hash matches the previous installation.
Removed source files are retained until separately reviewed. A failed write rolls
back the transaction, and explicit rollback refuses to erase later local edits.
Backups preserve overwritten bytes and record newly created paths.

Optional command advisories use the boolean build binding
`"command_advisories": true` (default `false`). The renderer emits shell-event
registrations only after that opt-in and records it in the target manifest.
It ships the scripts/schema/examples for review but never writes the active
`.airules/command-advisories.json` project table. Merge existing project Bash
handlers and review hook trust separately. Configuration, limits and the 1C
deployment advisory are described in
[COMMAND-ADVISORIES](../../docs/COMMAND-ADVISORIES.md).

The manifest records composition, native resource hashes, source revision/dirty
state and the imported port provenance. It is a development snapshot unless
built from an independently verified release tag. Tests prove offline assembly,
native formats and installer behavior, not live model, MCP, hook trust or 1C
acceptance. No project rollout or client configuration change is implicit.

## Provenance

Model mapping, role selection, command-to-skill conversion and conservative
installation ownership reuse the reviewed work in the separate Codex port
(`0.13.0-dev.1`, based on airules `0.12.0` / `05181aa`). Its source is read-only;
the current distribution remains the sole owner of shared content.

Native formats checked against official documentation:

- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://learn.chatgpt.com/docs/build-skills
- https://learn.chatgpt.com/docs/extend/mcp
- https://learn.chatgpt.com/docs/hooks
