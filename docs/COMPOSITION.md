# Composition model

airules is composed along independent axes. A target is not a fork of the
rules, and a recipient profile is not a concrete project configuration.

```text
core
  -> stack overlay
  -> common project layer
  -> recipient profile
  -> concrete project overlay
  -> target renderer
```

## Axes

### Method and stack

`core/` contains the generic method. `overlays/<stack>/` adds reusable stack
knowledge. Neither contains project names, machine paths or credentials.

### Common project layer

`project-layer/common/` is portable project operating policy: project context,
verification contour, lazy rule loading and explicit capability selection. It
is part of a distributable package.

`project-template/` remains the scaffold for values that are filled in the
target project. It is not a second policy layer.

### Recipient profile

`profiles/public` is a neutral hand-off configuration. `profiles/s0lo` extends
it with logical capabilities used in the owner's environment. A profile names
roles such as `project-onemcp`; it does not store an endpoint or credential.

Machine-local bindings live in ignored `profiles.local/`. Concrete project
facts live in the project's own repository or an ignored `projects.local/`.

### Target

`targets/<runtime>/` defines instruction filenames, target syntax, runtime
switches, model behavior and MCP projection. A renderer may transform layout,
but may not weaken or replace the composed project policy silently.

## Standard compositions

Neutral Claude distribution:

```text
stack=1c project_layer=common profile=public target=claude
```

Owner's DSH distribution:

```text
stack=1c project_layer=common profile=s0lo target=dsh-deepseek
```

The latter still needs a concrete project overlay for source roots, allowed
ONEMCP instances, QA contour and commands.

The DSH target also requires selecting the `1С Lite` project preset in the GUI
and creating a new chat. DSH stores this choice outside the project tree, so a
renderer cannot make that step silently.

The target is currently `experimental` with a pending renderer. Its
declarations and policy contract are validated, but it is not promoted to a
ready installation target until a DSH render smoke proves the instruction
budget, MCP projection and native artifact registration.

The current staging renderer already builds `AGENTS.md`, the lazy DSH rule
library and native skills outside the target project. Apply/rollback and MCP
mutation remain deliberately unavailable until their backup and conflict
contracts are covered by an integration smoke.

## Codex target

`stack=1c project_layer=common profile=public target=codex` selects the local
Codex adapter. The neutral profile does not require a facade or other MCP.
The target uses the same source rules, roles and skills as other runtimes;
only native layout, role configuration, hook protocol and runtime contract differ.
The implementation and CLI are documented in `targets/codex/README.md`.

The former separate port is provenance, not a second content owner. Its useful
generic method changes are merged into core; Codex-specific mechanics stay in
the target. Preserve current OpenSpec, hidden-desktop and workflow procedures.
See `docs/CODEX-CORE-MERGE.md` for the selective merge record.

The target is experimental/implemented. Offline assembly and native discovery
do not establish model routing, hook trust, MCP connectivity or 1C acceptance.

## Manifest compatibility

New installations add an optional block to `.airules-manifest.json`:

```json
{
  "composition": {
    "stack": "1c",
    "project_layer": "common",
    "profile": "public",
    "target": "claude"
  }
}
```

An older manifest without `composition` is interpreted as the legacy
`1c/common/public/claude` composition. This keeps existing installations
updatable while the renderers are introduced incrementally.
