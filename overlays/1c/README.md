# overlay: 1c

Слой специфики технологического стека 1С — практики, переносимые между разными
проектами на 1С, но не привязанные ни к одному конкретному проекту. Каждая
практика прошла входной фильтр из `docs/LAYERS.md` и генерализована до уровня
стека (без имён проектов, машинных путей, кредов и конкретных MCP-серверов —
инструменты названы категориями, конкретику даёт MCP-профиль целевого проекта).

Состав:

- `rules/` — 28 правил стека: стандарты разработки, анти-паттерны, формы,
  юнит-тесты (`unit-tests-1c`),
  блокировки/транзакции, регистры, СКД (`dcs-design` + приёмы обхода штатного
  вывода `dcs-composition-recipes`), права и профили групп доступа
  (`access-rights-bsp`), расширения, слои и доменная модель
  (`clean-architecture-1c`, `ddd-1c`), COM-автоматизация
  (`com-powershell-1c`), карта инструментов по типам задач (`tooling-playbooks`).
- `agents/` — 13 полных 1С-специализаций ролей реестра `core/agents/ROLES.md`
  (замещают generic-роли при установке на 1С-проект).
- `skills/` — `1c-metadata-manage` (метаданные/формы/СКД/MXL/роли/расширения),
  `img-grid-analysis` (сетка пропорций для макетов).
- `commands/` — `/deploy-and-test` (каркас деплоя на тестовую ИБ и прогона
  сценария); доставляется вместе с core-командами канала, см. `ONBOARD.md` §5.
- `tools/com-tools/` — библиотека COM-автоматизации (8 модулей `OneC-*`);
  при установке копируется в целевой проект, см. `ONBOARD.md` §5.
- `tools/agent-1c/` — профиле-ориентированный контур bootstrap / doctor / analyze
  (BSL LS) / deploy (DryRun + `-Extension` для расширений) / test
  (Vanessa-Automation), со скелетом смоук-набора `vanessa-suite/`. Проектные факты
  (пути, базы, креды, имя расширения) — в профиле `agent-1c.json` целевого проекта,
  не в контуре. Установка и «до боевого состояния» — `tools/agent-1c/DEPLOYMENT.md`.
- `dev.env.example` — шаблон параметров кодогенерации (префикс, шаблоны
  комментариев модификации); при установке копируется в корень цели как
  `.dev.env.example`, рабочий файл — `.dev.env` (см. `ONBOARD.md` §5).

Роутинг (доменные строки мини-таблицы корневого контракта):

| Триггер | Правило | Роль |
| --- | --- | --- |
| refactoring, duplicates, dead code / рефакторинг, дубли | `refactor-add` | refactoring |
| layers, dependencies, bounded contexts, DDD / слои, зависимости, границы контекстов | `clean-architecture-1c` + `ddd-1c` | architect |
| debugging, bug / отладка, баг — рядом с `debugging-loop` | `systematic-debugging` | error-fixer |
| формы, метаданные, СКД, макеты / forms, metadata | `forms` + скилл `1c-metadata-manage` | metadata-manager |
| распакованные исходники, `*.obj.bsl`, `*.elem.json`, сборка бинарника / v8unpack sources | `v8unpack-source-structure` | developer |
| правила обмена, конвертация данных, ПКО/ПКС, объект не найден при загрузке / data conversion rules | `kd2-exchange-rules` (XML-правила) или `kd31-exchange-rules` (EnterpriseData) | developer |
