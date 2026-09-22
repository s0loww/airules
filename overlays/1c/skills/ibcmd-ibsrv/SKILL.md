---
name: ibcmd-ibsrv
description: "Build, update and serve local 1C test infobases without Designer: ibcmd for create / import / apply / extensions / dump-restore / sessions, ibsrv as a stand-alone server that serves the web client and HTTP services of a base on a local port; headless runs through /C launch parameters; the boundary with bases under a server cluster. Load when setting up or repairing a local test base, when Designer loads hang, before UI testing in a browser, or when the agent needs a data channel into a base. Триггеры: ibcmd, ibsrv, автономный сервер, тестовая база без конфигуратора, веб-клиент локально, эксклюзивная блокировка, ServerData, прогон без интерфейса, RUN_, .dt."
---

# ibcmd and ibsrv

`ibcmd` administers an infobase without Designer and without a window.
`ibsrv` is a stand-alone server: it serves one base's web client and HTTP
services on a port, with no web server and no cluster. Both ship with the
platform's **server component**; a client-only install has neither
(`<platform>\bin\ibcmd.exe` is the test). Minimum 8.3.25.

## Where they may point — decide first

| Target | ibcmd / ibsrv allowed? |
| --- | --- |
| Local file base built from the sources | yes — the normal case |
| Local DBMS base of your own (`--dbms --db-server --db-name`) | yes |
| A copy of a stand, restored locally from `.dt` | yes, with the stand's platform build |
| A base served by a server cluster (team dev, test contour, prod) | **no** — only through the cluster: normal client, a published endpoint, the regular deploy |

Attaching `ibcmd`/`ibsrv` directly to the DBMS of a cluster base bypasses
the cluster's managed locks, configuration cache, sessions and licenses; a
tool build newer than the cluster may even try to convert the storage
format, after which the cluster cannot open the base. `test-model.md`,
"Environment boundaries".

**Build pinning.** Several platform builds coexist under
`<ProgramFiles>\1cv8\<build>\bin`. For a copy of a stand use the stand's
exact build (in a server base the client's "About" window shows it — the
starter always picks the build matching the cluster). A script picks the
build from the project profile or an explicit env variable, and falls back
to "newest with `ibcmd.exe`" only for purely local bases.

## Layout per base

```
build/<Base>/            the base (1Cv8.1CD)
build/<Base>_ServerData/ stand-alone server state — sessions, temp, logs
```

- Pass `--data=<Base>_ServerData` to **every** `ibcmd`/`ibsrv` call. The
  default data dir under the user profile is shared by all tools, and their
  locks collide.
- The base lives **outside** its data dir, so the data dir can be wiped
  without touching the base.

## Recipes

```powershell
$ib = @("--db-path=$Db", "--data=$Data")
ibcmd infobase create @ib
ibcmd infobase config import @ib $SrcDir            # full dump in XML
ibcmd infobase config import files @ib --base-dir=$SrcDir --partial <files>   # changed objects only
ibcmd infobase config apply  @ib --force
ibcmd infobase config import @ib --extension=$Ext $ExtDir
ibcmd infobase config apply  @ib --extension=$Ext --force
ibcmd infobase config extension update @ib --name=$Ext --safe-mode=no --unsafe-action-protection=no
ibcmd infobase config check  @ib                    # consistency of the loaded config
ibcmd infobase config export @ib $OutDir            # reverse dump — proves what was applied
ibcmd infobase dump    @ib $File.dt
ibcmd infobase restore @ib $File.dt
ibcmd eventlog export <Base>\1Cv8Log --format=json  # журнал регистрации as JSON
```

- An extension that changes shared data structures (adopting an enum,
  a register) needs `extension update --scope=infobase` before its apply.
- Full import + apply of a mid-size configuration takes tens of seconds;
  an extension, seconds.
- Exit code is the verdict, stdout/stderr the evidence — redirect both to a
  per-run log file, never interpret from memory.

## Running ibcmd from a script

- **Timeout on every call.** A wedged `ibcmd` (a ghost lock in a data dir
  left by an unclean shutdown) blocks forever at 0% CPU. Start without
  waiting, poll with a ceiling, kill and throw on expiry.
- In Windows PowerShell 5.1, touch `$proc.Handle` right after
  `Start-Process -PassThru` without `-Wait`; otherwise `.ExitCode` comes back
  `$null` and every success reads as failure.
- **Recovery ladder for "failed to get exclusive lock"**, in order:
  1. close sessions of the running server gracefully:
     `ibcmd --pid=<ibsrv pid> session list` → `session terminate --session=<uuid>`,
     then stop that `ibsrv`;
  2. `config apply --session-terminate=force`;
  3. wipe the base's data dir (state only, never the base) and retry;
  4. recreate the base — only if it is declared disposable.

## Serving with ibsrv

```powershell
ibsrv --db-path=$Db --data=$Data --address=127.0.0.1 --port=$Port
```

- Web client: `http://127.0.0.1:<port>/`; deep link **only with `#`**:
  `http://127.0.0.1:<port>/ru_RU/#e1cib/data/<FullName>?ref=<ref>` or
  `#e1cib/app/<FullName>` for a form.
- HTTP services: `http://127.0.0.1:<port>/hs/<rootUrl>/<path>` — no
  publication-name segment. A 503 whose body mentions `sessionId` means
  "no such route" (wrong port or base), not a crash.
- Readiness: poll the root URL for 200/302 — the server accepts
  connections a few seconds after start. Check the process has not exited
  immediately (port in use).
- Keep stdin detached (Windows: `Start-Process -WindowStyle Hidden`) or held
  open (POSIX: `tail -f /dev/null | ibsrv ...`); a wrapper that dies with a
  closed stdin takes `ibsrv` with it.
- Stop gracefully: terminate sessions through `ibcmd --pid`, then stop the
  process you started — only that PID.
- `--debug=http` exposes the HTTP debug server of that base.

**While `ibsrv` serves a file base, nothing else opens it**: `1cv8
ENTERPRISE`, `ibcmd` offline commands and unit runs fail with a shared
access error. Serialize: stop the server → update/seed → start it again.
Under many sessions `ibsrv` may start answering "License not found" —
restart it.

## Headless runs through `/C`

One mechanism covers unit tests, seeding and provisioning without COM and
without a window: a test extension handles the launch parameter in
`ПередНачаломРаботыСистемы`, does its work, writes a JSON/JUnit result file,
sets `Отказ = Истина` and calls `ЗавершитьРаботуСистемы(Ложь)`.

```powershell
1cv8 ENTERPRISE /F "$Db" /C "RUN_<ACTION>;<args>;<outFile>" `
  /DisableStartupMessages /DisableStartupDialogs /DisableSafeMode /DisableUnsafeActionProtection /Out "$Log"
```

- Grammar: `RUN_<ACTION>;<arg>;...;<outFile>` — one handler per action,
  first match cancels startup. Several handlers in one extension are tried
  in order.
- No result file = the run failed before the handler: export the журнал
  регистрации and filter by the handler's event name.
- `ibcmd` changes metadata, not data — setting a constant or seeding goes
  through such a handler (or through the HTTP bridge below).
- Each call costs a full session start (~10–15 s). For long interactive
  loops use a bridge instead.

## HTTP bridge — a data channel into a served base

A test-only extension with an HTTP service, served by `ibsrv` (local) or by
the stand's publication (remote), replaces COM checks and session-restart
loops. Requirements, all learned from failures:

- `GET /health` without auth; everything else behind a bearer token **and**
  a gate constant that is off by default. Never shipped to production.
- `POST /query` returns `{columns, rows}` **or** an explicit `error` field —
  never an empty result in place of an error.
- Arrange, act and assert of one scenario can run in one call.
- The publication can run under a restricted user, so role-scoped checks go
  through the same channel.
- After roles, profiles or metadata change, the bridge's sessions are
  restarted — they keep the rights they started with.
- JSON is read and written as explicit UTF-8 (PowerShell
  `[IO.File]::ReadAllText(path, [Text.Encoding]::UTF8)`), request bodies go
  as files.

## Browser against the served web client

- Driving the web client needs a browser tool that clicks, types and takes
  screenshots; a text-only pane can read a form but not operate it.
- Controls come without accessible names — click by screenshot
  coordinates; the DOM holds every open window at once, so a read subtree
  may belong to another form.
- **Synthetic input may not commit a field value** — `ПриИзменении` does not
  fire. A flow that depends on it is verified by a scenario runner or by
  hand, and the report says so.
- File pickers cannot be filled by automation.
- Screenshots can stall after a server round trip: wait 5–10 s → Escape or
  Tab → read the page as text → last resort, a fresh tab.
- Heavy UI sessions go to a separate subagent so screenshots do not flood
  the orchestrator's context.
