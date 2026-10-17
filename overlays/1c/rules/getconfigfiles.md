---
description: "Exporting an object missing from the working copy out of the infobase via Designer `/DumpConfigToFiles`. Триггеры: нет исходников объекта, выгрузить объект из базы, DumpConfigToFiles."
alwaysApply: false
kind: recipe
---

# Exporting Objects from an Infobase to the Repository

## Parameters (defined in `.dev.env` or supplied by the user at task start)

| Placeholder | Purpose |
|---|---|
| `{PLATFORM_PATH}` | Path to the 1C platform installation directory (containing `bin\1cv8.exe`). Example: `C:\Program Files\1cv8\8.3.23.1997` |
| `{INFOBASE_PATH}` | Path to a file infobase or the connection string of a server infobase |
| `{IB_USER}` | Infobase user name |
| `{IB_PASSWORD}` | Password (when required) |
| `{EXPORT_PATH}` | Directory where object sources are exported |
| `{EXTENSION_NAME}` | Extension name when exporting from an extension; otherwise omit the `-Extension` argument |
| `{LOG_PATH}` | Designer log file |
| `{RESULT_PATH}` | `/DumpResult` file — the batch result as a number |

If a value is unknown — **ask the user**, do not guess. Project-stable values go into `.dev.env`.

## Steps

**Step 1.** Compose the list of objects to export in `repoobjects.txt` (one full metadata-object name per line, e.g. `Справочник.Контрагенты`). Build the list via the project's metadata-search tool, or a semantic search over the project profile, confirming against local `src/` (see `tooling-playbooks.md → MCP-first Search`). Concrete tool names per category come from the project's MCP profile (root contract `AGENTS.md`).

Write the list as **UTF-8 with BOM**: without the BOM Designer answers
`Ошибка чтения файла-списка`. Agent write tools produce UTF-8 **without** BOM,
so a generated list must be re-saved before the run
(`io.open(path, 'w', encoding='utf-8-sig')`).

**Step 2.** Run the export through Designer. Objects are exported **in full**, strictly into the specified directory — **do NOT create new subdirectories**.

> This produces the **standard dump layout** (`Documents/<X>/Ext/ObjectModule.bsl`). If the project instead keeps sources unpacked by `v8unpack`, the layout is a different one — singular directory names, `*.obj.bsl` / `*.mgr.bsl` modules, forms as `*.elem.json` — and paths from this recipe will not be found. See `rules/v8unpack-source-structure.md`.

```powershell
$cliArgs = @(
    'DESIGNER',
    '/F', '{INFOBASE_PATH}',
    '/N', '{IB_USER}',
    '/P', '{IB_PASSWORD}',
    '/DisableStartupMessages', '/DisableStartupDialogs',
    '/DumpConfigToFiles', '{EXPORT_PATH}',
    '-listFile', 'repoobjects.txt',
    '-Extension', '{EXTENSION_NAME}',
    '/Out', '{LOG_PATH}',
    '/DumpResult', '{RESULT_PATH}'
)
Remove-Item '{RESULT_PATH}' -ErrorAction SilentlyContinue  # a stale file reads as this run's verdict
$proc = Start-Process -FilePath '{PLATFORM_PATH}\bin\1cv8.exe' `
    -ArgumentList $cliArgs -Wait -PassThru
$proc.ExitCode
```

`/DisableStartupDialogs` belongs next to `/DisableStartupMessages`: without it a
modal dialog hangs the run until someone kills it.

When exporting from the main configuration (not from an extension) — drop the `-Extension {EXTENSION_NAME}` argument.

> **Do not launch it as `& '…\1cv8.exe' …`.** Designer is a GUI application:
> the call returns immediately, `$LASTEXITCODE` stays empty, and the script walks
> on over an empty export directory reporting success. Only `Start-Process -Wait`
> actually waits, and only its `ExitCode` says whether the run failed.

**Step 3.** Take the verdict from **three signals, all of which must agree** —
batch Designer routinely exits with `0` on a failed operation:

| Signal | Pass |
|---|---|
| `ExitCode` of the process | `0` |
| `{RESULT_PATH}` (`/DumpResult`) | holds the number `0`; any other number **or no file** fails |
| `{LOG_PATH}` (`/Out`, UTF-8 with BOM) | no diagnostic lines |

Do not grep the log for `Ошибк*`: the success verdict itself reads
`Ошибок не обнаружено` / `Ошибок: 0`. Neutralize those exact success phrases
first, then treat any remaining `ошибк*` / `предупрежден*` / `не найден метод` /
`error` fragment as a failure. Finally confirm the expected files actually
appeared under `{EXPORT_PATH}` — an empty export with all three signals clean is
still a failed run.

## Limits and pitfalls

- **The list file is read as UTF-8 with BOM only** — otherwise
  `Ошибка чтения файла-списка`. The same error is sometimes **transient** on a
  just-written file (a byte-identical file reads fine a minute later): retry
  once before diagnosing anything else.
- **A list export is not a full export.** With `-listFile` Designer writes the
  listed objects only — no `Configuration.xml` with `<ChildObjects>` and no root
  `Ext/`. Such sources are fine to read, search and edit, but
  `/LoadConfigFromFiles` will not assemble a configuration back from them. When
  the goal is a complete tree, export without `-listFile`.
- **Object inventory without exporting anything** —
  `/DumpConfigToFiles {EXPORT_PATH} -configDumpInfoOnly` writes
  `ConfigDumpInfo.xml` and nothing else (tens of MB on a large configuration);
  the metadata skill exposes the same run as `-Mode UpdateInfo`. Use it to size
  the work or to compare the local tree against `<ChildObjects>`.
