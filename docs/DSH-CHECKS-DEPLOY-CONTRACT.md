# Черновик контракта проверок и deploy

Версия обсуждения: 0.4, 2026-11-04. Статус: **Proposed; не runtime API**.
Не добавляет MCP tools, endpoints, профили или разрешения в установку.
Основание: [ADR](DSH-CHECKS-DEPLOY-ADR.md).

Implementation 0.1: [core README](../core/tools/workflow/README.md) описывает
реализованное подмножество/API, CLI и его ограничения. Полный документ ниже —
целевой контракт; artifact edges/output contracts реализованы не полностью.
Native DSH bridge, UI и адаптеры проектных runners установлены
с проверенными `doctor`/`analyze`. Исполнители `deploy-preview`/`deploy-apply`
поддерживают файловые и серверные цели 1С test/development. Policy dev25 добавляет
recovery providers с доказательством остановки и состояния цели; исходный режим
fixture-only допускает только заглушку. Реальные базы при проверках не запускались.
Это не свидетельство готовности конкретной живой базы. См.
[workflow release](D:/AI_Projects/dsh_harness_overlay/docs/workflow-complete-release.md).

Execution host (далее также worker) — локальный компонент запуска, не обязательная
служба или MCP backend. Deploy и тестовые runners вызываются напрямую через
adapters. MCP используется только отдельными шагами с явно заявленной dependency;
отсутствие MCP-фасада само по себе не блокирует локальный deploy/test workflow.
Фасад не требуется и для MCP-шагов: допустимы прямые серверы, фасад и их смесь.
Использование одного из вариантов определяется настройками получателя/проекта.

## Capability и provider binding

`requiredCapability` шага — семантический versioned contract, не имя MCP tool.
Provider binding содержит `capabilityRef`, `providerKind=local|mcp`, `adapterRef`,
`connectionRef` и `toolRef` для MCP, ссылки на input/result mappings, допустимые
ресурсы/эффекты. ConnectionRef — ссылка на настроенное подключение без URL/ключа;
локальные providers не обязаны иметь MCP поля. Реальные подключения остаются
в штатных пользовательских/машинных настройках, отдельно от общего preset.

План фиксирует выбранный provider и digest его несекретной конфигурации;
run проверяет его identity/контракт. Название tool и успешный tools/list сами
по себе не подтверждают корректность входов, target или семантику PASS.
Нет автоматического выбора по имени, массового подключения backend или
fallback с фасада на прямой сервер. Capability discovery сначала читает
декларации, активные probes учитывают собственные эффекты и разрешения.

Приёмочные конфигурации: (1) только локальные runners без MCP; (2) один проект
с несколькими прямыми MCP и без фасада; (3) фасад плюс отдельные ONEMCP/QA;
(4) ненастроенный необязательный provider. Для (1)/(2) отсутствие фасада не
порождает ошибку готовности. Недоступность обязательного provider блокирует
зависящие шаги, остальные capabilities сохраняют свои собственные статусы.

## Универсальное ядро и пакет 1С

Core принимает workflow, ресурсы, schema-validated inputs, эффекты, зависимости
и ссылки на adapters/validators. `extensionName`, точный build 1С, Designer
DumpResult и последовательность load-config/update-db принадлежат domain pack
1С. Они обязательны в соответствующем домене, но не становятся полями каждого
workflow Python/sysadmin. Ни один другой домен в этом этапе не включается.

Дескриптор расширения: `protocolVersion`, `id`, `version`, `kind`, `inputSchema`,
`outputSchema`, `capabilities`, `supportedResourceKinds`, `hostRequirements`,
`effects`, `validatorRefs`, `cancellationSemantics`, `retrySemantics`.
Поддержка по умолчанию отсутствует, пока явно не объявлена. Core проверяет
совместимость версий и schemas до plan; adapter повторно проверяет факты на host.
Передача дескриптора не даёт права загрузить исполняемый модуль из проекта.

Workflow step: `stepId`, `adapterRef`, `operationId`, `inputs`, `dependsOn`,
`inputArtifactRefs`, `outputContracts`, `requiredCapabilities`, `resourceClaims`,
`effects`, `gates`, `timeoutPolicy`, `onFailure`. Inputs передаются типизированно,
не интерполяцией shell-строки. Artifact references имеют digest/provenance;
произвольный путь из вывода предыдущего шага не становится доверенным input.
Required gates нельзя отключить проектным override в обход domain/machine policy;
несовместимые политики дают явный конфликт, а не неявный last-write-wins.

Подключение обычного нового проекта: выбрать workflow и имеющиеся adapters,
указать ссылки на профили/ресурсы и обязательные проверки. Новый код нужен
для нового runner/формата/семантики, не для нового имени проекта.

## Три отдельных документа

**Binding** описывает, что разрешено проекту. **Plan** фиксирует конкретный
запуск и его входы. **Run result** сообщает наблюдавшийся результат. Статусы
capability не смешиваются со статусами прогона и состоянием базы.

| Объект | Обязательные поля и смысл |
|---|---|
| Binding | schemaVersion; projectId; adapterId/version; profileRef; sourceRef/kind/extensionName; targetRef; operations; requiredGates; baselineRef; backupPolicy; evidencePolicy |
| Plan | planId; trusted owner identity; bindingDigest; profileDigest и digests разрешённых несекретных config inputs; sourceDigest + scope; adapterDigest; toolchain exact build; opaque target identity; environment; operationId; ordered steps/dependencies; declared effects; preconditions; requiredGates; expiry; planDigest |
| Result | runId; trusted owner/worker identity; planDigest; resolved input digests; timestamps; per-step status/effects/artifacts; per-target receipts; overall verdict; mutationState; recoveryState; evidenceIndex |

Binding не дублирует пароль, адрес или настройки уже существующего профиля.
profileRef разрешается worker в зарегистрированном checkout и credential store;
запрещены traversal/symlink-escape и выбор чужого checkout через пользовательский
параметр. Реальные targets и исполняемые paths проверяет машинный registry.
Идентичность цели в UI — непрозрачный стабильный ID с безопасным описанием;
секреты и их обычные угадываемые хеши в plan не включаются.
Перед run сверяются содержимое профиля и все влияющие несекретные конфигурации,
а не только строка profileRef. Секретные inputs учитываются по версии записи
credential store без значения секрета; смена записи требует нового preflight.

## Операции и эффекты

Предлагаемые логические операции, ещё не зарегистрированные как инструменты:

- `capabilities`, `plan`: чтение metadata без запуска проектного кода.
- `run(planId, planDigest)`: выполнение разрешённой операции из сохранённого плана.
- `status(runId)`, `result(runId)`: структурированный статус и очищенный отчёт.
- `cancel(runId)`: остановка только owned процессов, затем финальная диагностика.

Owner поступает из аутентифицированного транспорта; для DSH дополнительно
связан с native session, для CLI/CI — с разрешённым principal соответствующего
client. Это не параметр модели. Worker проверяет полномочия на каждый эффект/target
перед run. planId/digest не являются разрешением; чужие status/result/cancel
отвергаются без утечки evidence. Для восстановления после закрытия чата нужен
явно разрешённый административный путь, а не обход ownership.

Доступные operation IDs определяет adapter: `doctor.files`, `analyze.source`,
`target.preflight`, `deploy`, `probe`, `test.unit`, `test.integration`, `test.ui`,
`backup`, `restore`, предметные операции проекта. Неизвестная операция отвергается.
Публичный вызов не содержит shell/argv/env/script; все реальные команды заданы
проверенным adapter. MCP-канал предметной операции задаётся существующим project
binding и его правилами маршрутизации; модель не добавляет новое подключение.

Каждый шаг объявляет эффекты: `readsSource`, `connectsTarget`, `startsProcess`,
`writesFilesystem`, `writesTargetData`, `changesMetadata`, `serviceLifecycle`,
`externalIO`, `destructiveRecovery`. Это проверяемая декларация adapter, не
песочница сама по себе. Имя check/test/DryRun не снимает эффектов. Скрытые hooks
и загрузка исполняемого профиля не допускаются в read-only plan.

Load-config, проверка применимости/загруженной конфигурации и update-db —
раздельные стадии графа. Если adapter умеет только load+update, это явно
отражается в capability; промежуточный gate не изображается как выполненный.
Ошибка до update может означать уже применённую загрузку конфигурации;
evidence хранит эффекты по стадиям, а не только общий mutationState.

## Состояния

Capability: `configured`, `not-configured`, `unsupported`, `unavailable`.
Наличие файла runner не означает configured; доступность требует проверенного
binding и зависимостей. Network/platform reachability доказывается отдельно.

Шаг: `pending`, `running`, `passed`, `failed`, `blocked`, `skipped`,
`interrupted`, `indeterminate`. Verdict: `PASS`, `FAIL`, `BLOCKED`,
`INTERRUPTED`, `INDETERMINATE`. Причины недоступности/skipped обязательны.
Смешанный результат сохраняет все шаги, а не сворачивается в exit=0.

`mutationState`: `not-applied`, `applied`, `partial`, `unknown`.
`recoveryState`: `not-required`, `required`, `completed`, `failed`, `unknown`.
Если deploy прошёл, но test упал: verdict FAIL, mutationState applied.
Отмена во время UpdateDBCfg: mutationState unknown до подтверждённой диагностики.
Нельзя показывать «откачено» по одному завершению restore-процесса.
Для batch у каждой цели собственные mutation/recovery states и receipt.
Общий applied означает применение ко всем запрошенным целям; partial — известную
часть, unknown — неопределённость хотя бы одной цели. Никакой атомарности между
целями не обещается. Общий FAIL не стирает успешные предыдущие загрузки.

## Evidence и правила PASS

| Канал | Минимальные доказательства |
|---|---|
| Source analyze | Версия checker, scope/source digest, машинный отчёт; diff с проверенной baseline, если она есть |
| Designer load/update | Отдельные свежие exit, DumpResult и разобранный Out; точное extension/source/target соответствие |
| ibcmd load/apply | Проверенные семантика/выходы конкретного adapter, свежие логи, postcondition; нельзя требовать несуществующий Designer DumpResult |
| Postdeploy probe | Проверяемая метадата/контексты, машинные результаты и baseline policy; не только успешная загрузка |
| Unit/Vanessa | Свежий валидный отчёт, expected suite/source identity, tests > 0, failures/errors=0, runner outcome, обязательные assertions |
| Предметная приёмка | Каталог assertions, ненулевое число проверок, результаты и identity пользователя/ролей, контролируемые эффекты/cleanup |
| Hidden UI | Вышеуказанный verdict + происхождение disposable copy, desktop/process ownership, отсутствие утечки окон, timeout/cleanup; visual proof отдельно при необходимости |
| Backup/restore | Identity исходной цели, метод и консистентность, артефакт/receipt, проверка восстановления по политике проекта |

Нулевые тесты, отсутствующий отчёт, старый JUnit и ненастроенный обязательный
probe не дают PASS. Автоматически созданная baseline требует review. Анализ
LLM/ответ COM без предусмотренного проектом oracle не повышает машинный verdict.

У каждого run отдельный UUID-каталог. Worker пишет evidence с контролем доступа,
атомарным финальным manifest и хешами артефактов; DSH получает очищенные данные.
Отдельно учитываются технический успех, бизнес-результат и состояние cleanup.
Ошибка очистки не стирает результат теста, но блокирует общий PASS, если cleanup
обязателен. Evidence не должен раскрывать credentials, URL с токенами или argv.

## Приёмка будущей реализации без базы

Fake adapters проверяют: неподдержанный source kind; отсутствующее имя extension;
неверную environment; неизвестную operation; подмену профиля/adapter/исходников
после plan; перемещение checkout; alias той же базы; symlink escape; чужую отмену;
timeout и partial apply; missing/zero/stale JUnit; malformed Out/DumpResult;
неподтверждённую baseline; недоступный backup; redaction; повторные запросы run.
Повтор одного принятого run request возвращает тот же runId, не второй deploy.
Отдельно тестируются restart worker и незавершённый run: без автоматического
повтора мутации; неизвестное состояние требует reconciliation.
Приёмка универсальности отдельно проверяет workflow с двумя adapters, новый
проект только через binding, неподдержанную protocolVersion, конфликт policy,
один ресурс под разными aliases/clients, обязательный gate при skipped step,
недоверенный output artifact и отсутствие 1С-полей в core-only fixture.
