# TODO / технический долг

## 1c-metadata-manage: рефакторинг (портирован как есть 2026-07-05)

- script-contract: **закрыто 2026-07-12** — все мутирующие скрипты семейства
  (db-ops/epf/meta-remove 2026-07-11; остальные 23 локально-мутирующих
  2026-07-12) на DryRun-дефолте + `-Apply`; пароль — через `-PasswordEnv`
  (в dry run отсутствие переменной — предупреждение, fail только под
  `-Apply`); mxl-decompile — чистый экспорт, без гейта.
- `role-compile.ps1` **восстановлен 2026-07-12** по
  `tools/1c-role-compile/dsl-reference.md` (пресеты, RLS, шаблоны, русские
  синонимы; UUID существующего descriptor сохраняется; проверен
  `role-validate` — 0 ошибок). Регистрацию в Configuration.xml скрипт не
  автоматизирует — только напоминает; кандидат на автоматизацию через
  meta-инструменты.
- `1c-web-ops` не портирован: `docs/web-manage.md` переписан 2026-07-12 на
  штатный `webinst` + ручное управление Apache; порт семейства
  (web-info/publish/stop/unpublish + Playwright-раннер) — кандидат.
- Вычистить из `docs/` ссылки на неиспользуемые graph-инструменты
  (`get_object_dossier`, `trace_impact`, `find_usages_of_object`):
  `docs/meta-manage.md:491,499,501`; `docs/cfe-manage.md:150,157`;
  `docs/cf-manage.md:109`; `docs/form-manage.md:1069`; `docs/skd-manage.md:381`;
  `docs/subsystem-manage.md:131,134` — заменить на категории инструментов
  профиля проекта.
- Дедуп/ужатие `docs/` (~240К, 18 файлов) — прогрессивная загрузка работает,
  но доки местами дублируют друг друга.

## Языковая миграция (политика — docs/CONTRIBUTING.md)

Переведено 2026-07-11: `core/rules/*` (все 11), `core/agents/**` (13 ролей,
ROLES.md, agent-template.md), `core/templates/AGENTS.md`, `core/commands/*`,
`core/skills/powershell-windows`, новый `core/channels/model-profiles.md`.
Остаток (переводить по мере правок):

- `core/channels/adapters.md` — канальные грабли, переводить с особой
  аккуратностью;
- `ONBOARD.md` — исполняется агентом при установке;
- `overlays/1c/agents/*.md` (13, русские тела) и
  `overlays/1c/rules/com-powershell-1c.md`;
- `docs/*` — человекочитаемые, низкий приоритет.

## Разное

- simple-версии правил (`*.simple.md` для слабых агентов) не портированы —
  решить формат (без CJK-мантр, согласовать с `subagent-pipeline.md`).
- `subagent-pipeline`: рассмотреть вынос Handoff-формата в отдельное правило
  (сейчас единый файл; ядро ценности — блок Handoff — при разбиении вынести
  целиком).
- `git-hooks` / `playbook-smoke-test` / `rag-reindex` из донора не портированы
  (платформенная инфраструктура; функцию контроля в airules несёт
  `ci/check_layers.py`).
- `extension-and-graph-mcp`, `nbki-domain` — проектный слой конкретного
  проекта, в дистрибутив не входят.
- `agent-1c` (`overlays/1c/tools/agent-1c`, портирован 2026-07-11): `bootstrap`
  ставит только BSL LS — портативная установка тест-стека
  (OneScript/opm/vanessa-runner/VA-single) пока ручная (DEPLOYMENT.md §3),
  кандидат на отдельную команду `bootstrap-tests`. `toolchain.lock.json` —
  reference-снимок версий, сверять живыми прогонами при обновлении.
  Baseline-политика analyze (гейт только новых Error-диагностик) описана в
  доке, но автоматического сравнения с baseline контур не делает — на стороне
  CI проекта.
