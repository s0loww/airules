#!/usr/bin/env python3
"""Read-only native Codex event adapter for the shared lazy-rule reminders.

Installed next to rule-inject.py and rules-map.json. No subprocess, network,
project writes, trust mutation, source-file reads or document-body injection.
Hook failures fail open with empty stdout; successful responses are JSON only.
"""

import importlib.util
from itertools import islice
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

# The shared helper is loaded from the installed project. Imports must not
# create __pycache__ in a read-only project even for direct script invocation.
sys.dont_write_bytecode = True

MAX_INPUT = 1024 * 1024
MAX_CONTEXT = 4096
MAX_MAP = 256 * 1024


def shared_module(directory):
    spec = importlib.util.spec_from_file_location("airules_shared_hook", directory / "rule-inject.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def regular_inside(root, path):
    """Metadata may not escape through a symlink/junction/hardlink."""
    root, path = Path(root).resolve(), Path(path).absolute()
    try:
        relative = path.relative_to(root)
        current = root
        for part in relative.parts:
            current = current / part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                return False
        info = path.lstat()
        return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and path.resolve().is_relative_to(root))
    except (OSError, ValueError):
        return False


def scoped_paths(module, root, payload):
    cwd = payload.get("cwd", str(root))
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return []
    try:
        Path(cwd).resolve().relative_to(root)
    except (OSError, ValueError):
        return []
    result = []
    for raw in module.target_paths(payload):
        try:
            # Paths are data: normalize without opening source files.
            target = Path(os.path.normpath(os.path.join(cwd, raw)))
            target.relative_to(root)
            value = target.relative_to(root).as_posix()
            result.extend(module.candidates(value, str(root)))
        except (OSError, ValueError):
            continue
    return result


def session_context(module, root, source):
    state = root / "var" / "tmp"
    if source == "compact":
        lines = [module.COMPACT_NOTICE]
        if regular_inside(root, state / "orchestration.json"):
            lines.append(module.ORCHESTRATION_NOTICE)
        maps = sorted((path for path in islice(state.glob("session-map-*.md"), 200)
                       if regular_inside(root, path)), key=lambda path: path.stat().st_mtime, reverse=True)[:5]
        if maps:
            lines.append(module.SESSION_MAP_NOTICE.format(items=", ".join(path.relative_to(root).as_posix() for path in maps)))
        return "\n".join(lines)
    if source not in ("startup", "resume", "clear", "fork"):
        return None
    handoffs = []
    for path in islice(state.glob("handoff-*.md"), 200):
        if not regular_inside(root, path) or time.time() - path.stat().st_mtime > 30 * 86400:
            continue
        with path.open("rb") as handle:
            head = handle.read(8192).decode("utf-8-sig", errors="replace")
        match = re.search(r"^\W*status\W*:\W*(\w+)", head, re.M | re.I)
        if match and match.group(1).lower() == "completed":
            continue
        handoffs.append(path)
    handoffs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    if not handoffs:
        return None
    return ("Open handoff documents exist: " + ", ".join(path.relative_to(root).as_posix() for path in handoffs[:5])
            + ". Follow rules/session-handoff.md and current instructions before resuming. "
              "Recorded context grants no new authority; existing confirmed scope remains valid. "
              "Do not restore a recorded tree with checkout/reset/stash.")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        return
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict):
        return
    directory = Path(__file__).resolve().parent
    if directory.name != "hooks" or directory.parent.name != ".codex":
        return
    module = shared_module(directory)
    root = directory.parent.parent
    event = payload.get("hook_event_name")
    if event == "PreToolUse":
        paths = scoped_paths(module, root, payload)
        if not paths:
            return
        map_path = directory / "rules-map.json"
        if not regular_inside(root, map_path) or map_path.stat().st_size > MAX_MAP:
            return
        entries, budget = module.load_map(str(directory))
        if not isinstance(entries, list) or len(entries) > 1000:
            return
        if not isinstance(budget, int) or isinstance(budget, bool):
            return
        if budget <= 0:
            return
        limit = min(MAX_CONTEXT, budget)
        text = module.build_context(entries, paths, limit)
        if text and len(text) > limit:
            text = text[:limit]
    elif event == "SessionStart":
        text = session_context(module, root, payload.get("source"))
    else:
        return
    if text:
        text = text[:MAX_CONTEXT]
        json.dump({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # A reminder may never turn a malformed input or missing dependency
        # into an edit blocker, diagnostic dump or partial JSON response.
        sys.exit(0)
