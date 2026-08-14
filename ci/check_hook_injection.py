#!/usr/bin/env python3
"""Что впрыснет хук напоминаний на конкретном пути — и молчит ли он там, где должен.

Что закрывает. `rule-inject.py --check-map` проверяет карту на согласованность
с правилами: ссылки ведут в существующие файлы, жанр верный, инвариант
непустой. Ни одна из этих проверок не отвечает на вопрос, ради которого хук
существует: **что получит агент, правя вот этот файл.** Маска, не ловящая свой
путь, проходит их все — карта валидна, правило на месте, напоминание не
приходит.

Так и вышло: на `Ext/ObjectModule.bsl` хук молчал не из-за масок, а потому что
`print` падал на символе, которого нет в кодировке консоли Windows, а
fail-open обёртка глотала исключение и выходила с нулём. Все проверки были
зелёные, доставки не было.

    python ci/check_hook_injection.py check      # сверить пути с ожиданиями
    python ci/check_hook_injection.py coverage   # какие инварианты вне карты

`check` вызывается из `check_layers.py` и потому проходит на каждый коммит.
Проверка сюда и переехала из `evals/`: у вопроса «какое напоминание придёт на
этот путь» один правильный ответ, модель не нужна, разброса между прогонами
нет — значит красное здесь всегда дефект, а не шум, и ждать релиза незачем.
В `evals/` осталось то, что действительно требует суждения модели.

## Почему подпроцессом, а не импортом

Функции хука можно позвать напрямую — быстрее и проще. Но тогда проверка
обходила бы stdout, то есть проверяла бы всё, кроме сломанного. Поэтому хук
запускается настоящим процессом с настоящим stdin, а вывод читается
**байтами** и декодируется явно: мусор в кодировке иначе неотличим от
совпавшей маски.

По той же причине скрипт и карта копируются во временный каталог рядом друг с
другом. В репозитории они лежат врозь (скрипт в ядре, карта в оверлее), а хук
ищет карту только рядом с собой — проверять надо ту раскладку, которая приедет
пользователю.

## Как писать кейсы (`hook_cases.json`)

`path` — из реальной раскладки исходников, а не выдуманный. `expect` —
правила, которые обязаны подняться. `forbid` — **правдоподобный сосед**: маска
ловится на расползании только там, где рядом есть чужая территория. Пути, на
которых хук обязан молчать целиком, идут в `clean`.

`forbid` кодирует проектное решение, а не вкус. Пример: `anti-patterns`
запрещён в модуле формы, потому что тяжёлые запросы там — уже нарушение слоёв,
и напоминать о них значит легитимизировать. Меняется решение — меняется кейс,
и `_note` объясняет, почему.

Ожидание двигается **следом за контентом, а не вместо него**. Промах показал,
что маска не ловит путь → чинится маска. Если вместо этого поправить `expect`,
проверка станет декорацией за минуту.

## Проверка, что гейт умеет краснеть

Прогонялось на трёх поломках (2026-08-14):

    убрана принудительная UTF-8 у stdout      -> 11 промахов из 15
    у locks-and-transactions отобран
      ObjectModule.bsl                        -> «не поднялось» на doc-object
    dev-standards-core расширен на *.xml/*.md -> «поднялось лишнее» на трёх
                                                 XML и срабатывание на README

Гейт, не проверенный на поломке, не отличается от заглушки, которая всегда
печатает «чисто».

Чистая стандартная библиотека, Python 3.8+.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
HOOK = os.path.join(REPO, "core", "hooks", "rule-inject.py")
STACK = "1c"
MAP = os.path.join(REPO, "overlays", STACK, "hooks", "rules-map.json")
RULES_DIR = os.path.join(REPO, "overlays", STACK, "rules")

# Синтетический корень проекта: хук получает абсолютный путь и cwd, как в
# настоящем вызове, а в кейсах лежат относительные пути.
FAKE_ROOT = "/work/target"

RULE_RE = re.compile(r"rules/([A-Za-z0-9_-]+)\.md")
KIND_RE = re.compile(r"^kind:\s*[\"']?([A-Za-z-]+)")


def load_cases():
    with open(os.path.join(HERE, "hook_cases.json"), "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return data.get("cases") or [], data.get("clean") or []


def installed_layout():
    """Карта рядом со скриптом — так это выглядит после установки.

    В репозитории они лежат врозь (скрипт в ядре, карта в оверлее), а хук ищет
    карту только рядом с собой. Проверять надо ту раскладку, которая приедет к
    пользователю, а не ту, что удобна репозиторию.
    """
    tmp = tempfile.mkdtemp(prefix="airules-injection-")
    shutil.copy(HOOK, os.path.join(tmp, "rule-inject.py"))
    shutil.copy(MAP, os.path.join(tmp, "rules-map.json"))
    return tmp


def run_hook(script, rel_path):
    """(правила, проблемы) для правки rel_path. Вывод читается байтами."""
    payload = {
        "tool_name": "Edit",
        "cwd": FAKE_ROOT,
        "tool_input": {"file_path": FAKE_ROOT + "/" + rel_path},
    }
    proc = subprocess.run(
        [sys.executable, script],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    raw = proc.stdout or b""
    if not raw.strip():
        return [], []

    problems = []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [], ["вывод не UTF-8: кириллица приедет мусором"]
    try:
        context = json.loads(text)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        return [], ["вывод не разбирается как ответ хука: {0}".format(text[:80])]

    if "�" in context:
        problems.append("в тексте символы-замены — кодировка потерялась")
    if "truncated" in context:
        problems.append("напоминание обрезано бюджетом")
    return RULE_RE.findall(context), problems


def known_rules():
    """{stem: kind} по правилам оверлея."""
    result = {}
    if not os.path.isdir(RULES_DIR):
        return result
    for name in sorted(os.listdir(RULES_DIR)):
        if not name.endswith(".md"):
            continue
        kind = None
        with open(os.path.join(RULES_DIR, name), "r", encoding="utf-8-sig") as handle:
            for _ in range(20):
                line = handle.readline()
                if not line:
                    break
                match = KIND_RE.match(line)
                if match:
                    kind = match.group(1)
                    break
        result[name[:-3]] = kind
    return result


def warn_stale(cases, rules):
    """Кейс ссылается на правило по имени. Переименовали — кейс молча перестал
    что-либо проверять, и это выглядит как промах маски, а не как протухший
    кейс."""
    stale = set()
    for case in cases:
        for name in list(case.get("expect", [])) + list(case.get("forbid", [])):
            if name not in rules:
                stale.add((case["id"], name))
    for case_id, name in sorted(stale):
        sys.stderr.write(
            "ВНИМАНИЕ: кейс {0} ссылается на несуществующее правило '{1}'\n".format(
                case_id, name
            )
        )
    return len(stale)


def cmd_check():
    cases, clean_paths = load_cases()
    rules = known_rules()
    stale = warn_stale(cases, rules)

    tmp = installed_layout()
    script = os.path.join(tmp, "rule-inject.py")
    problems = []
    try:
        for case in cases:
            got, defects = run_hook(script, case["path"])
            missed = [r for r in case.get("expect", []) if r not in got]
            banned = [r for r in case.get("forbid", []) if r in got]
            if missed or banned or defects:
                problems.append((case["id"], missed, banned, defects, got))
        for rel_path in clean_paths:
            got, defects = run_hook(script, rel_path)
            if got or defects:
                problems.append((rel_path, [], [], defects or ["хук не смолчал"], got))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = len(cases) + len(clean_paths)
    print("путей: {0}, чисто: {1}, с промахом: {2}".format(
        total, total - len(problems), len(problems)))

    if problems:
        print("\n== ПРОМАХИ ==")
        for case_id, missed, banned, defects, got in problems:
            print("  {0}".format(case_id))
            if missed:
                print("    не поднялось: {0}".format(", ".join(missed)))
            if banned:
                print("    поднялось лишнее: {0}".format(", ".join(banned)))
            for defect in defects:
                print("    дефект: {0}".format(defect))
            print("    впрыснуто: {0}".format(", ".join(got) if got else "(ничего)"))
    return 1 if problems or stale else 0


def cmd_coverage():
    """Какие инварианты остались вне карты.

    Не промах сам по себе: у части правил нет пути, по которому их можно
    опознать. Но список должен быть осознанным, а не накопившимся: решение
    «этот инвариант по пути не ловится» принимает человек.
    """
    rules = known_rules()
    with open(MAP, "r", encoding="utf-8-sig") as handle:
        entries = json.load(handle).get("entries") or []
    mapped = {RULE_RE.search(entry.get("rule") or "").group(1)
              for entry in entries if RULE_RE.search(entry.get("rule") or "")}

    invariants = sorted(name for name, kind in rules.items() if kind == "invariant")
    outside = [name for name in invariants if name not in mapped]
    wrong_kind = sorted(name for name in mapped if rules.get(name) != "invariant")

    print("инвариантов: {0}, из них в карте: {1}".format(
        len(invariants), len(invariants) - len(outside)))
    if outside:
        print("\nвне карты:")
        for name in outside:
            print("  {0}".format(name))
    if wrong_kind:
        print("\nв карте, но не invariant (дефект):")
        for name in wrong_kind:
            print("  {0}".format(name))
    return 1 if wrong_kind else 0


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    command = argv[0] if argv else "check"
    if command == "check":
        return cmd_check()
    if command == "coverage":
        return cmd_coverage()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
