#!/usr/bin/env python3
"""Rule reminders that survive context compaction: two hook modes.

* Default (PreToolUse, stdin payload): the file about to be edited is matched
  against a table, and the rules bound to that path are named.
* `--session-start` (SessionStart, source "compact"): after a compaction, state
  plainly that rule bodies are gone and must be re-read. Needs no table.

Two offline modes support installation, where the repository's CI is absent:
`--dry-run <path>` renders what an edit of that path would inject, and
`--check-map [root [map_dir]]` verifies the table against the rules actually
installed — a reminder pointing at an absent rule looks healthy and leads
nowhere.


Why this exists. Rule bodies are read lazily and live in the conversation as a
tool result — the first thing dropped when context is compacted. What survives
is the *summary* line saying the rule was read, so the model treats the question
as settled and never re-reads. The rule is formally loaded and factually gone,
with no signal that anything was lost.

An event-driven reminder does not degrade that way: it is not history, it is a
reaction to an action, and it fires again on every edit of a matching file.

What it deliberately does NOT do:

* It does not inject rule bodies. It injects the one invariant that must not be
  got wrong, plus the rule's path. The body stays on lazy Read — the failure
  mode being fixed is *forgetting that the rule applies*, not the absence of
  the text, and a pointer that arrives at the right moment fixes it at a
  fraction of the cost.
* It does not judge. The mapping is a table, matched by path. Putting a model
  inside the mechanism would inherit exactly the failure mode the mechanism
  exists to cure, and add latency and a second point of failure to every edit.
* It never blocks an edit. Any error at all — unreadable map, malformed JSON,
  missing key — exits quietly with no output. A broken reminder must not be
  able to stop work.

Map format (`rules-map.json`, next to this script):

    {
      "budget_chars": 1200,
      "entries": [
        {
          "globs": ["**/migrations/*.sql"],
          "rule": "rules/<rule-name>.md",
          "invariant": "One line: the thing that must not be got wrong."
        }
      ]
    }

Pure standard library, cross-platform, Python 3.8+.
"""

import fnmatch
import json
import os
import sys

MAP_NAME = "rules-map.json"
DEFAULT_BUDGET = 1200

# Emitted after a compaction (SessionStart, source "compact"), where stdout
# becomes context. This is the counterpart to the path-matched reminder: the
# hook above fires when a *file* is touched, this one when the context that
# held the rule bodies was just rewritten.
COMPACT_NOTICE = (
    "Context was just compacted. Rule bodies read earlier in this session are "
    "no longer present, even where the summary records that a rule was read — "
    "a summary line is not the rule. Treat every previously read rule as "
    "unloaded: before acting on its topic again, re-read it from the Rule "
    "Index. Do not answer from a remembered impression of a rule."
)

# Tools whose input names a file we can match on. The settings.json matcher
# should already narrow to these; this is a second, cheap guard.
PATH_KEYS = ("file_path", "notebook_path", "path")


def load_map(script_dir):
    path = os.path.join(script_dir, MAP_NAME)
    with open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    entries = data.get("entries") or []
    budget = data.get("budget_chars") or DEFAULT_BUDGET
    return entries, budget


def target_path(payload):
    """The file this tool call is about, as a posix-style string."""
    tool_input = payload.get("tool_input") or {}
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value.replace("\\", "/")
    return None


def candidates(raw_path, cwd):
    """Match against both the absolute path and the project-relative one, so a
    map can be written with short repository-relative globs."""
    result = [raw_path]
    if cwd:
        cwd_posix = cwd.replace("\\", "/").rstrip("/")
        lowered = raw_path.lower()
        if lowered.startswith(cwd_posix.lower() + "/"):
            result.append(raw_path[len(cwd_posix) + 1:])
    # A `**/Roles/**` mask needs a separator before `Roles`, which a path
    # starting at the project root does not have. Offer a rooted variant of
    # every candidate so the natural way of writing a mask keeps working.
    return result + ["/" + path.lstrip("/") for path in result]


def matches(entry, paths):
    for pattern in entry.get("globs") or []:
        for path in paths:
            # fnmatch's `*` crosses separators, so `**/x/**/y` behaves as
            # intended here without a path-aware globber.
            if fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(
                path.lower(), pattern.lower()
            ):
                return True
    return False


def build_context(entries, paths, budget):
    seen = set()
    lines = []
    for entry in entries:
        rule = entry.get("rule")
        if not rule or rule in seen:
            continue
        if not matches(entry, paths):
            continue
        seen.add(rule)
        invariant = (entry.get("invariant") or "").strip()
        lines.append("- `{0}` — {1}".format(rule, invariant) if invariant else "- `{0}`".format(rule))
    if not lines:
        return None

    header = (
        "Rules bound to the file you are about to edit. If a rule body is not "
        "in your current context — read it before writing, do not rely on "
        "having read it earlier in this session:"
    )
    text = header + "\n" + "\n".join(lines)
    if len(text) > budget:
        text = text[:budget].rstrip() + "\n(truncated — rule budget reached)"
    return text


def emit(text):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": text,
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")


def rule_kind(path):
    """`kind` из frontmatter правила, или None если его нет."""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            lines = [handle.readline() for _ in range(20)]
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("kind:"):
            return line[5:].strip().strip("\"'")
    return None


def check_map(map_dir, root):
    """Проверка карты в целевом проекте: у него нет нашего CI.

    Карта живёт отдельно от правил, на которые ссылается, и расходится с ними
    молча: запись, указывающая на неустановленное правило, выглядит рабочей и
    печатает путь в никуда. Проверять это глазами при установке — то же
    самое, что полагаться на память вместо перечитывания правила.
    """
    problems = []
    try:
        entries, budget = load_map(map_dir)
    except OSError:
        print("rules-map.json не найден в {0} — режим по путям не работает".format(map_dir))
        return 1
    except ValueError as error:
        print("rules-map.json не разбирается: {0}".format(error))
        return 1

    if not entries:
        problems.append("карта пуста: ни одной записи")

    for index, entry in enumerate(entries, 1):
        where = "запись {0}".format(index)
        rule = entry.get("rule")
        globs = entry.get("globs")
        invariant = (entry.get("invariant") or "").strip()

        if not isinstance(globs, list) or not globs:
            problems.append("{0}: нет масок".format(where))
        if not rule:
            problems.append("{0}: нет поля rule".format(where))
            continue
        where = "{0} ({1})".format(where, rule)
        if not invariant:
            problems.append("{0}: пустой invariant — впрыснется голый путь".format(where))

        rule_path = os.path.join(root, rule.replace("/", os.sep))
        if not os.path.isfile(rule_path):
            problems.append("{0}: правило не установлено по этому пути".format(where))
            continue
        kind = rule_kind(rule_path)
        if kind is None:
            problems.append("{0}: у правила нет kind во frontmatter".format(where))
        elif kind != "invariant":
            problems.append(
                "{0}: kind '{1}', а в карту идут только invariant".format(where, kind)
            )

        line = "- `{0}` — {1}".format(rule, invariant)
        if len(line) > budget:
            problems.append(
                "{0}: строка длиннее всего бюджета ({1} > {2})".format(
                    where, len(line), budget
                )
            )

    if problems:
        for problem in problems:
            print(problem)
        print("карта: {0} дефект(ов)".format(len(problems)))
        return 1
    print("карта: {0} запись(ей), все правила на месте".format(len(entries)))
    return 0


def force_utf8_stdout():
    """Без этого хук молча теряет напоминание на Windows.

    stdout по умолчанию берёт кодировку консоли (cp1251/cp866), а читатель
    ждёт UTF-8. Кириллица приезжает мусором, а символ вроде «→» вообще не
    кодируется — `print` бросает UnicodeEncodeError, его глотает fail-open
    обёртка, и напоминание исчезает без следа. Ровно тот отказ, который хук
    и должен предотвращать.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main(argv):
    force_utf8_stdout()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # `--check-map [root [map_dir]]`: does the map agree with the rules
    # actually installed? Run at install time, where the repository's CI is not
    # available. Defaults describe the installed layout — map next to the
    # script in `.claude/hooks/`, rules under the project root two levels up.
    # Both are arguments so the distribution's own CI can point the same check
    # at an overlay, where the map does not sit next to the script.
    if argv and argv[0] == "--check-map":
        root = argv[1] if len(argv) >= 2 else os.path.dirname(os.path.dirname(script_dir))
        map_dir = argv[2] if len(argv) >= 3 else script_dir
        return check_map(map_dir, root)

    # `--dry-run <path>` renders what an edit of <path> would inject. Used by
    # the map's own tests and when adding an entry by hand.
    if len(argv) >= 2 and argv[0] == "--dry-run":
        entries, budget = load_map(script_dir)
        text = build_context(entries, candidates(argv[1].replace("\\", "/"), None), budget)
        print(text if text else "(no rule matches this path)")
        return 0

    # `--session-start`: post-compaction notice. Registered on SessionStart,
    # where plain stdout is what reaches the model. Needs no map — it says
    # nothing about any particular rule, only that the bodies are gone.
    if argv and argv[0] == "--session-start":
        try:
            source = (json.load(sys.stdin) or {}).get("source")
        except Exception:
            source = None
        # The matcher in settings.json already narrows to "compact"; this is a
        # second guard for the case where it does not.
        if source in (None, "compact"):
            # Отметка времени делает срабатывание проверяемым: без неё нельзя
            # отличить «хук впрыснул текст» от «модель помнит этот текст».
            import datetime

            print("[rule-inject {0}] {1}".format(
                datetime.datetime.now().strftime("%H:%M:%S"), COMPACT_NOTICE))
        return 0

    payload = json.load(sys.stdin)
    raw_path = target_path(payload)
    if not raw_path:
        return 0
    entries, budget = load_map(script_dir)
    text = build_context(entries, candidates(raw_path, payload.get("cwd")), budget)
    if text:
        emit(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        # Fail open, always: a reminder must never be able to block an edit.
        sys.exit(0)
