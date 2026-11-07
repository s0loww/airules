# OpenSpec

> **AI-агенты:** правила проекта — в корневом `AGENTS.md`; установка и обновление правил — по `ONBOARD.md` дистрибутива airules (в проект не копируется). Этот файл — человекочитаемый обзор воркспейса OpenSpec.

Воркспейс spec-driven разработки для этого проекта, устроенный по workflow
[Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) v1.0+ (OPSX,
artifact-guided).

Эта папка раскладывается инсталлятором дистрибутива правил как общий
scaffold — так что любой проект, устанавливающий дистрибутив, стартует с
готовой структурой OpenSpec. Инсталлятор копирует файлы в режиме
**skip-if-exists** — существующие specs и change-предложения никогда не
перезаписываются.

## Структура каталога

```
openspec/
├── README.md           # этот файл
├── config.yaml         # опциональный проектный конфиг OpenSpec
├── project.md          # паспорт проекта для агента (см. project-template)
├── specs/              # источник истины: как система ведёт себя сейчас
│   └── <domain>/
│       └── spec.md
└── changes/            # активные предложения (одна папка на change)
    ├── archive/        # завершённые changes (создаётся `openspec archive`)
    └── <change-name>/
        ├── proposal.md # зачем и что меняется
        ├── design.md   # как (технические решения, опционально)
        ├── tasks.md    # чеклист реализации
        └── specs/      # дельта-спеки (ADDED / MODIFIED / REMOVED)
            └── <domain>/
                └── spec.md
```

## `project.md` — паспорт проекта

`project.md` — компактный источник фактов о проекте для агента: что за
проект, где истина, какие ограничения, термины, контуры и неизвестные факты.
Он не заменяет README и не дублирует детали — детали остаются в
specs/rules/docs. Файл заполняется вручную или инсталлятором проекта на
основе реальных сигналов конкретного стека; при отсутствии таких сигналов
секции остаются помеченными как «НЕ НАСТРОЕНО» до заполнения.

## Активация команд

The distribution supplies six canonical skills:
`openspec-propose`, `openspec-apply-change`, `openspec-update`,
`openspec-sync`, `openspec-archive-change` and `openspec-explore`.
The target installer determines their paths. A harness may expose matching
slash commands and a panel, all using the same canonical skill provider.
Restart the tool after installation when it does not reload skills live.

`openspec-update` revises an existing change's plan. `openspec-sync` merges
its delta specs into main specs without archiving. They are workflow skills;
there is no CLI `openspec sync`, and CLI `openspec update` has a different
maintenance purpose.

### Обновление до новой версии OpenSpec (опционально)

Use the CLI version selected by the project or bundled by the harness.
Upgrading that CLI and refreshing tool integrations are explicit maintenance
operations; neither is required merely to use a workflow skill.

```bash
openspec update      # refresh integration files using the selected CLI
```

Review the affected instruction/skill files before this command overwrites
them. The distribution's canonical skills remain authoritative; retain project
overrides and avoid registering a competing generated skill set.

## Workflow (базовый профиль)

```
propose <idea>   →  apply   →  archive
```

1. **propose** — агент создаёт новую папку в `changes/<change-name>/` с
   `proposal.md`, дельта-`specs/`, `design.md` и `tasks.md`.
2. **apply** — агент реализует задачи из `tasks.md`.
3. **archive** — завершённые changes вмерживаются в `specs/`, папка change
   переносится в `changes/archive/<date>-<change-name>/`.

Подробнее см.:

- Getting started — <https://github.com/Fission-AI/OpenSpec/blob/main/docs/getting-started.md>
- Workflows — <https://github.com/Fission-AI/OpenSpec/blob/main/docs/workflows.md>
- Commands — <https://github.com/Fission-AI/OpenSpec/blob/main/docs/commands.md>

## Интеграция с дистрибутивом правил

Подробные правила о том, как читать и обновлять эту папку, живут в
`rules/sdd-integrations.md` (загружается по требованию, когда в проекте
обнаружен SDD-фреймворк).
