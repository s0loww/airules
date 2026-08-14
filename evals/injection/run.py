#!/usr/bin/env python3
"""Что впрыснет хук на конкретном пути — и молчит ли он там, где должен.

Что измеряется. `ci/check_layers.py --check-map` проверяет, что карта
согласована с правилами: ссылки ведут в существующие файлы, жанр верный,
инвариант непустой. Ни одна из этих проверок не говорит, **что получит агент,
правя вот этот файл**. Маска, не ловящая свой путь, проходит их все: карта
валидна, правило на месте, напоминание не приходит.

Ровно так и случилось: на `Ext/ObjectModule.bsl` хук молчал не из-за масок, а
потому что `print` падал на символе, которого нет в кодировке консоли Windows,
и fail-open обёртка глотала исключение. Все проверки были зелёные.

Отсюда два решения в устройстве прогона:

* хук запускается **подпроцессом с реальным stdin**, а не импортом функций.
  Импорт обходит stdout и не увидел бы отказ кодировки — то есть проверял бы
  всё, кроме сломанного;
* вывод читается **байтами** и декодируется явно. Мусор в кодировке иначе
  выглядит как совпавшая маска.

Прогон детерминированный: у вопроса «какое напоминание придёт на этот путь»
один правильный ответ, суждение модели не нужно. Поэтому, в отличие от
`triggering/`, здесь нет промпта и ответов — есть ожидание и факт.

    python evals/injection/run.py check      # сверить пути с ожиданиями
    python evals/injection/run.py coverage   # какие инварианты вне карты

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
REPO = os.path.dirname(os.path.dirname(HERE))
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
    with open(os.path.join(HERE, "cases.json"), "r", encoding="utf-8-sig") as handle:
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
