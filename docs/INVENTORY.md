# Состав дистрибутива

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
| версия | 0.7.3 |
| правил | 48 |
| скиллов | 8 |
| ролей субагентов | 13 |
| команд | 4 |
| гейтов | 4 |
| файлов в цели | 234 |
<!-- /generated:stats -->

## Что появляется в целевом проекте

```
AGENTS.md                корневой контракт: роли, MCP-профиль, Rule Index, роутинг
CLAUDE.md                ровно одна строка: See @AGENTS.md
rules/                   тела правил, читаются по требованию
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
| `rules/` | 48 |
| `openspec/` | 5 |
| `tools/` | 70 |
| `.claude/agents/` | 13 |
| `.claude/skills/` | 88 |
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
| `case` | 1 | симптом → фикс |
| `recipe` | 8 | задача → процедура |
| `process` | 17 | как вести работу: делегирование, память, верификация |
| `router` | 1 | навигация к соседним правилам |
<!-- /generated:genres -->

<!-- generated:rules-core -->
**Ядро** (17): `case-book`, `collaboration-modes`, `context-packs`, `debugging-loop`, `decision-interview`, `decisions-log`, `orchestrator-economy`, `preflight-worktree`, `script-contract`, `sdd-integrations`, `session-handoff`, `subagent-pipeline`, `subagent-task-templates`, `subagents-model-routing`, `test-discipline`, `tool-output-economy`, `verification-matrix`.
<!-- /generated:rules-core -->

<!-- generated:rules-overlay -->
**Оверлей 1c** (31): `access-rights-bsp`, `anti-patterns`, `async-methods`, `clean-architecture-1c`, `com-powershell-1c`, `dcs-composition-recipes`, `dcs-design`, `ddd-1c`, `dev-standards-architecture`, `dev-standards-core`, `dev-standards-forms`, `extension-patterns`, `form-module`, `form-reserved-names`, `forms`, `forms-add`, `forms-events-add`, `getconfigfiles`, `integrations-add`, `kd2-exchange-rules`, `kd31-exchange-rules`, `locks-and-transactions`, `logging-strategy`, `metadata-xml-workarounds`, `platform-solutions`, `refactor-add`, `registers-design`, `systematic-debugging`, `tooling-playbooks`, `unit-tests-1c`, `v8unpack-source-structure`.
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
| `mermaid-diagrams` | core | Practical guide for creating human-readable and agent-parseable diagrams using Mermaid |
| `openspec-apply-change` | core | Implement tasks from an OpenSpec change |
| `openspec-archive-change` | core | Archive a completed change in the experimental workflow |
| `openspec-explore` | core | Enter explore mode - a thinking partner for exploring ideas, investigating problems, and clarify |
| `openspec-propose` | core | Propose a new change with all artifacts generated in one step |
| `powershell-windows` | core | Windows environment: PowerShell scripting rules for both Windows PowerShell 5.1 and PowerShell 7 |
| `1c-metadata-manage` | 1c | 1C metadata management — create, edit, validate, and remove configuration objects (catalogs, doc |
| `img-grid-analysis` | 1c | Overlay a numbered grid on an image to determine column proportions for layout generation |
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
