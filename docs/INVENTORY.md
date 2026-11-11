# Состав дистрибутива

Codex использует ту же canonical библиотеку. Его нативная раскладка, конвертация
команд в навыки и проверка discovery описаны в [CODEX-INTEGRATION.md](CODEX-INTEGRATION.md).
Генерируемые ниже блоки продолжают отражать стандартную Claude-симуляцию.

Что лежит в airules и что из него появляется в целевом проекте. Числа сняты
прогоном `ci/simulate_install.py` со стеком `1c` — это фактический результат
установки, а не пересказ инструкции.

Числа и перечни в блоках `<!-- generated:… -->` собираются скриптом — править
их руками бессмысленно, они перезапишутся:

```sh
python ci/simulate_install.py --emit-inventory
```

Проза между блоками пишется руками и генератором не трогается. Расхождение
блоков со сборкой роняет `check_layers`, поэтому протухнуть молча файл не может.

<!-- generated:stats -->
| | |
|---|---|
| версия | 0.16.0 |
| правил | 55 |
| скиллов | 51 |
| ролей субагентов | 13 |
| команд | 4 |
| гейтов | 4 |
| файлов в цели | 441 |
<!-- /generated:stats -->

## Что появляется в целевом проекте

```
AGENTS.md                корневой контракт: роли, MCP-профиль, Rule Index (он же роутинг)
CLAUDE.md                ровно одна строка: See @AGENTS.md
rules/                   тела правил, читаются по требованию
.airules/                общий project layer: контекст и тестовый контур
openspec/                паспорт проекта и воркспейс спецификаций
tools/                   библиотеки оверлея (agent-1c, com-tools)
.mcp.json                серверы MCP; remote — обязательно с "type": "http"
.claude/
  agents/                определения субагентов
  skills/                скиллы со своими ресурсами
  commands/              команды
  hooks/                 rule-inject.py + карта путей
  settings.json          регистрация хука: PreToolUse и SessionStart
.airules-manifest.json   sha256 каждого файла — на нём стоит безопасное обновление
```

<!-- generated:tree-counts -->
| Каталог | Файлов |
|---|---|
| `rules/` | 55 |
| `.airules/` | 2 |
| `openspec/` | 5 |
| `tools/` | 53 |
| `.claude/agents/` | 13 |
| `.claude/skills/` | 302 |
| `.claude/commands/` | 4 |
<!-- /generated:tree-counts -->

Каталога `.claude/rules/` в раскладке **нет намеренно**: Claude Code грузит его
целиком в каждый промпт, что убило бы ленивую загрузку, ради которой построена
вся структура. Тела правил лежат только в корневом `rules/`.

## Правила

Жанр (`kind`) решает канал доставки. Инварианты нужны в момент написания строки
и опознаются по пути файла, поэтому их можно привязать к маскам хука. Остальные
жанры живут на ленивом индексе и подтягиваются по описанию.

<!-- generated:genres -->
| Жанр | Всего | Что это |
|---|---|---|
| `invariant` | 21 | что всегда верно про код такого вида; привязано к файлу |
| `case` | 2 | симптом → фикс |
| `recipe` | 8 | задача → процедура |
| `process` | 23 | как вести работу: делегирование, память, верификация |
| `router` | 1 | навигация к соседним правилам |
<!-- /generated:genres -->

<!-- generated:rules-core -->
**Ядро** (23): `autonomous-run`, `autonomous-run-templates`, `case-book`, `collaboration-modes`, `context-packs`, `debugging-loop`, `decision-interview`, `decisions-log`, `intent-testing`, `orchestrator-economy`, `outbound-messages`, `preflight-worktree`, `script-contract`, `sdd-integrations`, `session-handoff`, `session-map`, `subagent-pipeline`, `subagent-task-templates`, `subagents-model-routing`, `test-discipline`, `test-model`, `tool-output-economy`, `verification-matrix`.
<!-- /generated:rules-core -->

<!-- generated:rules-overlay -->
**Оверлей 1c** (32): `access-rights-bsp`, `anti-patterns`, `async-methods`, `clean-architecture-1c`, `com-powershell-1c`, `dcs-composition-recipes`, `dcs-design`, `ddd-1c`, `dev-standards-architecture`, `dev-standards-core`, `dev-standards-forms`, `extension-patterns`, `form-module`, `form-reserved-names`, `forms`, `forms-add`, `forms-events-add`, `getconfigfiles`, `integrations-add`, `kd2-exchange-rules`, `kd31-exchange-rules`, `locks-and-transactions`, `logging-strategy`, `metadata-xml-workarounds`, `platform-solutions`, `refactor-add`, `registers-design`, `systematic-debugging`, `testing-1c`, `tooling-playbooks`, `unit-tests-1c`, `v8unpack-source-structure`.
<!-- /generated:rules-overlay -->

<!-- generated:hook-coverage -->
Из 19 инвариантов оверлея **13 заведены в карту хука** и приезжают по пути файла. Остальные 6 по пути не опознаются: `async-methods`, `ddd-1c`, `extension-patterns`, `kd2-exchange-rules`, `kd31-exchange-rules`, `logging-strategy`.
<!-- /generated:hook-coverage -->

## Хуки

Единственный исполняемый механизм дистрибутива. Правило, прочитанное через
Read, живёт в истории и первым уходит при сжатии контекста, а в summary
остаётся строка «правило прочитано» — модель считает вопрос закрытым и не
перечитывает. Хук не история, а реакция на действие.

| Точка | Что делает |
|---|---|
| `PreToolUse` / `Edit\|Write` | сверяет путь правки с картой и называет привязанные правила — путь и строку инварианта, не тело |
| `SessionStart` / `compact` | после сжатия говорит прямо: тела выгружены, строка в summary — не правило |
| `SessionStart` / `startup\|clear` | на свежем контексте перечисляет незавершённые `var/tmp/handoff-*.md` и велит спросить пользователя; сам не подхватывает, без документов молчит |
| `--check-map` | офлайн-сверка карты с установленными правилами при установке |
| `--dry-run` | офлайн: что впрыснется на конкретном пути |
| `.githooks/pre-commit` | гейт чистоты слоёв, контрибьюторам; в цель не ставится |

**Регистрация — не запуск.** Хук не блокирует правку никогда: любая ошибка —
выход с нулём и без вывода. Обратная сторона в том, что молчание неотличимо от
незапуска, поэтому живость точки проверяется зондом с собственным логом.
Замерено: в проекте, где каталога `.claude` не было, десктоп подхватывает
новую регистрацию только после перезапуска клиента.

## Память и фиксация находок

| Что записывается | Чем регулируется | Форма |
|---|---|---|
| решение — стабильное, неочевидное, с реальным разменом | `decisions-log` | Decision · Reason · Scope · Verification |
| отказ, который ударит по другому так же | `case-book` | Problem · Symptom · Fix · Reference |
| тупик — подход испробован и брошен | `case-book` | Dead end · Why · Instead · Do not retry unless |
| ложный дефект — код выглядит ошибкой и ею не является | `case-book` | Fact · Why · Do not · Source |
| разбор бага — подтверждённая гипотеза | `debugging-loop` §6 | в описании коммита |
| передача между сессиями | `session-handoff` | handoff-документ |

Три правила, которые нарушают чаще всего:

- **порог решения — три условия сразу**: необратимо, удивительно без контекста,
  был реальный размен;
- **в сам файл правила дописывать нельзя** — установленная копия под манифестом
  и заменяется при обновлении;
- **сила источника** помечается на каждой записи: «со слов автора» против
  «выведено из кода». Без пометки записи считаются одинаково достоверными, и
  реконструкция выигрывает спор у того, кто знал замысел.

Адрес записи выбирается один раз и фиксируется в корневом контракте: инциденты
проекта — на сервер памяти, если он подключён; то, что едет в другие проекты, —
в git, потому что блоб не поревьюить. Запись в оба места даёт две
половинчатые копии.

## Скиллы и команды

<!-- generated:skills -->
| Скилл | Слой | Что делает |
|---|---|---|
| `api-conventions` | core | Design or review a REST endpoint's resource contract, validation, compatibility and failure sema |
| `archify` | core | Create validated architecture, workflow, sequence, data-flow and lifecycle diagrams as standalon |
| `architecture-evolution` | core | Assess a design or substantial change for compatibility, migration and preservation of existing  |
| `caveman` | core | Use a concise lite reply style when the user explicitly requests caveman, terse replies, or shor |
| `craft-mermaid` | core | Render Mermaid source into a portable Craft-style PNG and inspect its readability |
| `document-import` | core | Read and search local PDF, DOCX, XLSX or PPTX reference documents with bounded extraction and so |
| `handoff` | core | Write or receive a compact transfer of an active task between sessions, with current artifacts a |
| `memory-workspace` | core | Search project memory, preserve an established finding, or inspect memory documents and their gr |
| `mermaid-diagrams` | core | Practical guide for creating human-readable and agent-parseable diagrams using Mermaid inside Ma |
| `office` | core | Create or edit local Office documents, spreadsheets and presentations with verified output |
| `office-docx` | core | Create, inspect and edit Word DOCX files with structure and visual validation |
| `office-export-pdf` | core | Export local Office documents to PDF and inspect the exported result |
| `office-pptx` | core | Create or edit PPTX slide decks with visual checks |
| `office-recalculate` | core | Recalculate workbook formulas with a local calculation engine and verify cached values |
| `office-render` | core | Render local Office or PDF files into preview images and inspect layout |
| `office-xlsx` | core | Create, edit and validate XLSX spreadsheets and formula results |
| `openspec-apply-change` | core | Implement tasks from an OpenSpec change |
| `openspec-archive-change` | core | Archive a completed change in the experimental workflow |
| `openspec-explore` | core | Enter explore mode - a thinking partner for exploring ideas, investigating problems, and clarify |
| `openspec-propose` | core | Propose a new change with all artifacts generated in one step |
| `openspec-sync` | core | Merge a selected OpenSpec change's delta specs into main specs while keeping the change active a |
| `openspec-update` | core | Revise an existing OpenSpec change's planning artifacts after a scope or design decision, withou |
| `powershell-windows` | core | Windows environment: PowerShell scripting rules for both Windows PowerShell 5.1 and PowerShell 7 |
| `security-baseline` | core | Review changed trust boundaries or security-sensitive behavior using concrete source-to-sink evi |
| `skill-maintainer` | core | Create or narrowly improve a task skill from a demonstrated reusable method or a concrete failur |
| `technical-debt` | core | Assess existing architectural debt and prioritize its actual maintenance cost and exit condition |
| `1c-ai-merge` | 1c | Plan a supplier update with local customizations, classify three-way changes and separate an ext |
| `1c-business-tests` | 1c | Create or maintain repeatable tests of 1C calculations, data and business behavior using the pro |
| `1c-code-search` | 1c | Locate a BSL routine, behaviour, literal or module structure in the correct 1C source contour |
| `1c-config-docs` | 1c | - |
| `1c-debug-runtime` | 1c | Investigate a runtime 1C fault with discriminating hypotheses, owned probes and source/target-bo |
| `1c-element` | 1c | Recognize a 1C:Элемент/XBSL project or subtree and choose its actual text, build and verificatio |
| `1c-event-journal` | 1c | Inspect relevant entries in the 1C Журнал регистрации with a bounded time/target scope |
| `1c-form-inspect` | 1c | Inspect a managed 1C form's elements, data bindings, commands and handlers before changing it |
| `1c-form-shot` | 1c | Capture an identified 1C form through an already supported browser, EDT, QA or desktop surface |
| `1c-impact` | 1c | Assess callers, metadata dependencies and downstream consequences of a proposed 1C change |
| `1c-mechanism-map` | 1c | Explain a 1C mechanism as an evidence-linked map of entry points, handlers, subscriptions and da |
| `1c-meta-info` | 1c | Read a 1C object's type, attributes, tabular parts, forms and ownership before reasoning about i |
| `1c-metadata-manage` | 1c | Create, edit, validate and remove 1C metadata — objects, managed forms, SKD, MXL, roles, EPF/ERF |
| `1c-platform-help` | 1c | Resolve a 1C platform or БСП API, format or standard against version-relevant primary documentat |
| `1c-qa-testing` | 1c | Verify a thin-client 1C scenario through the project's available QA interface with observe–act–a |
| `1c-repository-manage` | 1c | Inspect or change a 1C configuration repository through explicit object-scoped operations; disti |
| `1c-templates-memory` | 1c | Find and adapt an existing 1C solution pattern while keeping project decisions and reusable temp |
| `1c-tj-analysis` | 1c | Analyse a 1C technological log (ТЖ): what the log actually recorded, the slowest server calls an |
| `1c-ui-regression` | 1c | Create or maintain saved, repeatable 1C UI regression scenarios using the project's configured w |
| `1c-verify-project` | 1c | Create or maintain a project-local 1C verification recipe that maps features to real entry point |
| `ibcmd-ibsrv` | 1c | Build, update and serve local 1C test infobases without Designer: ibcmd for create / import / ap |
| `img-grid-analysis` | 1c | Overlay a numbered grid on an image to determine column proportions for layout generation |
| `mcp-1c-tools` | 1c | Discover the actually exposed 1C capabilities and their schemas without assuming a facade or don |
| `onec-check-mcp` | 1c | Diagnose missing or failing project MCP capabilities while separating discovery, transport and s |
| `v8unpack-cf` | 1c | Inspect or transform a 1C binary artifact using a confirmed codec, separating ordinary Form.bin  |
<!-- /generated:skills -->

Команды: `techdebt-capture`, `todolist` (ядро), `deploy-and-test` (оверлей).
Библиотеки оверлея: `tools/agent-1c/` (тулчейн), `tools/com-tools/` (COM-обёртки).
Путь `tools/<библиотека>/` **нормативный** — правила ссылаются на него буквально.

## Опциональные контуры

**OpenSpec** — правило `sdd-integrations` плюс четыре скилла `openspec-*` плюс
скаффолд `openspec/` в корень (skip-if-exists: существующие specs и changes не
перезаписываются). CLI нужен только скиллам.

**Сервер памяти** — спрашивается в интервью тремя вариантами: подключить
существующий, развернуть свой, не использовать. Третий полноценный: остаётся
файловая память Claude Code, ни одно правило не перестаёт действовать.
Граница слоёв задаётся до подключения: конституция (правила, договорённости,
топология) — в markdown под git, операционный поток (инциденты, находки, TODO) —
на сервер. Подключение проверяется рукопожатием MCP, а не пингом; конфиг
проектный, не глобальный. Подробности — `ONBOARD.md` §4.3.

## Софт

Установка внешнего софта не требует. Обязательны только Git и Claude Code;
Python 3.9+ — контрибьюторам, для гейтов.

Опционально по правилам ядра: OpenSpec CLI, rtk (сжатие вывода команд),
ripgrep (для фильтров rtk).

Оверлей 1c: платформа 1С:Предприятие 8.3, BSL Language Server, OneScript с opm,
vanessa-runner, Vanessa Automation, Apache HTTP Server. Версии пинятся в
`overlays/1c/tools/agent-1c/toolchain.lock.json`; в `SOFTWARE.md` — только
адреса проектов.

## Чем это проверяется

| Проверка | Что ловит | Объём |
|---|---|---|
| `ci/check_layers.py` | чистота слоёв: креды, машинные пути, доменные имена, жанр правила, правила-сироты, согласованность карты хука | весь репозиторий |
| `ci/check_hook_injection.py` | что впрыснет хук на конкретном пути и молчит ли там, где должен | 19 путей |
| `ci/simulate_install.py` | собирается ли из дистрибутива рабочая установка; лист верификации по факту | 15 проверок |
| `evals/triggering` | находится ли правило по формулировке задачи — нужна сессия без правил в контексте | 44 кейса |

Первые три гоняются на каждый коммит, четвёртая — руками перед релизом.
Каждый из трёх гейтов намеренно ломали и убеждались, что он краснеет: снятая
кодировка у хука дала 11 промахов из 15, суженная маска — «не поднялось»,
расширенная — «поднялось лишнее». Гейт, не проверенный на поломке, неотличим
от заглушки, которая всегда печатает «чисто».
