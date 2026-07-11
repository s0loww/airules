# Софт для развёртывания и работы дистрибутива

Справочник по инструментам, на которые опираются правила и скиллы airules:
что обязательно, что опционально и откуда скачивать. Установка дистрибутива
сама по себе внешнего софта **не требует** (см. `README.md` — standalone);
всё ниже подключается по мере использования соответствующих правил.

## Обязательное (любой канал)

| Инструмент | Зачем | Репозиторий / скачивание |
| --- | --- | --- |
| Git | репозиторий цели, бэкапы, диффы | <https://git-scm.com/downloads> |
| Кодинг-агент (один из) | исполнитель ONBOARD и рабочих сессий | Claude Code — <https://claude.com/claude-code>; Codex CLI — <https://github.com/openai/codex>; Cursor — <https://cursor.com>; сторонние агенты — канал `plain` |

## Контрибьюторам дистрибутива

| Инструмент | Зачем | Репозиторий / скачивание |
| --- | --- | --- |
| Python 3.9+ | `ci/check_layers.py`, pre-commit hook | <https://www.python.org/downloads/> |

## Опциональное — по core-правилам и скиллам

| Инструмент | Правило/скилл | Репозиторий / скачивание |
| --- | --- | --- |
| OpenSpec CLI | скиллы `openspec-*`, правило `sdd-integrations` | <https://github.com/Fission-AI/OpenSpec> |
| rtk (сжатие вывода команд) | правило `tool-output-economy` | репо: <https://github.com/rtk-ai/rtk>; релизы (Windows: `rtk-x86_64-pc-windows-msvc.zip`): <https://github.com/rtk-ai/rtk/releases> |
| ripgrep | нужен только для `rtk rg` (часть фильтров rtk) | <https://github.com/BurntSushi/ripgrep/releases> |

Примечания к rtk: телеметрия opt-in (по умолчанию выключена); автоперехват —
только глобальный `rtk init -g` по решению пользователя; проектный `rtk init`
в airules-раскладке не использовать (грабля — `core/channels/adapters.md`);
проектные фильтры одобряются командой `rtk trust` вручную. Готовый рецепт
фильтров для 1С — `overlays/1c/tools/rtk-filters.example.toml`.

## Оверлей 1c

Точные закреплённые версии, URL и sha256 — в
`overlays/1c/tools/agent-1c/toolchain.lock.json`; порядок развёртывания
тест-контура — `overlays/1c/tools/agent-1c/DEPLOYMENT.md`.

| Инструмент | Зачем | Репозиторий / скачивание |
| --- | --- | --- |
| Платформа 1С:Предприятие 8.3 | конфигуратор, `1cv8.exe`, `webinst` | <https://releases.1c.ru> (по лицензии) |
| BSL Language Server | анализ/диагностики BSL (`agent-1c analyze`) | <https://github.com/1c-syntax/bsl-language-server/releases> |
| OneScript (oscript) | рантайм для opm/vanessa-runner | <https://oscript.io> / <https://github.com/EvilBeaver/OneScript/releases> |
| opm | пакетный менеджер OneScript | <https://github.com/oscript-library/opm> |
| vanessa-runner | запуск сценарных тестов | <https://github.com/oscript-library/vanessa-runner> |
| Vanessa Automation | BDD-сценарии (`vanessa-suite/`) | <https://github.com/Pr-Mex/vanessa-automation/releases> |
| Apache HTTP Server | веб-публикация ИБ (`docs/web-manage.md`) | <https://httpd.apache.org/download.cgi> (windows-сборки: <https://www.apachelounge.com/download/>) |

Правило обновления ссылок: версии в этом файле не фиксируются — источник
пинов один (`toolchain.lock.json`), здесь только адреса проектов.
