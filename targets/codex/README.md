# Codex target

The canonical distribution now owns the Codex target alongside Claude and DSH.
The separate Codex port supplied the reviewed native formatting and ownership
mechanics; shared rules and skills are read from this repository at build time.

See [layout.md](layout.md) for the CLI, safety boundary and installed artifacts,
[contract.md](contract.md) for runtime semantics and [bindings.example.json](bindings.example.json)
for explicit project inputs. Python 3.11+ and its standard library are required.

The CLI is `python targets/codex/render.py render|verify|plan|apply|rollback`.
`render` takes `--source`, `--project`, `--bindings`, `--output` and optional
`--profile public`. Native skill and hook discovery can be tested separately;
green assembly does not establish hook trust, model routing or live 1C acceptance.

Integration evidence and native discovery results are recorded in
[CODEX-INTEGRATION.md](../../docs/CODEX-INTEGRATION.md). Hook definitions are
installed for review; the installer does not approve or enable their trust.

Root `AGENTS.md` must fit the default 32768-byte instruction budget. Build rejects
oversized contracts rather than claiming the client read silently truncated text.
Project context and testing-contour files are project-owned once installed.
