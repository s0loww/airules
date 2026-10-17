---
description: "Platform traps that make a 1C test lie: unopened form, posting without checks or movements, admin-only runs, stale roles, deploy not applied. Триггеры: тест 1С, тест под ролью, проведение без движений, стенд."
alwaysApply: false
kind: case
---

# Testing 1C: traps that make a verdict lie

The generic list of lying oracles is `test-discipline.md`; the layer model
is `test-model.md`. This file holds the 1C mechanics behind them. Every item
was paid for by a false verdict on a live project.

## Forms

- **A form is verified only by opening it in the client.** A successful
  `/LoadConfigFromFiles`, `ibcmd infobase config apply`, epf/cfe build or
  `/CheckModules` checks neither element properties nor name shadowing. Seen
  live: a реквизит added via `ИзменитьРеквизиты` and referenced by a bare
  name, a local variable shadowing a реквизит формы, an element property
  that does not exist (`ТолькоЧтение` on the wrong element), a динамический
  список with no columns in `Form.xml` — all compiled, all failed on the
  first open. Minimum smoke: open → first command → close.
- A form under test lives in an **extension**, not in an external epf:
  opening it by `e1cib/app/...` is scriptable, and the standard Vanessa
  build cannot open an external epf at all.

## Posting and data checks

- **`Записать(РежимЗаписиДокумента.Проведение)` does not run
  `ОбработкаПроверкиЗаполнения`.** A programmatic test of fill checking calls
  `ПроверитьЗаполнение()` explicitly or goes through the UI. A prohibition
  that must hold for code *and* the operator is enforced in
  `ОбработкаПроведения` too, not only in the fill check.
- **Проведение without an exception proves nothing.** Check the count and
  content of movements in every expected регистр, and that key dimensions
  are filled: a reference whose type is missing from a composite type is
  written as an empty value silently, and a document can post with zero
  movements when a wrong object (a договор instead of an объект расчетов)
  is passed.
- **Read the журнал регистрации for the run's window.** Contour code that
  catches and logs its errors leaves the functional check green; any error
  event in the window fails the run. Errors raised through an external COM
  connection are **not** logged there at all — call such code with an
  explicit catch and return the error.
- **String attributes truncate silently** to their declared length, and
  `Формат(0, "ЧГ=0")` returns an empty string — generated identifiers need
  `"ЧН=0; ЧГ=0"` and a length check against the schema.
- **Session time has one-second precision** (`ТекущаяДатаСеанса`,
  `МоментВремени` of objects created in the same second): tests that order
  by creation time stamp a marker or wait a second.
- **СКД is judged by running it**, never by its query text: the composer
  substitutes period and filter parameters that the text does not show.
  Control data sits exactly on the period boundaries.

## Roles and RLS

- **Run under every target role**, not under the administrator — subscriptions
  on dates of prohibition, RLS and missing read rights are invisible to an
  admin session.
- **Queries in role-scoped tests use `РАЗРЕШЕННЫЕ`.** Without it the query
  fails under RLS, while `ПЕРВЫЕ 1` may still pass — easy to misread as
  "RLS does not work".
- **One role without an RLS condition lifts the restriction entirely** for a
  user who has it. The quantitative check (restricted user sees strictly
  fewer rows than admin) catches this; a spot check does not.
- БСП access-group profiles rewritten by code drop manually added roles —
  re-assert them after every profile rewrite (`access-rights-bsp.md`).

## Caches and sessions

- After writing settings, call `ОбновитьПовторноИспользуемыеЗначения()`
  before the check; otherwise the code reads the cached value.
- **A published endpoint's session keeps the roles and metadata it started
  with.** After changing roles, profiles or metadata, restart the sessions of
  every HTTP bridge / web publication the test goes through, then run the
  preflight below.
- Objects processed before a fix keep their old outcome — test on objects
  created after it.

## Deploy that did not apply

- Exit 0 of a load is not proof. After deploy, probe that the new objects
  and реквизиты exist in the base (metadata query or a reverse dump) and run
  `/CheckModules` for every context the code targets (`-ThinClient
  -WebClient -Server -ExternalConnection`).
- A new file missing from `ConfigDumpInfo.xml` is skipped silently by
  `/LoadConfigFromFiles` — `metadata-xml-workarounds.md` §8.
- `/LoadCfg -Extension` and `/UpdateDBCfg` run as separate calls.

## Encodings — a false red before the test even starts

- The Designer `/Out` log of 8.3.27 is **UTF-8 with BOM**. Read it as
  `utf-8-sig`; read as cp1251, a clean compile parses as `COMPILE_FAIL`.
  Calibrate any log parser on a known-clean log before trusting a verdict.
- `.ps1` files with Cyrillic are saved with BOM for Windows PowerShell 5.1;
  here-strings break otherwise (`com-powershell-1c.md`).
- Cyrillic HTTP bodies go as a UTF-8 file (`curl --data-binary @body.json`),
  never inline from Git Bash: the shell sends cp1251 and the verdict is made
  on mangled input.

## Stand preflight — before interpreting any FAIL

1. The platform build of every local tool equals the stand's build
   (`test-model.md`, "Tool build = target build").
2. The stand's configuration matches the sources: `/CompareCfg` or the
   versions of the host configuration and extensions. Code that reads the
   host's common templates or objects behaves differently on an older host.
3. The test user still has the bridge/publication role, and a request under
   that user answers anything but 401/403.
4. Queues and buffers the scenario depends on are drained.

A FAIL read before the preflight is a hypothesis about the stand, not a
finding about the product.

## Companion rules

| Concern | File |
|---|---|
| Layers, gating vs advisory, environment boundaries | `test-model.md` |
| Lying oracles in general | `test-discipline.md` |
| ibcmd / ibsrv environments | skill `ibcmd-ibsrv` |
| Vanessa scenario pitfalls | `tools/agent-1c/DEPLOYMENT.md` |
| Unit tests | `unit-tests-1c.md` |
