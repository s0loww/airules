# TODO / технический долг

## 1c-metadata-manage: рефакторинг (портирован как есть 2026-07-05)

- Пересмотреть 33 PowerShell-скрипта `tools/` на соответствие `core/rules/script-contract.md` (DryRun/-Apply есть не везде; креды передаются как plain-параметры, нет чтения из .env-профилей; отчёты не машиночитаемые).
- Вычистить из `docs/` ссылки на неиспользуемые graph-инструменты (`get_object_dossier`, `trace_impact`, `find_usages_of_object`): `docs/meta-manage.md:491,499,501`; `docs/cfe-manage.md:150,157`; `docs/cf-manage.md:109`; `docs/form-manage.md:1069`; `docs/skd-manage.md:381`; `docs/subsystem-manage.md:131,134` — заменить на категории инструментов профиля проекта.
- `SKILL.md:22` — канальный хардкод пути (`.codex/agents/metadata-manager.toml`) в канало-нейтральном скилле.
- Дедуп/ужатие `docs/` (~240К, 18 файлов) — прогрессивная загрузка работает, но доки местами дублируют друг друга.

## Разное

- simple-версии правил (`*.simple.md` для слабых агентов) не портированы — решить формат (без CJK-мантр, согласовать с `subagent-pipeline.md`).
- `subagent-pipeline`: рассмотреть вынос Handoff-формата в отдельное правило (сейчас единый файл; ядро ценности — блок Handoff — при разбиении вынести целиком).
- `git-hooks` / `playbook-smoke-test` / `rag-reindex` из донора не портированы (платформенная инфраструктура; функцию контроля в airules несёт `ci/check_layers.py`).
- `extension-and-graph-mcp`, `nbki-domain` — проектный слой конкретного проекта, в дистрибутив не входят.
- `agent-1c` (`overlays/1c/tools/agent-1c`, портирован 2026-07-11): `bootstrap` ставит только BSL LS — портативная установка тест-стека (OneScript/opm/vanessa-runner/VA-single) пока ручная (DEPLOYMENT.md §3), кандидат на отдельную команду `bootstrap-tests`. `toolchain.lock.json` — reference-снимок версий, сверять живыми прогонами при обновлении. Baseline-политика analyze (гейт только новых Error-диагностик) описана в доке, но автоматического сравнения с baseline контур не делает — на стороне CI проекта.
