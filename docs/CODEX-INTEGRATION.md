# Codex в основном airules

Дата: 2026-11-07. Codex реализован как `targets/codex`, а не как новая копия
библиотеки правил. Статус: experimental / renderer implemented. Рабочие проекты,
профили клиентов и установленная DSH в этой работе не обновлялись.

## Что перенесено из отдельного порта

Источником адаптаций служил отдельный `project_rules_codex` версии
`0.13.0-dev.1`, основанный на airules `0.12.0` / `05181aa` (импорт 2026-10-29).
Он использован только для чтения. Текущие общие правила и навыки берутся из
этого основного репозитория, включая последние дополнения обеих очередей.

- Нативные TOML-роли, разделение динамического и фиксированного исполнителя.
- Преобразование проектных команд в навыки Codex.
- Проектная конфигурация MCP со ссылками на переменные окружения.
- Нативный hook protocol, Windows launcher, multi-file `apply_patch` и compact.
- Проверки владения файлами, конфликтов, обновления и проектного слоя.
- Переносимые уточнения оркестрации сведены в core, а не оставлены отдельными
  копиями. Карта решений: [CODEX-CORE-MERGE.md](CODEX-CORE-MERGE.md).

Свежие OpenSpec, hidden-desktop, workflow runner и skill изменения основного
airules сохранены. Метод больше не нужно независимо дописывать в двух деревьях.
Отдельный порт остаётся исходным свидетельством; дальнейшие изменения Codex
следует вносить в основной target и общий core по их ответственности.

## Состав и запуск

Состав `1c/common/public/codex`: 55 правил, 13 основных ролей и дополнительное
аналитическое deep-определение (всего 14 TOML), 46 canonical навыков и 4 навыка
из команд. Навыки DSH `creating-dsh-plugins` и `telegram` сюда не добавляются.
Все ресурсы и лицензии bundle сохраняются; DSH backend tools не создаются в
Codex одним копированием инструкций.

Руководство и пример bindings:
[README target](../targets/codex/README.md),
[раскладка и CLI](../targets/codex/layout.md),
[bindings.example.json](../targets/codex/bindings.example.json).
Python 3.11+; только стандартная библиотека, без скачивания зависимостей.

CLI поддерживает `render`, `verify`, `plan`, `apply`, `rollback`. Render пишет
только в новый стенд, plan не изменяет проект. Профиль public не требует ни
фасада, ни Memoria: выбранные MCP задаются отдельно. Пустой набор MCP сохраняет
существующий `.codex/config.toml` и не создаёт подключения.

`AGENTS.md` проверяется на полный индекс и таблицу ролей, default budget
32768 байт; превышение блокирует сборку вместо скрытого усечения. Проектные
факты, testing contour и существующий OpenSpec остаются собственностью проекта.

## Владение и обновление

Нативное владение фиксирует `.airules-codex-manifest.json`. Оно отделено от
прежнего `.airules-manifest.json`: чужой manifest не предоставляет разрешения
перезаписать существующий `AGENTS.md`, навыки или настройки. Переход с прежней
установки требует просмотра плана и явного разрешения конфликтов, без force.

Apply проверяет весь план до записи и снимает backup/receipt. Обновляются
только принадлежащие установке неизменённые файлы; снятые с исходника файлы
сами не удаляются. При ошибке записи компенсируются уже сделанные изменения.
Конкурентная локальная правка сохраняется и отмечается как `recovery-required`,
вместо ложного сообщения о полном восстановлении. Rollback тоже компенсирует
частичный сбой; после успешной компенсации его можно повторить.

## Проверка

- Общий unittest gate: 38 тестов PASS (14 прежних, 14 target, 10 Codex hooks).
- Проверка трёх compositions и layer purity: PASS; layer selftest PASS.
- Прежние Claude injection cases: 19/19; Claude install simulation: 19/19.
- DSH regression rulepack: build/verify PASS, 48 навыков, 55 правил, 13 ролей,
  360 файлов. Этот пакет не устанавливался в рабочую DSH.
- Target fixtures проверяют canonical ресурсы/NOTICE, таблицу и TOML ролей,
  бюджет, optional MCP, сохранность проекта и config, локальные конфликты,
  tamper/traversal, failure recovery и rollback. Два обнаруженных дефекта
  восстановления воспроизведены независимым агентом и закрыты повторным прогоном.
- Hooks проверяются через зарегистрированный matcher и фактический процесс,
  включая Windows запуск из вложенного Git-каталога с пробелами. Это offline
  проверка обработчика и dispatch, не обход client trust.

Нативная проверка discovery выполнена установленным
`codex-cli 0.167.0-alpha.3.2` через stdio app-server в отдельном временном
`CODEX_HOME`, на новом Git-стенде. Проектный config layer доверен только в этом
временном home для обнаружения файлов; доверие самим хукам не выдавалось.

- `skills/list`: 50/50 навыков, отсутствующих нет.
- `hooks/list`: PreToolUse и SessionStart найдены; оба остаются untrusted.
- `config/read`: нативная конфигурация успешно разобрана.
- Протокол probe допускает только initialize/initialized и три read-метода.
  Model turns = 0, MCP calls = 0, исполнение хуков и ролей не запускалось.

Результаты: `var/codex-integration/native-discovery.json`, `final-tests.log`,
`composition.log`, `layers.log`. Probe: [ci/probe_codex_native.py](../ci/probe_codex_native.py).
Он требует отдельный disposable Git-стенд и пустые MCP bindings; global config,
учётные данные, hook trust и рабочие проекты не меняет. Подробности hook контракта:
[CODEX-HOOKS.md](CODEX-HOOKS.md).

## Граница готовности

Реализованы и проверены source/build/install/rollback и native discovery.
Выбор модели/effort на живом запуске роли, исполнение после review/trust хуков,
MCP handshake, triggering-evals и реальные проверки 1С требуют отдельной
проектной приёмки. Наличие навыка не доказывает доступность его внешнего runtime.
Версия `VERSION` и Git-теги не менялись; это проверенный development snapshot.

Нативные форматы сверены с официальной документацией OpenAI 2026-11-07:
[custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents),
[skills](https://learn.chatgpt.com/docs/build-skills),
[MCP](https://learn.chatgpt.com/docs/extend/mcp),
[hooks](https://learn.chatgpt.com/docs/hooks).
В частности, `Edit|Write` — поддерживаемые aliases `apply_patch`, а не найденный
баг прежнего порта.
