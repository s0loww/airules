# TODO / технический долг

## 1c-metadata-manage: рефакторинг (портирован как есть 2026-07-05)

- Пересмотреть 33 PowerShell-скрипта `tools/` на соответствие `core/rules/script-contract.md` (DryRun/-Apply есть не везде; креды передаются как plain-параметры, нет чтения из .env-профилей; отчёты не машиночитаемые).
- Вычистить из `docs/` ссылки на неиспользуемые graph-инструменты (`get_object_dossier`, `trace_impact`, `find_usages_of_object`): `docs/meta-manage.md:491,499,501`; `docs/cfe-manage.md:150,157`; `docs/cf-manage.md:109`; `docs/form-manage.md:1069`; `docs/skd-manage.md:381`; `docs/subsystem-manage.md:131,134` — заменить на категории инструментов профиля проекта.
- `SKILL.md:22` — канальный хардкод пути (`.codex/agents/metadata-manager.toml`) в канало-нейтральном скилле.
- Дедуп/ужатие `docs/` (~240К, 18 файлов) — прогрессивная загрузка работает, но доки местами дублируют друг друга.

## Разное

(пусто, задел на будущее)
