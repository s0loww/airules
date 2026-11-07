# Единый пресет 1С для DSH

Статус: официальный Desktop собран, проверен и установлен в live-профиль  
Дата: 2026-11-04  
Стенд: `D:\AI_Projects\project_bki`  
Базовая поставка: DSH Desktop 1С `20261103-134539`

## Текущий прогресс

- baseline поставки зафиксирован в private `dsh_harness_overlay`;
- builder создаёт deterministic `airules-dsh-rulepack`;
- 1С rulepack содержит 55 правил, 13 ролей и 14 skills;
- embedded Rule Index загружает правила через read-only `airules_rule`;
- runtime-provider проверяет manifest/hashes и монтирует contract/rules/roles/skills;
- MCP в artifact представлен только логическими ролями;
- роли доступны через проверяемый `prompt-adapter` (`airules_role`): отдельного
  named-role registry в pinned API DSH нет;
- version-gated installer с backup, receipt и rollback реализован и проверен на fixtures;
- базовый testing contour доступен через declarative-only provider
  (`airules_verification`); конкретные команды остаются проектными bindings;
- pinned patch для release `20261103-134539` добавляет `1c-airules` и скрывает
  Lite/Full/Only из обычного roster, сохраняя legacy-resume;
- schema v2 installer проверяет 11 baseline hashes, 316 artifact files и семь
  exact-text patch targets; read-only plan для установленной сборки имеет статус `READY`;
- итоговый UI artifact `0.1.0-dev13`, policy artifact `0.12.0-dev15`;
- полный private overlay suite: 237/237; API-каталог и смену уровня рассуждений
  подтвердил пользователь. Несовместимый анимированный slider отключён,
  используется штатное меню DSH;
- установлены «Среда 1С», модели 13 ролей, выключенная по умолчанию ротация и
  native-пресеты Python/системного администрирования. Их canonical policy лежит
  в overlays/python и overlays/sysadmin; 6 правил и 4 навыка отдельны от 1С;
- airules_delegate запускает native spawn с выбранной моделью/effort; это
  исполнитель привязок, в отличие от read-only persona в airules_role;
- установлены группировка настроек, единая страница провайдеров/моделей и
  форма проектных параметров .dev.env; MCP и deploy автоматически не меняются;
- устранены HTTP405 подписок и ложное подключение Kimi; HUD подключён к native
  сервису баланса. Подробности: dsh_harness_overlay/docs/settings-release-dev13.md;
- установлен Kimi через штатный PiAiAdapter с отдельным OAuth; реальный вход
  пользователь ещё не проверял;
- установлен read-only инспектор локальных XML/EDT-метаданных и структуры форм
  в правой панели; UI-проверка на BKI остаётся отдельным шагом;
- MCP Manager русифицирован через штатный locale API; новый live receipt:
  `dsh_harness_overlay/var/live-promotion-backups/release-20261104-items234-policy15/receipt.json`;
- установлены отдельные настройки Telegram, ACP, подписок, HTTPS-доступа с
  телефона и MCP Manager; учётные данные и endpoints поставщика не копировались;
- Telegram/ACP/HTTPS listener по умолчанию выключены; подключения и входы
  настраивает пользователь; дополнительные supplier CLI-провайдеры остаются
  отдельной очередью;
- полный OpenSpec runtime/UI установлен: private CLI 1.12.0, панель,
  slash-команды, status/validation, task board, editor и progress/handoff;
- шесть canonical OpenSpec skills; всего embedded skills теперь 14;
- правила hidden-desktop Vanessa и контракт артефактов тестировщика входят
  в установленный dev8 rulepack;
- apply/rollback/reapply доказан на отдельном candidate, финальный visible smoke
  пройден на втором чистом candidate;
- guarded live promotion выполнен с отдельным receipt и полным откатом;
- в рабочем DSH проверены пресет «1С», русская локализация, Plugins, безопасный
  balance HUD и компаньон Капитан Дизель;
- MCP bindings не вшиты и остаются machine/project-настройкой.

## Решение

В обычном выборе должен остаться один пресет **«1С»** с новым внутренним ID
`1c-airules`.

Он строится от `1c-lite` и получает выбранные механизмы `1c-full`, но не канон,
правила, MCP-маршрутизацию и обязательный workflow поставщика. Политика проекта,
оркестрация, роли, testing contour и MCP bindings принадлежат `project_rules`.

Текущая установка почти чистая и совместимость со старыми чатами не требуется.
Поэтому обычный roster можно сразу заменить: оставить один видимый пресет
`1c-airules`, а Lite/Full не переносить в нашу сборку. Alias `1c` из поставки
не переиспользуется, чтобы код не продолжал неявно разворачивать его в Full.

## Почему нельзя просто использовать Full с тремя env-флагами

`ONEC_RULES_AUTO=off`, `ONEC_MCP_FIRST_MODE=off` и
`ONEC_FOREIGN_AGENT_RULES=off` нужны, но недостаточны. При `full=true` всё равно
активируются:

- `onec:contract`, project context, preflight и safe-execution prompts;
- task taxonomy и task-tool loading поставщика;
- rules-source и часть role/domain routing;
- evidence/completion gates и обязательные skills;
- MCP gateway/admin/indexing и поставляемый MCP canon;
- команды установки, обновления базы и deploy;
- Full-only UI, project settings и background lifecycle.

Флаг `full` одновременно означает механику, политику и опасные операции. Его
нужно заменить декларативными capabilities.

## Фактическая разница Lite и Full

| Область | `1c-lite` | Дополнение `1c-full` | Решение для `1c-airules` |
|---|---|---|---|
| Cordis composition | те же 32 plugin rows | те же 32 plugin rows | skeleton оставить |
| Persona | общий coding agent | русская persona senior 1С | заменить короткой нейтральной 1С-persona |
| Базовый Desktop | ASK/PLAN/BUILD, файлы, shell, сессии, модели | без существенной разницы | оставить |
| Разработка | review, checkpoints, общая оркестрация | расширенный процесс | оставить нейтральную механику |
| 1С локально | XML/EDT tree, BSL LS, модули, локальные настройки | graph/MCP actions и расширенные операции | Lite оставить, расширения включать capabilities |
| Правила | только правила проекта | `onec:contract`, rules-source, auto routing | заменить `project_rules` |
| Агенты | штатные субагенты; проектные роли только как текст | роли и handoff поставщика | заменить native-ролями `project_rules` |
| Skills | project/user skills и общий dev-набор | почти весь `onec-bundle` | механические skills выбрать; process skills заменить |
| MCP | пользовательский `.mcp.json` | gateway, admin, canon, auto-install/update | facade + memoria из bindings; admin отдельно |
| Параметры задачи | только ASK/PLAN/BUILD | типы задач, quality, orchestration, UI tests | UI оставить, схему заменить нашей |
| Проверки | локальная BSL-диагностика | prewrite, evidence, completion gate, mandatory checks | движки оставить opt-in, политику взять из testing contour |
| Deploy | отсутствует | Designer/CF/DT, DB mutations, update/deploy commands | отдельная capability, по умолчанию выключена |
| Lifecycle | Desktop/session lifecycle | обновления правил и MCP поставщика | bundle update оставить; rules/MCP update заменить |
| OpenSpec/Atlassian | по умолчанию выключены | по умолчанию включены | независимые project toggles, default off |

Библиотеки правил нельзя объединять. В поставке Full — 60 правил примерно на
500 КБ; в текущем `project_rules` — 23 core + 32 overlay 1С, а BKI-композиция
содержит 59 итоговых правил. Совпадают имена 20 файлов, но ни один общий файл не
совпадает по хэшу. Смешивание создаст два конкурирующих policy layer.

## Целевая композиция

```text
Official DSH Desktop
  + UI, balance, settings, sessions, schedules, plugins
  + Oleg bundle mechanics compatible with the pinned release
  + preset: 1c-airules
      + development mechanics
      + 1C local tools
      + neutral project wizard
      + generic MCP manager and health
      + selected optional 1C engines
  + embedded airules rulepack
      + root contract and lazy rule index
      + rules, verified role prompt-adapter and skills
      + default testing contour
      + no MCP endpoints or credentials
  + optional project overlay
      + project facts
      + rule/role/testing overrides
      + MCP bindings
      + allowed operations
      + deploy/testing capabilities
```

## Встроенный rulepack

Правила встраиваются в поставку как отдельный versioned package, например
`airules-dsh-rulepack`. Это подтверждённый путь: текущий bundle уже монтирует
собственный provider правил и отдельный provider skills. Мы заменяем их нашим
пакетом, а не раскладываем полный комплект в каждый проект.

```text
airules-dsh-rulepack/
  manifest.json
  contract/AGENTS.bundle.md
  rules/*.md
  roles/*.md
  skills/*/SKILL.md
  testing/default.json
```

`project_rules` остаётся source of truth. CI компилирует rulepack, проверяет
ссылки, хэши, лимит инструкций и создаёт release artifact. Private harness
overlay включает этот artifact в поставку DSH.

На чистой машине и в пустом проекте пользователь сразу получает:

- общий контракт и всю ленивую библиотеку правил;
- пресет «1С»;
- verified role personas и model-routing defaults;
- skills и базовый testing contour.

Проектная раскатка нужна только для фактов и отличий конкретного проекта.
Приоритет композиции:

```text
embedded rulepack
  < recipient profile
  < project overlay
  < machine-local override
```

Override выполняется по стабильному ID, а не созданием второй копии правила.
Manifest обязан показать owner, source version и итоговый hash каждого элемента.

Renderer получает два режима:

- `embedded` — для нашей сборки: проверяет совместимость установленного rulepack
  и пишет в проект только context/overrides/testing contour;
- `standalone` — для обычного DSH: при необходимости раскладывает полный набор
  `.dsh/rules-1c` и `.dsh/skills`, как текущий BKI-пилот.

В `embedded`-режиме наличие старой проектной копии тех же правил считается
конфликтом и требует явной миграции, чтобы один rule ID не загружался дважды.

### MCP не входит в rulepack

Встроенный пакет содержит только логические роли MCP, например `code-facade`,
`memory`, `project-data` и `qa`. URL, команды запуска, headers, токены и выбор
конкретного сервера туда не попадают.

MCP настраивается независимо на двух уровнях:

1. machine/user scope — общие facade и memoria через настройки DSH;
2. project scope — `.mcp.json` или ignored binding для ONEMCP/QA и overrides.

Приоритет: project binding → machine binding → capability unavailable. Отсутствие
MCP не мешает старту DSH: UI показывает degraded capability и предлагает
настройку, но не подставляет скрытый endpoint. Секреты хранятся только штатным
credential store или в ignored project configuration.

## Capability registry

Вместо вывода поведения из имени пресета вводится декларативный реестр.

Обязательная основа `1c-airules`:

- `desktop.core` — штатный Desktop;
- `development.core` — файлы, shell, jobs, checkpoints и review;
- `onec.local` — XML/EDT, BSL LS, переходы к модулям и локальное дерево;
- `onec.project-settings` — безопасные локальные настройки;
- `project-wizard.neutral` — обнаружение исходников без установки чужого канона;
- `mcp.manager` — UI, health и ручное подключение;
- `policy.airules` — только инструкции и manifest нашего renderer;
- `memory.project` — memoria по проектному binding;
- `orchestration.airules` — наши роли и handoff contract.

Опциональные capabilities:

- `onec.runtime` — Designer/COM и локальные операции;
- `onec.graph` — graph/index UI поверх зарегистрированного facade;
- `onec.testing` — BSL validation, evidence и completion checks;
- `onec.mcp-admin` — расширенное администрирование MCP;
- `onec.deploy` — изменение базы и развёртывание;
- `onec.rule-router` — будущий lazy router, читающий наш manifest;
- `integrations.openspec` и `integrations.atlassian`;
- `ui.testing` — UI regression contour.

Наличие capability не повышает ASK/PLAN/BUILD и не выдаёт разрешение на опасную
операцию. `onec.deploy` требует проектного allowlist, BUILD, preflight, backup и
явного подтверждения.

## Владение компонентами

| Компонент | Владелец |
|---|---|
| Desktop UI, баланс, настройки, auth, sessions | upstream DSH |
| Совместимые UI/plugins и механические адаптеры | pinned bundle/наш private overlay |
| Правила, Rule Index и project policy | `project_rules` |
| Роли, model routing и handoff | `project_rules` |
| Testing contour и обязательность проверок | `project_rules` + project overlay |
| Endpoint, токены и локальные MCP bindings | ignored local configuration |
| Факты проекта и разрешённые операции | репозиторий проекта |
| Runtime state, credentials, cookies, history | `.desktop-local`/`.dsh-1c`, вне Git |

## Отдельный UI overlay

Интерфейс сборки поставщика переносится отдельным artifact и не входит ни в
`airules-dsh-rulepack`, ни в MCP bindings. Это позволяет независимо обновлять
политику, UI и локальные подключения, а также не превращать отсутствие
необязательного виджета в отказ пресета `1c-airules`.

```text
official/clean DSH baseline
  + ui-overlay
      + balance and cost HUD
      + settings surfaces
      + Russian localization
      + plugin/schedule/MCP management panels
      + optional theme/background/companion
  + preset-overlay
      + 1c-airules and neutral 1C mechanics
  + embedded rulepack
      + policy, roles, skills and verification contour
  + local/project MCP bindings
```

Каждый UI-компонент получает manifest с owner, source package/version/license,
client/backend dependencies, state and secrets policy, compatibility range,
install order и smoke checks. Режим переноса указывается явно:

- `config-only` — компонент уже есть в целевом DSH, переносится только включение;
- `package-copy` — автономный пакет с разрешённой поставкой и pinned hashes;
- `vendor-patch` — точный release-specific patch с backup/rollback;
- `reimplement` — интерфейс переносится на наших контрактах без копирования кода;
- `not-portable` — зависит от закрытого backend или условий лицензии.

Порядок реализации UI: сначала balance/cost HUD, settings и localization;
затем панели plugins/schedules/MCP; после них workspace/sidebar; theme,
background и companion остаются необязательными. Компонент не переносится,
пока не определены лицензия, backend contract, state paths и rollback.

Целевой clean baseline найден в официальном Desktop `0.2.1-rc.5`. Его EXE и
основные package contracts совпадают с portable-сборкой, но `app.asar`
отличается: в сборке поставщика изменены 96 внутренних entry. Поэтому UI overlay
получает отдельный target `official-desktop` и устанавливает внешние пакеты в
профиль Desktop. Полная замена или копирование `app.asar` запрещены; внутреннее
поведение переносится во внешние плагины, а неизвлекаемый runtime patch считается
release-specific исключением с отдельным решением и rollback.

## Provider contracts

Механические плагины не должны импортировать решения конкретного policy layer.
Между preset engine и `project_rules` нужны четыре явных интерфейса:

```text
PolicyProvider
  instructions(scope)
  classifyTask(task, project)
  orchestrationPlan(classification)

RoleProvider
  resolve(role)
  modelTier(role)
  effort(role)
  allowedTools(role)

McpPolicyProvider
  effectiveAllowlist(project)
  routeOrder(project)
  requiredServers(project)

VerificationProvider
  checksFor(changeSet)
  evaluate(evidence)
  completionDecision(evidence)
```

`1c-airules` получает все четыре реализации из встроенного rulepack и
скомпонованного project overlay. Одновременно активировать два provider одного
типа запрещено.

## Что переносим из Full

### Зафиксированный scope переноса

Не переносим в нашу сборку:

- отдельный «Ассистент DSH»;
- OpenWhispr и голосовой слой поставщика;
- Atlassian/Jira;
- support inbox, канал и инфраструктуру поддержки поставщика;
- updater поставщика и обновление через его каталог;
- Live2D-компаньонов поставщика (используется отдельный Капитан Дизель).

Проверки и deploy 1С вынесены в отдельное решение. До включения нужно сравнить
механику поставщика с проектными способами deploy в Эквадоре, КА2 и БЛ:
границы базы/расширений, Designer/EDT/COM, backup, preflight, rollback, smoke,
evidence и разрешения. До завершения сравнения `onec.deploy` остаётся выключен.

OpenSpec, напротив, входит в целевую сборку в полном пользовательском объёме,
но с разделением владельцев:

- `project_rules` остаётся единственным владельцем policy, workflow, ролей,
  структуры артефактов и verification gates;
- из интеграции поставщика переносится только execution/UI layer: pinned CLI,
  DSH panel, slash-команды, status/validation, safe scaffold/detection и
  lifecycle notifications;
- skills и policy поставщика не дублируют наши `openspec-*` skills и
  `sdd-integrations.md`;
- runtime capability называется `integrations.openspec`, включена для
  `1c-airules` по умолчанию и может быть отключена явным project override;
- OpenSpec не включает Atlassian и не требует никакого MCP endpoint.

Стенд приёмки — `project_bki`: в нём уже есть реальные `specs`, `changes`,
`design/tasks`, archive и установленный CLI, поэтому UI/execution layer можно
проверять на существующих артефактах без генерации фиктивного проекта.

### Оставить как механику

- расширенный HUD параметров задачи, но с нашей схемой;
- MCP manager, health/status и long operations;
- metadata/graph UI как клиент нашего facade;
- BSL diagnostics и безопасные validation hooks;
- evidence/receipt engine без навязанного completion policy;
- model orchestration UI, ACP и fallback engine;
- runtime investigation и version help;
- project wizard в нейтральном режиме;
- bundle update, backup и rollback самой поставки.

### Заменить

- `onec:contract` и `onec:project` → скомпонованный `AGENTS.md`/`USER-RULES.md`;
- rules-source и auto routing → renderer manifest и будущий airules router;
- роли и handoff → native roles из `project_rules`;
- task taxonomy и quality defaults → общий testing contour;
- MCP canon/gateway defaults → facade + memoria + project bindings;
- project initialization → наш renderer/installer;
- process skills → наши skills и правила.

### Не включать по умолчанию

- автоустановку и автообновление правил/MCP поставщика;
- MCP-first enforcement поставщика;
- обязательный `onec-development-process`;
- автоматические DB mutations и deploy;
- скрытые фоновые действия, зависящие от `full=true`;
- повторную копию правил в `.codex/rules` и `playbook-rules` как источник истины.

## Порядок сборки

1. Снять machine-readable baseline нужной механики Lite/Full: commands, tools,
   skills, prompt sections и background hooks.
2. Создать private overlay и сразу оставить один пресет `1c-airules`.
3. Ввести capability registry; переносить только выбранные компоненты, без
   требования parity ненужным legacy-пресетам.
4. Добавить сборку `airules-dsh-rulepack` из `project_rules`.
5. До появления named-role API использовать проверяемый `prompt-adapter` для 13
   ролей; после появления API заменить его нативным registry без смены role IDs.
6. Подключить rulepack к preset-level providers и проверить чистый проект без
   проектной раскатки.
7. Подключить BKI overlay и отдельно настроенные `1c-facade`/`memora`.
8. По одной capability включать testing, orchestration, MCP admin,
  graph/runtime и deploy. OpenSpec execution/UI переносится отдельным
  обязательным capability до этих optional-блоков.

## Acceptance gates

### Preset isolation

- новый чат получает `1c-airules`, дочерний чат наследует его snapshot;
- Lite/Full отсутствуют в обычном roster нашей сборки;
- отключённая capability не добавляет command, tool, skill, prompt или
  background action;
- прямой вызов отключённого инструмента отклоняется.

### Policy ownership

- в assembled prompt нет `onec:contract` и правил поставщика;
- активен один Rule Index, все ссылки разрешаются;
- instruction probe не имеет omitted/truncated и остаётся ниже 64 KiB;
- `LLM-RULES.md` остаётся владельцем `/evolve`, renderer его не заменяет.

### Rulepack distribution

- чистая portable-установка получает правила, роли и skills без правки проекта;
- установка работает offline после распаковки;
- manifest и все hashes rulepack воспроизводимы;
- project overlay заменяет элемент по ID без дублирования;
- обновление rulepack имеет backup, version guard и rollback;
- в artifact отсутствуют MCP endpoints, credentials и machine paths.

### MCP

- активный allowlist точно совпадает с project binding;
- для BKI это `1c-facade` и `memora`, без проектных ONEMCP/QA;
- неизвестные серверы сохраняются выключенными;
- secrets не попадают в plan, manifest или отчёты;
- смена MCP требует нового chat/session snapshot только там, где это нужно DSH.

### Roles and skills

- 13 ролей разрешаются проверяемым `prompt-adapter` с model/effort metadata;
- capability честно сообщает `nativeRoleRegistry: false`;
- коллизии skills определяются до apply;
- project skill имеет предсказуемый приоритет;
- process skills поставщика не активируются скрыто.

### Safety and verification

- BKI smoke, hook check и BSL analysis проходят;
- `onec.deploy` отсутствует без явной project capability;
- mutation требует BUILD, preflight, backup и подтверждение;
- apply/rollback overlay проверяется на portable-копии установки;
- неизвестный release ID блокирует patch apply.

## Репозитории

Распространяемая политика остаётся в `project_rules`. Платную поставку и её
локальное состояние туда не копируем.

Рекомендуемый private overlay:

```text
D:\AI_Projects\dsh_harness_overlay
  upstream/release.lock.json
  upstream/manifest.sha256
  src/capability-registry/
  src/presets/1c-airules.json
  src/native-roles/
  patches/<release-id>/
  installer/{plan,render,apply,rollback}/
  tests/{contracts,golden,smoke,fixtures}/
```

Installed release не содержит vendor `test/`, хотя `package.json` ссылается на
него. До получения исходного test suite обязательны собственные golden и
black-box contract tests. Vendor tests затем добавляются, но не заменяют их.

## Следующий инкремент

Проработка проверок/deploy от 2026-11-04 вынесена в
[отдельный Proposed ADR](DSH-CHECKS-DEPLOY-ADR.md) и
[черновик контракта](DSH-CHECKS-DEPLOY-CONTRACT.md). Сопоставлены реальные
инструменты Олега, Эквадора, КА2 и БЛ. Предложен общий протокол с прямым локальным
исполнением через adapters; MCP-фасад не требуется для deploy/test runners.
Capability исполнения пока не включается.

Базовая сборка завершена и установлена. Дальнейшая работа уже проектная:

Уточнение 2026-11-04: пользователь пропустил сценарий на БКИ. Пункты среды 1С,
ролевых моделей/ротации и предметных Python/Sysadmin-пресетов реализованы.
Ниже перечислен оставшийся проектный трек; сценарий БКИ автоматически не запускать.

1. подключить machine MCP facade/memoria без переноса endpoint и секретов в
   distributable artifact;
2. проверить `project_bki` как первый project overlay и подтвердить разрешение
   `airules_rule`, `airules_role`, `airules_verification` и skills в реальной
   задаче;
3. затем раскатать общий project layer на Эквадор, КА2 и БЛ;
4. capabilities `onec.testing`, `onec.runtime` и `onec.deploy` включать отдельно
   по проектным allowlist и только после соответствующих smoke/gates.
