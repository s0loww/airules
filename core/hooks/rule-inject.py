#!/usr/bin/env python3
"""Rule reminders that survive context compaction: two hook modes.

* Default (PreToolUse, stdin payload): the file about to be edited is matched
  against a table, and the rules bound to that path are named.
* `--session-start` (SessionStart, source "compact"): after a compaction, state
  plainly that rule bodies are gone and must be re-read. Needs no table.


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


def main(argv):
    script_dir = os.path.dirname(os.path.abspath(__file__))

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
            print(COMPACT_NOTICE)
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
