---
name: /todolist
id: todolist
category: OpenSpec
description: Проверить техдолг в OpenSpec todo.md и вывести таблицей
---

<!-- Формат todo.md описан в правиле sdd-integrations: одна задача = секция `## <TaskName>`, буллеты — детали той же задачи. -->

Собери список зафиксированного техдолга из OpenSpec TODO-файлов и покажи результат таблицей.

## Что считать источником техдолга

- Ищи файлы `openspec/specs/**/todo.md`.
- Если пользователь явно указал capability — ограничься файлом `openspec/specs/<capability>/todo.md`;
  иначе просканируй все `openspec/specs/*/todo.md`.
- Формат задачи:
  - **одна задача = один раздел `## <Название задачи>`**;
  - bullets внутри раздела (`- ...`, `- [ ] ...`, `- [x] ...`) — это детали этой же задачи.
- Статус задачи:
  - если внутри раздела есть хотя бы один `- [ ]`, статус `open`;
  - иначе, если есть только `- [x]`, статус `done`;
  - если чекбоксов нет, статус `open`.

## Шаги

1. Найди все `openspec/specs/**/todo.md` (или только указанную capability, если она передана).
2. Для каждого файла:
   - Определи capability как имя каталога под `openspec/specs/<capability>/`.
   - Разбери разделы `## ...` как отдельные задачи.
   - Для каждой задачи определи статус по правилам выше.
3. Покажи итог в markdown-таблице с колонками:
   - `Capability`
   - `Status`
   - `Task`
   - `Source`
4. В конце добавь сводку:
   - `Total`
   - `Open`
   - `Done`

## Формат вывода

```markdown
| Capability | Status | Task | Source |
|---|---|---|---|
| <capability> | open | <task name> | openspec/specs/<capability>/todo.md |
```

Если TODO-файлы не найдены — выведи: `OpenSpec todo.md files were not found.`
