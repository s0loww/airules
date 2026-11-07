# Codex: напоминания о правилах и восстановление контекста

Владелец правил и карты остаётся в `core/hooks/rule-inject.py` и оверлее.
`targets/codex/hooks/config.py` строит регистрацию; `codex-hook.py` — тонкий
runtime-адаптер официальных событий. В проект устанавливаются общий скрипт,
Codex-адаптер и карта рядом в `.codex/hooks/`; конфигурация — `.codex/hooks.json`.

`PreToolUse` принимает `tool_input.command` для `apply_patch`, включая add,
update, delete и move нескольких файлов. Проверяются заголовки, а не содержимое
патча; пути с пробелами и кириллицей сохраняются. Пути разрешаются относительно
cwd вызова, ограничиваются корнем установленного проекта и не открываются.
`Edit`/`Write` используют прежние file-path поля общего скрипта.

Регистрация явно сопоставляет `apply_patch|Edit|Write`. Официальный Codex также
сопоставляет apply_patch через aliases Edit/Write; прежний `Edit|Write` сам по
себе не является доказанным дефектом. Тест проверяет dispatch зарегистрированным
matcher до запуска скрипта, а не только ручную передачу JSON обработчику.

`SessionStart` поддерживает startup/resume/clear/compact/fork. После compact
выдаются указатели на правила, orchestration state и session maps; содержимое
файлов состояния не переносится в prompt. Для остальных источников перечисляются
активные handoff-файлы. Подтверждённый scope сохраняется; заметка не добавляет
разрешений. Пути метаданных проверяются на выход из проекта, ссылки и hardlinks.

В обоих режимах успешный stdout содержит только native JSON:
`hookSpecificOutput.hookEventName` и `additionalContext`. Вход ограничен 1 MiB,
выходной context — 4096 символами, карта — 256 KiB. Ошибка даёт пустой stdout
и exit 0: напоминание не блокирует правку и не выводит диагностические дампы.
Хук не запускает инструменты, сеть, MCP, платформу или команды из документов.

Команда запуска использует Git root, поэтому работает из вложенного каталога
с пробелами. В Windows используется `commandWindows` с PowerShell и локальным
Python; в POSIX — python3. Доверие к hooks устанавливается пользователем в Codex;
инсталлятор не подтверждает trust и не отключает механизмы проверки клиента.

Проверки: `python -B -m unittest ci.test_codex_hooks` и прежний
`python -B ci/check_hook_injection.py check`. Это offline wire/launcher tests,
а не доказательство исполнения хуков живым клиентом после доверия.

Контракт сверен 2026-11-07 с официальной документацией:
[Codex hooks](https://learn.chatgpt.com/docs/hooks), включая tool coverage,
общие входные поля, SessionStart и поддерживаемый output envelope.
