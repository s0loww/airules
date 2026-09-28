# The wrapper — `tools/_common/Invoke-1CEdit.ps1`

Every tool of this skill that writes — to the configuration dump, to an
infobase, to a web server — runs through one wrapper. It carries the airules
script contract (`rules/script-contract.md`): **DryRun by default, `-Apply` to
write**, the password from an environment variable, honest exit codes.

## Why a wrapper

The tools under `tools/` are vendored from upstream (Nikolay Shirokov's
cc-1c-skills, via comol/ai_rules_1c) nearly verbatim; `form-compile.ps1` alone is
over 350 KB. Patching a DryRun mode into thirty-odd writers would be lost on the
next sync. Instead each writer carries a five-line gate that refuses to run
unless the wrapper launched it (exit `3` and the command to use), and the
contract lives here. `ci/sync_metadata_manage.py` in the airules repository
re-inserts the gates on every sync and fails on an upstream tool nobody has
classified.

## Invocation

```powershell
powershell.exe -NoProfile -File skills/1c-metadata-manage/tools/_common/Invoke-1CEdit.ps1 `
    -Tool <name> [-Object <address>] [-Root <dump>] [-Apply] [-PasswordEnv <VAR>] [-Scope <paths>] `
    <tool parameters...>
```

| Parameter | Meaning |
|---|---|
| `-Tool` | Script name without `.ps1`: `meta-edit`, `form-add`, `db-update`. The two scaffold scripts are `epf-scaffold/init` and `erf-scaffold/init`. |
| `-Object` | Logical address, resolved to the tool's path parameter (grammar below). Works for read-only tools too. Tools that take `-Object` themselves (`meta-remove`, `cfe-borrow`) get it passed through unchanged. |
| `-Root` | Dump root for `-Object`. Default: `EXPORT_PATH` from `.dev.env`, else the nearest folder holding `Configuration.xml`. |
| `-Apply` | Write for real. Without it nothing is left changed. |
| `-PasswordEnv` | Name of the environment variable with the infobase password; handed to the tool as `-Password`. A literal `-Password` is refused (exit 2). |
| `-Scope` | Extra paths to snapshot when the dump is not under git. |
| everything else | Passed to the tool by name. |

## What DryRun means per tool kind

| Kind | Tools | Without `-Apply` | With `-Apply` |
|---|---|---|---|
| File writers | `meta-edit`, `meta-compile`, `form-*`, `skd-compile`/`-edit`, `role-compile`, `mxl-compile`, `cf-edit`/`-init`, `cfe-*`, `subsystem-*`, `interface-edit`, `add-template`, `add-help`, `xdto-compile`/`-edit`, `support-edit`, `uuid-check -Fix`, scaffolds | the tool **runs**, the diff of everything it changed is printed, the tree is restored | the tool runs; newly changed paths are listed |
| Own `-DryRun` | `meta-remove`, `remove-form`, `remove-template`, `db-load-git`, `web-unpublish` | the tool's `-DryRun` — its own plan, nothing written | runs; `-Force` is added only where it merely confirms the plan (`remove-form`, `remove-template`, `web-unpublish`). For `meta-remove`, `-Force` means *remove despite references* — pass it yourself, deliberately. |
| Platform / server | `db-*`, `epf-build`, `epf-dump`, `stub-db-create`, `install-files-update`, `web-publish`, `web-stop` | the planned call is printed (password masked) | runs |
| Read-only | `*-info`, `*-validate`, decompilers, `dump-validate`, `web-info` | run as they are | — |

### How a file-writer DryRun restores the tree

- **Under git** (the usual case): `git status` of the whole repository is taken
  before and after the run, so a write anywhere in the repository is seen, not
  only near the target. Files that were already modified or untracked — work in
  progress — are saved by content first and put back byte for byte; files that
  were clean go back with `git checkout`, new files are deleted. The restore is
  verified; if it is incomplete the run exits `2` and names the folder holding
  the saved copies. More than 3000 already-dirty files: DryRun is refused —
  commit or stash first. Files matched by `.gitignore` are invisible to this.
- **Outside git**: a content snapshot of the target's scope (the object file,
  its folder, `Configuration.xml`, plus `-Scope`) is taken and restored. Writes
  outside that scope are not seen — the output says so.

A DryRun is a preview, not a verification: validators (`meta-validate`,
`form-validate`, …) still run as the tools run them, and a diff that looks right
proves nothing about the platform accepting the result.

## Logical addresses (`-Object`)

```
<Kind>.<Name>                        -> Catalogs\Контрагенты.xml
<Kind>.<Name>.Форма.<FormName>       -> …\Forms\<FormName>\Ext\Form.xml
<Kind>.<Name>.Макет.<TemplateName>   -> …\Templates\<TemplateName>\Ext\Template.xml
<Kind>.<Name>.Права                  -> …\Ext\Rights.xml
<Kind>.<Name>.МодульОбъекта          -> …\Ext\ObjectModule.bsl
<Kind>.<Name>.МодульМенеджера        -> …\Ext\ManagerModule.bsl
<Kind>.<Name>.МодульНабораЗаписей    -> …\Ext\RecordSetModule.bsl
```

Kind names and member keywords are accepted in Russian and English
(`Справочник` or `Catalog`, `Форма` or `Form`); the table is
`tools/_common/MetadataAddress.ps1` (upstream). An address it cannot resolve is
an error, never a guess. `Роль.ПолныеПрава.Права` is the handy one for
`role-info` / `role-validate`.

## Exit codes

| Code | Meaning |
|---|---|
| the tool's own | the tool's result — a DryRun of a failing tool fails too |
| `2` | wrapper refusal: literal password, unknown tool, restore incomplete, DryRun scope too large |
| `3` | a writing script was called directly, not through the wrapper |
