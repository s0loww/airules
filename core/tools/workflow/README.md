# Workflow core

Версия 0.1.0. Node.js 20+, только стандартные модули, без установки зависимостей.
Это первый исполняемый инкремент универсального механизма проверок и deployment.
Конкретные доменные правила и штатные права клиента подключаются отдельно.

## Что реализовано

- Строго типизированные операции adapters и граф зависимостей workflow.
- Пассивные capabilities без запуска процессов, hooks или MCP.
- Plan фиксирует фактические файлы, включая новые файлы внутри объявленной
  области, профиль/config, binding, workflow, adapter и ресурсы. Истёкший либо
  изменившийся план не исполняется; после шага входы проверяются повторно.
- Plan не вызывает adapters. Сохранение плана создаёт только приватный receipt;
  capabilities не создаёт даже state directory.
- Запуск, проверка owner/полномочий, дедупликация request и одно исполнение
  каждого plan, UUID evidence, общие межпроцессные resource locks.
- Состояния каждой стадии и цели: применённое изменение не исчезает при ошибке
  следующей стадии. Перед мутацией journal уже содержит unknown для crash recovery.
- Ограничение времени, кооперативная отмена, ожидание остановки процесса,
  сохранение lock при неопределённом состоянии. Отмена не считается rollback.
- Локальный процесс без shell, счётчики stdout/stderr без сохранения содержимого;
  отдельный adapter для типизированного свежего JSON-отчёта.
- MCP adapter получает уже настроенный caller от клиента. Он не создаёт
  подключения, не ищет tools по имени и не зависит от конкретной топологии.

## Состав и границы доверия

| Файл | Назначение |
|---|---|
| index.mjs | WorkflowHost: capabilities, plan, run, result, cancel, recover |
| cli.mjs | Явный операторский вход с data-only machine registry |
| lib/contracts.mjs | Canonical JSON/digest, ограниченное подмножество JSON Schema, DAG/descriptors |
| lib/snapshot.mjs | Ограниченное чтение, scope fingerprints, запрет symlink inputs |
| lib/local-process.mjs | Фиксированный executable и аргументы от доверенного host |
| lib/report-process.mjs | Свежий нормализованный JSON-отчёт, связанный с run/source |
| lib/mcp-adapter.mjs | Типизированный вызов существующего client MCP caller |
| lib/validators.mjs | Техническое завершение, assertions и normalized test summary |
| lib/recovery.mjs | Доказательное восстановление, durable receipts и снятие только собственной блокировки |

Machine registry, schemas, исполняемый код adapters, result mappings и authorize
поставляет доверенный host. Workflow/binding не могут загружать JS, executable,
shell или выбирать незарегистрированный checkout. Binding содержит лишь
выбор provider и типизированные inputs. Секреты передаются отдельно средствами
host; inline password/token-поля не поддерживаются. Не помещать секреты в
binding, profile snapshots, статические аргументы и source scope.

Native client должен передавать authenticated principal, привязанный к сессии,
и проверять права на чтение проекта и эффекты запуска. CLI использует OS identity.
Один digest или доступ к planId не является авторизацией. Приватный stateDir
должен находиться под ACL пользователя/сервиса, вне scope исходников и вне Git.
Для общей блокировки разных клиентов используется один доверенный stateDir
и одинаковые canonical resource IDs. Resource ID задаётся host; автоматического
обнаружения identity реальной цели в generic core нет.

Local process adapter предназначен для доверенного операторского CLI. Он не
песочница и наследует окружение процесса. Его нельзя напрямую регистрировать
как инструмент чата: native client должен предоставить adapter с собственными
sandbox/subprocess/approval services и фильтрацией окружения. Отмена дерева
процессов не изолирует detached/escaped descendants и не заменяет OS sandbox.
Конкурентный злоумышленник с правами записи в registry/state/input directories
лежит вне модели защиты: проверки symlink/identity не заменяют изоляцию ОС.

## Machine registry и проект

Registry передаётся CLI явно абсолютным путём. Код/настройки в проекте не
загружаются автоматически. Пример структуры (плейсхолдеры нужно заполнить
локальными абсолютными путями, автоматического раскрытия нет):

```json
{
  "schemaVersion": 1,
  "stateDir": "<absolute-private-state-directory>",
  "projects": {
    "sample": {
      "root": "<absolute-project-directory>",
      "bindingPath": ".airules/workflow.json",
      "sourcePaths": ["src"],
      "configPaths": []
    }
  },
  "workflows": {
    "technical-check": {
      "schemaVersion": 1,
      "id": "technical-check",
      "version": "0.1.0",
      "steps": [{"id":"check","adapter":"local","operation":"check","timeoutMs":30000}]
    }
  },
  "localAdapters": {
    "local-checker": {
      "operations": {
        "check": {
          "command": "<absolute-trusted-executable>",
          "args": ["--version"],
          "inputSchema": {"type":"object","additionalProperties":false},
          "effects": ["startsProcess"],
          "validator": "process-exit"
        }
      }
    }
  }
}
```

Проектный binding:

```json
{
  "schemaVersion": 1,
  "projectId": "sample",
  "providers": {"local": {"adapterId": "local-checker"}}
}
```

Это техническая проверка executable, не функциональный test/deploy.
CLI первой версии поддерживает только localAdapters с постоянными аргументами;
MCP и report-process adapters доступны через host API, не через autoload modules.

Из каталога tool:

```text
node cli.mjs capabilities --registry <absolute-registry.json> --project sample --workflow technical-check
node cli.mjs plan --registry <absolute-registry.json> --project sample --workflow technical-check
node cli.mjs run --registry <absolute-registry.json> --plan <id> --digest <digest> --request <unique-request-id> --execute
node cli.mjs result --registry <absolute-registry.json> --run <run-id>
```

Run без --execute отвергается. CLI намеренно не разрешает target mutations;
их сценарии сейчас проверяются только на fake adapters. Новое реальное
исполнение требует отдельного native/domain integration и его gates.

## Evidence

`process-exit` доказывает лишь техническое завершение; для target mutation
он не принимается. `assertions` требует complete и непустые уникальные assertions.
`test-summary` требует complete, положительное число реально исполненных tests,
согласованные counters, отсутствие failures/errors, совпадающие runId/sourceDigest.
JUnit/XML пока не разбираются: доменный adapter должен дать нормализованный
отчёт. Неизвестный validator, пустой отчёт и stale source не дают PASS.

JSON Schema реализована ограниченным строгим подмножеством; неподдержанные
keywords ($ref, pattern, format и др.) отклоняются, не игнорируются. Принимаются
object/properties/required/additionalProperties, array/items/counts/uniqueItems,
string length, number/integer bounds, boolean/null, enum/const/anyOf и annotations.

После перезапуска host старый run не исполняется повторно. Если другой host
не наблюдает владельца выполняющегося run, result сообщает owner-not-attached;
это не доказательство смерти процесса. Неоконченный journal и lock требуют
явной reconciliation через доверенный recovery provider. Автоматического unlock/restore/retry нет.

## Recovery API

`new WorkflowHost({ recoveryProviders, ... })` принимает реестр доверенных
реализаций, поставляемый клиентом, а не проектным JSON. Метод
`recover({ runId, targetId, providerId, requestId, principal })` проверяет владельца,
отдельную авторизацию `recover` с эффектами provider, отсутствие локально активного
executor и принадлежность удержанной блокировки. Provider с изменяющими цель
эффектами требует `allowTargetMutations: true`. Историческую цель после снятой
блокировки этот API не захватывает: восстановление не должно перетирать следующий
деплой. При известном применении с ошибкой host теперь тоже удерживает блокировку.

Provider имеет `effects` (фиксированный массив из EFFECTS), `fingerprint()`
(SHA-256 проверенного кода/конфигурации), `timeoutMs` (100..3600000, default 60000)
и `reconcile(context)`. Context содержит:

```text
schemaVersion, recoveryId, runId, targetId, planDigest, sourceDigest,
targetFingerprint, providerDigest, originalTarget, originalResult,
artifactDir, signal, timeoutMs, deadline
```

`targetFingerprint` связывает исходную цель/класс среды с adapter fingerprints
из сохранённого плана. Provider обязан независимо доказать остановку всех
исполнителей, способных менять эту цель, включая предыдущую recovery-попытку,
и проверить фактическое состояние. Для `restored` он сам выполняет восстановление
через штатные механизмы клиента и проверяет результат по исходной резервной копии.
Булево поле от модели или отсутствие PID в памяти host не является доказательством.
Повтор `reconcile` с тем же recoveryId после прерывания должен быть идемпотентным.

Перед возвратом provider записывает долговечный файл доказательства в
`context.artifactDir` и вычисляет SHA-256 **точных записанных bytes**. Core читает
и перепроверяет файл (1 byte..1 MiB, без symlinks/path escape/hardlinks). Возвращается
только такой объект; дополнительные поля не принимаются:

```js
{
  schemaVersion: 1,
  recoveryId: context.recoveryId,
  runId: context.runId,
  targetId: context.targetId,
  planDigest: context.planDigest,
  sourceDigest: context.sourceDigest,
  targetFingerprint: context.targetFingerprint,
  providerDigest: context.providerDigest,
  executorStopped: true,
  outcome: 'restored', // либо 'not-applied', если исходный journal не подтверждает applied
  observedAt: Date.now(),
  artifact: { path: 'proof.json', digest: '<sha256 of stored bytes>', bytes: storedBytes.length }
}
```

Отмена/таймаут вызывает AbortSignal; recovery mutex сохраняется, пока callback
реально не завершится. Исходная блокировка цели остаётся удержанной. Код provider
проверяется до и после операции; смена кода не превращает старую попытку в успех.
Отдельный sealed receipt сохраняется **до** освобождения блокировки. Перезапуск
после атомарного перемещения старой блокировки завершает этот receipt по tombstone,
не повторяя restore и не трогая блокировку следующего владельца.

`result()` оставляет исходные verdict/mutationState и файл execution journal,
добавляет `recoveries[]`, обновлённые target.recoveryState и aggregate
recoveryState=`completed`, retainedLocks=`false` после восстановления всех целей.
Это не переписывает неудавшийся deploy в PASS. Повтор того же requestId возвращает
тот же receipt без второй операции. Готового universal database restore provider
в generic core нет: предметный проверенный provider должен поставить native host.

## Проверка

```text
node --test test/*.test.mjs
```

Suite использует временные каталоги, fake adapters и собственные процессы Node.
Никаких рабочих projects, external services или target deployments.
