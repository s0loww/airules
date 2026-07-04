---
description: "Интеграция с OpenSpec. Load when working with the openspec/ workspace (specs and change proposals)."
alwaysApply: false
---

# SDD-интеграция — OpenSpec

[OpenSpec](https://github.com/Fission-AI/OpenSpec) — единственный SDD-фреймворк,
поддерживаемый в этом дистрибутиве. Другие SDD-фреймворки (Memory Bank, Spec
Kit, TaskMaster и т. п.) **не** поддерживаются — не генерировать и не
обновлять для них артефакты, даже если соответствующие папки или MCP-серверы
случайно присутствуют в проекте.

## Канонические источники

Структура воркспейса, формат spec, формат дельт и полный workflow описаны в
самом воркспейсе — не дублировать их здесь:

| Тема | Файл |
|------|------|
| Структура воркспейса, команды, политика обновления | [`openspec/README.md`](../openspec/README.md) |
| Формат spec и соглашения для `openspec/specs/` | [`openspec/specs/README.md`](../openspec/specs/README.md) |
| Структура change-предложения и формат дельт для `openspec/changes/` | [`openspec/changes/README.md`](../openspec/changes/README.md) |

Прочитать эти файлы перед тем, как писать или редактировать артефакты OpenSpec.

## Соответствие субагент → артефакт OpenSpec

Каждый субагент отвечает за конкретные артефакты OpenSpec. Таблица определяет,
куда какому субагенту разрешено писать.

| Субагент | Читает | Пишет |
|----------|--------|-------|
| **analytic** | существующие `specs/` для контекста | `changes/<id>/proposal.md`, новые записи в `specs/` (через дельты) |
| **planner** | `specs/`, `changes/<id>/proposal.md`, `design.md` | `changes/<id>/tasks.md` |
| **architect** | `specs/`, `changes/<id>/proposal.md` | `changes/<id>/design.md` |
| **arch-reviewer** | `changes/<id>/design.md`, `proposal.md`, `specs/` | заметки ревью (без записи артефактов) |
| **developer** | `specs/`, активный `changes/<id>/` | код; обновляет дельты `changes/<id>/specs/` и отмечает пункты в `tasks.md` |
| **metadata-manager** | `specs/`, активный `changes/<id>/` | структура/схема данных; дельты spec под `changes/<id>/specs/` для новых/изменённых объектов схемы |
| **refactoring** | `specs/`, активный `changes/<id>/` | код; обновляет дельты только при изменении наблюдаемого поведения |
| **performance-optimizer** | `specs/` (нефункциональные/перф-требования) | код; дельты только при изменении перф-требования |
| **error-fixer** | активный `changes/<id>/` | код; обычно без изменений spec (фикс бага сохраняет задуманное поведение) |
| **tester** | `specs/` (сценарии), `changes/<id>/tasks.md` | результаты тестов, отметки в `tasks.md` |
| **code-reviewer** | `specs/`, дельты `changes/<id>/specs/` | вердикт ревью относительно требований (без записи артефактов) |
| **doc-writer** | `specs/`, `changes/archive/` | пользовательская документация, производная от specs |

## Соответствие фазы → субагент

Дефолтный workflow `propose → apply → archive` раскладывается по субагентам так:

| Фаза | Ведущий(е) субагент(ы) | Результат |
|------|------------------------|-----------|
| Требования | `analytic` | `proposal.md` + первичные дельты в `changes/<id>/specs/` |
| Дизайн | `architect` (опционально ревью от `arch-reviewer`) | `design.md` |
| Планирование | `planner` | `tasks.md` |
| Реализация | `developer`, `metadata-manager`, `refactoring`, `performance-optimizer`, `error-fixer` | код + обновлённые дельты + отмеченный `tasks.md` |
| Верификация | `tester`, `code-reviewer` | результаты тестов, вердикт ревью |
| Документация и архивация | `doc-writer`, затем скилл `openspec-archive-change` | пользовательская документация; дельты вмержены в `specs/`, change перенесён в `changes/archive/` |
