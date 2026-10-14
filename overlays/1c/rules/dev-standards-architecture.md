---
description: "Development standards — architecture patterns, extensions, platform standards, code smells, authoritative query rules. Includes the stability taxonomy of standard-library modules (public region, internal layer, deprecated area, extension points that are implemented rather than invoked) and index alignment: which conditions an index actually serves. Триггеры: где разместить код, стандарты платформы, правила запросов, стабильность API библиотеки, устаревший раздел, точка расширения, индекс не помогает."
alwaysApply: false
kind: invariant
---

# Development Standards — Architecture & Platform

## 1. Architecture Patterns

### Code Placement
- Business logic — **in common modules**, not in form modules
- Common module suffixes follow BSP (`*ВызовСервера`, `*Клиент`, `*КлиентСервер`, `*ПолныеПрава`); layers and their limits — `clean-architecture-1c.md §3`
- Server object modules — mandatory preprocessor: `#Если Сервер Или ТолстыйКлиентОбычноеПриложение Или ВнешнееСоединение Тогда`

### "Result-Structure" Pattern
Return compound results via Structure:

```bsl
Результат = Новый Структура;
Результат.Вставить("ПроверкаПройдена", ПроверкаПройдена);
Результат.Вставить("ТекстОшибки", ТекстОшибки);
Возврат Результат;
```

### "Early Return" Pattern
Reduce nesting by returning early when there is nothing to do. A missing required input is not "nothing to do": it raises or returns a Result-Structure failure, never a default value — a default turns the caller's error into a plausible figure.

```bsl
Если Отказ Тогда
	Возврат;
КонецЕсли;

Если Не ЗначениеЗаполнено(ДатаДействия) Тогда
	ВызватьИсключение НСтр("ru = 'Не задана дата действия.'");
КонецЕсли;
```

### Event Subscriptions
Preferable over modifying typical modules. All subscription methods — via common module `{PREFIX}ПодпискиНаСобытия`.

### New Metadata Objects Placement
Determined by `{NEW_OBJECTS_IN}` parameter from `.dev.env`:

| `{NEW_OBJECTS_IN}` | Behavior |
|---|---|
| `main_configuration` | New objects go into main configuration. Extension — only for event interception |
| `extension` | New objects may be placed in extension. Main configuration not modified without explicit instruction |

Default: `main_configuration`.

### Background Jobs
Operations taking > 10 seconds — move to background jobs with progress indication. Do not block UI.

### Defensive Type Checking
BSL has no strict typing. Check type at function entry when critical:

```bsl
Если ТипЗнч(ДокументыИлиСсылка) <> Тип("Массив") Тогда
	ДокументыКОбработке = Новый Массив;
	ДокументыКОбработке.Добавить(ДокументыИлиСсылка);
Иначе
	ДокументыКОбработке = ДокументыИлиСсылка;
КонецЕсли;
```

### Safe Structure Property Access
Check optional keys with `Свойство(Ключ, Значение)`. A required key (your own Result-Structure, a constructor's output) is accessed directly: if it is missing, the call should fail loudly rather than skip a branch.

```bsl
Если ПараметрыОтчета.Свойство("ДатаНачала", ДатаНачала) Тогда
	// используем ДатуНачала
КонецЕсли;
```

### Collection Normalization
Normalize input to a single collection type for uniform processing. Use `ОбщегоНазначенияКлиентСервер.ЗначениеВМассиве()` for single-to-array conversion.

## 2. Extensions

### Modification Priority
1. **Event subscriptions** (preferred)
2. **Extensions**
3. **Typical code modification** (last resort)

### Extension Directives
- `&Перед` / `&После` — preferred
- `&Вместо` — full replacement or a wrapper of a procedure or function; the original runs only via `ПродолжитьВызов()` (see `extension-patterns.md`)

### Placement Rules (when `{NEW_OBJECTS_IN} = main_configuration`)
- New metadata objects → main configuration
- New attributes of typical objects → main configuration
- Roles → main configuration

Regardless of `{NEW_OBJECTS_IN}`:
- Typical roles → DO NOT modify (create new ones with `{PREFIX}`)

### Forms in Extensions
Visual form editing in extensions — **minimize**. Changes — programmatically through code.

## 3. Platform Standards

### Standard-library API — what is callable

Reusing БСП instead of writing your own is the default (the `1c-metadata-manage`
skill, `ssl-patterns` doc). But not everything exported from a standard module
is public API: **the region a method is declared in is its stability contract**,
and one module holds both the public surface and the internals.

| Region / module shape | Status | In application code |
|---|---|---|
| `#Область ПрограммныйИнтерфейс` | Public API, compatibility maintained across library versions | Call it — this is the intended surface |
| `#Область СлужебныйПрограммныйИнтерфейс`, modules named `*Служебный*` | Internal API between library subsystems, no compatibility guarantee | Do not call — look for a public equivalent |
| `#Область СлужебныеПроцедурыИФункции` | Module-internal | Do not call |
| `#Область УстаревшиеПроцедурыИФункции` | Deprecated, kept for compatibility | Do not use in new code — find the current replacement |
| Modules `*Переопределяемый` / `*КлиентПереопределяемый` | Extension points | **Implement** them, never call them |

`*Переопределяемый` is the trap: its methods do sit in `ПрограммныйИнтерфейс`,
but the library calls them, not you. Calling one from application code compiles
and runs, and is still wrong — you are invoking an extension point instead of
filling it in.

**A plausible method name is not evidence that the method exists.** Names are
easy to derive by analogy and easy to get wrong; a wrong one fails at compile
time, and the failure is trivially avoidable. Before calling an unfamiliar
standard-library method, confirm it in the source — module-structure inspection
or a text search over the common modules — and check which region it sits in
while you are there.

### Async and Modality
- Modal calls are **PROHIBITED**: `Вопрос()`, `Предупреждение()`, `ВвестиЧисло()`, `ВвестиСтроку()`, `ВвестиДату()`, `ВвестиЗначение()`, `ОткрытьЗначение()` and any other synchronous-blocking dialogs.
- Approach depends on `{PLATFORM_VERSION}` from `.dev.env`:

| `{PLATFORM_VERSION}` | Approach |
|---|---|
| < 8.3.18 | `ОписаниеОповещения` (callback) |
| ≥ 8.3.18 | `Асинх` / `Ждать` (preferred) |

- Inside an `Асинх` procedure, use the `*Асинх` variant wherever one exists instead of a callback-based `Показать*` / `Начать*` call. Ordinary synchronous code and server calls are fine there.
- The gate is the configuration's compatibility mode, not the installed platform: a configuration running on 8.3.27 in 8.3.14 compatibility mode cannot use `Асинх`. The same applies to the API check in "Platform Version Compatibility".
- Any dialog calls on the server are **PROHIBITED**.
- **Treatment: `rules/async-methods.md`** — old-to-new method correspondence, what `Ждать` actually returns, ready shapes for a question on form open / close, file workflows and HTTP (8.3.21+). The trap that costs most: **without `Ждать` an exception inside an async call is silently lost**, so a failing operation looks like a successful one.

### Client-Server Interaction
- **`&НаСервереБезКонтекста` is MANDATORY** for all server methods that do not access form data. `&НаСервере` is allowed only when the method directly reads/writes form attributes or elements.
- If a method only needs a form attribute value — pass it as a parameter and use `&НаСервереБезКонтекста`.

### Security
- `Выполнить()` and `Вычислить()` — **PROHIBITED** without extreme necessity.
- No credentials (passwords, tokens, API keys) in code. Store them in the БСП secure storage (`ОбщегоНазначения.ЗаписатьДанныеВБезопасноеХранилище` / `ПрочитатьДанныеИзБезопасногоХранилища`). A constant is not a secret store: read rights on constants are routinely granted to roles.
- **RLS** — design with access restriction requirements in mind.

### Error Handling
- String localization — `НСтр("ru = '...'")` with `СтроковыеФункцииКлиентСервер.ПодставитьПараметрыВСтроку()`.
- Error collection — into a single variable via `Символы.ПС`.
- Logging — `ПодробноеПредставлениеОшибки(ИнформацияОбОшибке())`, NOT `КраткоеПредставлениеОшибки()`.
- An exception handler re-raises (`ВызватьИсключение`). Swallowing an error is allowed only where the contract names the specific error being absorbed: log-and-continue hides a failed operation behind a plausible result. Event-log writes follow `rules/logging-strategy.md` and only when the task asks for logging (`dev-standards-core.md §2`).

### Dates
- On server — `ТекущаяДатаСеанса()` instead of `ТекущаяДата()`. See `rules/platform-solutions.md §6`.

### Queries — Authoritative Rules
- Verify metadata attributes (existence, names, types) **before** writing a query — see `rules/tooling-playbooks.md → MCP-first Search`.
- Look for existing query examples before writing complex queries (`templatesearch`, `search_code`).
- Query text formatting — on a new line at the same indentation level as the variable declaration:

```bsl
Запрос = Новый Запрос;
Запрос.Текст =
"ВЫБРАТЬ
|	Контрагенты.Ссылка КАК Ссылка,
|	Контрагенты.ИНН КАК ИНН
|ИЗ
|	Справочник.Контрагенты КАК Контрагенты";
```

- Always use an intermediate variable for query results. Method chaining is **PROHIBITED**:
  - Correct: `РезультатЗапроса = Запрос.Выполнить();`
  - Incorrect: `Запрос.Выполнить().Выгрузить()` / `Запрос.Выполнить().Выбрать()`.
- Always use `КАК` aliases for query fields (e.g. `Контрагенты.ИНН КАК ИНН`).
- **`РАЗРЕШЕННЫЕ` when the query runs in the user's rights context.** Against real tables (catalogs, documents, registers and their virtual tables) under record-level restrictions, a plain `ВЫБРАТЬ` fails with «Недостаточно прав» for a restricted user — even when the rows they cannot see are irrelevant to the result. `ВЫБРАТЬ РАЗРЕШЕННЫЕ` makes the platform filter those rows out instead of failing. Not a blanket rule: it is pointless under `УстановитьПривилегированныйРежим` and on temporary tables, and it silently narrows the result — so never add it to a query whose completeness is the point (reconciliations, totals, integrity checks) without saying so.
- **Aliases must not be query-language keywords** (runtime error `Ожидается имя`). `Есть`, `Значение`, `Выбор`, `Первые`, `Различные`, `Истина`, `В`, `Между`, `Подобно` and the rest of the vocabulary are unusable as `КАК`-names. The classic is an existence check written as `ВЫБРАТЬ ПЕРВЫЕ 1 ИСТИНА КАК Есть` — select a real field with a plain alias and test `РезультатЗапроса.Пустой()` instead. This class **passes static validation and fails only against a live infobase**, so a new or edited query is confirmed by executing it, not by the linter.
- **Query alias naming — avoid ambiguous names in JOINs** (runtime error: `Неоднозначное поле`):
  - Table/VT alias **must not** match a field alias in the same query (`КАК КОтгрузке` table + `КАК КОтгрузке` field → fail).
  - Prefer distinct names: table `РезервыКОтгрузке`, field `КОтгрузкеОстаток`, output `КОтгрузке`.
  - Avoid language-type names as aliases: `Документ`, `Справочник`, `Регистр` — use `ДокументРегистратор`, `СтрокиДокумента`.
  - For JOINs prefer `ПОМЕСТИТЬ ВТ_*` + `ЛЕВОЕ СОЕДИНЕНИЕ ВТ_*` over inline subqueries in `СОЕДИНЕНИЕ (...)`.
  - See `rules/anti-patterns.md §4` for a concrete bad/good example.
- **Queries inside loops are PROHIBITED.** Use batch queries with temporary tables. See `rules/anti-patterns.md §1` and "Batch Query with Temp Table" template.
- Use `Запрос.УстановитьПараметр()` instead of string concatenation — prevents SQL injection and improves plan caching.
- For complex data retrieval prefer batch queries with temporary tables over multiple separate queries.
- Temporary tables — prefixed with `ВТ_`.
- Choose the join by meaning, not by speed: `ЛЕВОЕ СОЕДИНЕНИЕ` keeps rows that have no match, `ВНУТРЕННЕЕ` drops them. Turning a left join into an inner one silently removes rows from totals (contracts without payments, counterparties without movements); do it only when an unmatched row is impossible or must be excluded, and say which.
- When accessing registers — filter by dimensions first (in virtual table parameters, not in `ГДЕ`). Only dimension conditions move into the parameters: a condition on a resource or attribute inside `СрезПоследних` / `СрезПервых` parameters returns the last record that matches, not the last record — keep such conditions in `ГДЕ`.
- Do not modify register movements directly — only via the posting mechanism.
- `ПЕРВЫЕ N` only where a partial result is the intent (existence check, preview, top-N), and with `УПОРЯДОЧИТЬ ПО` whenever it matters which rows come back (latest, top-N) — without it the platform returns arbitrary N rows, so "the latest rate" becomes any rate. Never on a selection that feeds a calculation, a total or a report: the cut is silent and the figure is wrong.
- Index all fields that participate in filters/joins via metadata.
- **An index is used only when the condition lines up with it.** All the fields of the condition must be in the index, starting from its first field, with no gaps. Given an index `(Организация, Контрагент, Дата)`: a condition on `Организация И Контрагент` uses it; one on `Контрагент И Дата` does not use it at all (the leading field is missing); one on `Организация И Дата` uses only the leading part. This is why "add an index on the field" often changes nothing — the index exists and the condition does not align with it. For temp tables the equivalent is `ИНДЕКСИРОВАТЬ ПО` on the join key.

### Cross-Platform Compatibility
- **COM objects** (`Новый COMОбъект(...)`) are **PROHIBITED** unless explicitly specified in the task.
- For Excel — use spreadsheet document or БСП, not `Excel.Application`.
- File paths — use `/` or platform functions; do not hardcode `\`.

### Platform Version Compatibility
- Before using any platform API method, verify it exists in `{PLATFORM_VERSION}` from `.dev.env`.
- Using methods from newer versions without checking is **PROHIBITED**.

## 4. Data Access — Reference Attribute Access

**Direct dot-notation access on references** (e.g. `Контрагент.ИНН`) loads the entire object from the database. **[Project rule — stricter than ITS standard:** outside trivial single-call handlers, the rule is a hard ban; in simple, non-loop code with one or two attributes ITS allows it, but the project default is to use dedicated БСП methods.**]**

Use these methods instead:

| Method | Purpose | Example |
|--------|---------|---------|
| `ОбщегоНазначения.ЗначениеРеквизитаОбъекта` | Single attribute from one ref | `ОбщегоНазначения.ЗначениеРеквизитаОбъекта(Контрагент, "ИНН")` |
| `ОбщегоНазначения.ЗначенияРеквизитовОбъекта` | Multiple attributes from one ref | `ОбщегоНазначения.ЗначенияРеквизитовОбъекта(Контрагент, "ИНН, Наименование")` |
| `ОбщегоНазначения.ЗначениеРеквизитаОбъектов` | Same attribute from multiple refs | `ОбщегоНазначения.ЗначениеРеквизитаОбъектов(Контрагенты, "ИНН")` |
| `ОбщегоНазначения.ЗначенияРеквизитовОбъектов` | Multiple attributes from multiple refs | `ОбщегоНазначения.ЗначенияРеквизитовОбъектов(Контрагенты, "ИНН, КПП")` |

Their `ВыбратьРазрешенные` parameter has the same effect as `РАЗРЕШЕННЫЕ`: references the user cannot read silently drop out. Do not set it where completeness matters.

### Caching and Batch Retrieval

- Cache repeated reference-attribute lookups via `Соответствие` (Map). Full example — `rules/anti-patterns.md §9 "Missing Caching"`.
- For multiple references prefer batch queries (`ОбщегоНазначения.ЗначенияРеквизитовОбъектов`, or `ВЫБРАТЬ ... ГДЕ Ссылка В (&МассивСсылок)`) over per-reference calls in loops. Temp-table template — `rules/anti-patterns.md → "Batch Query with Temp Table"`.

## 5. Performance Headlines

Mandatory baseline. Detailed anti-pattern catalog with severity — in `rules/anti-patterns.md`. Platform pitfalls (long-running ops, temporary storage, collection search, external components, locks) — in `rules/platform-solutions.md`.

- **Server-side bulk.** Run mass operations on the server; avoid client-server round trips inside loops. Server methods that do not access form data — `&НаСервереБезКонтекста`.
- **Queries.** Never inside loops — use batch queries and temporary tables. `ПЕРВЫЕ N` — by the rule in §3 "Queries". Index every filter/join field in metadata.
- **Privileged mode.** `УстановитьПривилегированныйРежим(Истина)` — only when needed and always paired with `УстановитьПривилегированныйРежим(Ложь)`. Check current state via `ПривилегированныйРежим()`.
- **Caching.** Cache repeated computations — `Соответствие` per call; per session — a common module with return-value reuse (`*ПовтИсп`). Never cache data that can change during the session (rates, balances, settings being edited): a stale cache returns a plausible wrong figure. Reference attributes — via `ОбщегоНазначения.ЗначенияРеквизитов*` with a cache.
- **Collections.** Bulk fill — `ЗаполнитьЗначенияСвойств()`. Search: ≤ ~100 elements — `Найти()` / `НайтиПоЗначению()` is fine; ≥ ~1000 elements or inside a loop — index on `Соответствие` (O(1)) or `ТаблицаЗначений.Индексы.Добавить(...)` + `НайтиСтроки()`. See `rules/platform-solutions.md §7`.
- **Transactions.** Keep them short, no user interaction inside. Account for implicit transactions (e.g. object write).

## 6. Code Smells

Smells are about **shape**, and are judged over a module or a subsystem.
Concrete constructs that are wrong on sight — a query inside a loop, dot
notation on a reference — are a different thing and live in `anti-patterns.md`.

| Smell | Signs | Fix |
|---|---|---|
| **Big Ball of Mud** | No discernible structure; everything depends on everything | Introduce boundaries — `clean-architecture-1c.md`, `ddd-1c.md` |
| **God Module** | One module does everything; hundreds of procedures | Split by responsibility; one reason to change per module |
| **Tight Coupling** | Modules reach into each other's implementation details; a change cascades | Talk through the public region of the owning module (`ПрограммныйИнтерфейс`) |
| **Copy-Paste Architecture** | The same logic in several places, no shared module | Extract into a common module — but only once the third copy appears; approach in `refactor-add.md` |
| **Premature Optimization** | Caching and complexity built before any measurement | Remove until a measurement asks for it back |
| **Data Clumps** | Same 3+ parameters passed together in multiple methods | Combine into Structure via constructor function |
| **Primitive Obsession** | Strings instead of enums, numeric codes instead of references | Use `Enum`, `CatalogRef`, `DefinedType` |
| **Divergent Change** | One module constantly changed for different reasons | Split module: each handles one responsibility (SRP) |
| **Shotgun Surgery** | One business logic change requires edits in 5+ places | Consolidate related logic into one common module |
| **Feature Envy** | Form module method heavily works with data of another object | Move method to the common module of that object |
| **Variable Reuse** | One variable stores different values at different stages | Create separate variable for each value |
