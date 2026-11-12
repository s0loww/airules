#!/usr/bin/env python3
"""Opt-in, bounded command hints. Commands and responses are data, never code.

The project owns .airules/command-advisories.json. Missing, disabled or invalid
configuration is silent. This helper never blocks an action or writes state.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
MAX_INPUT = 256 * 1024
MAX_TABLE = 64 * 1024
MAX_TEXT = 32768
MAX_COMMAND = 8192
MAX_ENTRIES = 64
MAX_HINTS = 4
MAX_CONTEXT = 4096
BANNER = "[airules advisory]"
CONFIG = ".airules/command-advisories.json"
ENTRY_FIELDS = {"id", "hint", "command_any", "output_any", "output_all", "ignore_case"}


def project_root(script):
    directory = Path(script).absolute().parent
    if directory.name != "hooks" or directory.parent.name not in {".codex", ".claude"}:
        raise ValueError("installed hook layout required")
    root = directory.parent.parent
    if root.resolve() != root:
        raise ValueError("linked project root")
    return root


def safe_file(root, relative):
    root = Path(root).absolute()
    if root.resolve() != root:
        raise ValueError("linked project root")
    current = root
    for part in Path(relative).parts:
        if part in {"..", "."} or Path(relative).is_absolute():
            raise ValueError("unsafe path")
        current = current / part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("linked configuration")
    info = current.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_TABLE:
        raise ValueError("configuration size/type")
    current.resolve().relative_to(root)
    return current


def bounded_strings(value, *, depth=0):
    """Only known response fields, bounded before joining nested chunks."""
    if depth > 8:
        return []
    if isinstance(value, str):
        return [value[:MAX_TEXT]]
    if isinstance(value, dict):
        result = []
        for key in ("stdout", "stderr", "output", "content", "error", "text"):
            if key in value:
                result.extend(bounded_strings(value[key], depth=depth + 1))
        return result[:64]
    if isinstance(value, list):
        result = []
        for item in value[:64]:
            result.extend(bounded_strings(item, depth=depth + 1))
            if len(result) >= 64:
                break
        return result[:64]
    return []


def response_text(payload):
    parts = bounded_strings(payload.get("tool_response"))
    remaining, result = MAX_TEXT, []
    for part in parts:
        if remaining <= 0:
            break
        part = part[:remaining]
        result.append(part)
        remaining -= len(part) + 1
    return "\n".join(result)[:MAX_TEXT]


def literal_list(value):
    return (isinstance(value, list) and len(value) <= 32
            and all(isinstance(s, str) and 0 < len(s) <= 256 for s in value))


def valid_entry(entry, event):
    if not isinstance(entry, dict) or set(entry) - ENTRY_FIELDS:
        return False
    if not isinstance(entry.get("id"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", entry["id"]):
        return False
    if not isinstance(entry.get("hint"), str) or not 0 < len(entry["hint"]) <= 1600:
        return False
    if BANNER in entry["hint"] or not isinstance(entry.get("ignore_case", True), bool):
        return False
    for key in ("command_any", "output_any", "output_all"):
        if key in entry and not literal_list(entry[key]):
            return False
    if event == "PreToolUse":
        return bool(entry.get("command_any")) and not (entry.get("output_any") or entry.get("output_all"))
    return bool(entry.get("output_any") or entry.get("output_all"))


def load_config(root):
    file = safe_file(root, CONFIG)
    before = file.stat()
    with file.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(MAX_TABLE + 1)
    after = file.stat()
    if len(raw) > MAX_TABLE or (before.st_ino, before.st_mtime_ns, before.st_size) != (opened.st_ino, after.st_mtime_ns, after.st_size):
        raise ValueError("configuration changed")
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict) or set(value) - {"schema_version", "enabled", "pre", "post", "deploy"}:
        raise ValueError("configuration shape")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1 or not isinstance(value.get("enabled"), bool):
        raise ValueError("configuration version/enabled")
    entries, ids = 0, set()
    for key, event in (("pre", "PreToolUse"), ("post", "PostToolUse")):
        rows = value.get(key, [])
        if not isinstance(rows, list):
            raise ValueError("entry collection")
        entries += len(rows)
        if entries > MAX_ENTRIES:
            raise ValueError("entry budget")
        for entry in rows:
            if not valid_entry(entry, event) or entry["id"] in ids:
                raise ValueError("invalid or duplicate entry")
            ids.add(entry["id"])
    if "deploy" in value and not isinstance(value["deploy"], dict):
        raise ValueError("deployment configuration")
    return value


def event_command(payload):
    if not isinstance(payload, dict) or payload.get("tool_name") not in {"Bash", "PowerShell"}:
        return None
    if payload.get("hook_event_name") not in {"PreToolUse", "PostToolUse"}:
        return None
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command or len(command) > MAX_COMMAND or BANNER in command:
        return None
    return command


def matches(entry, command, output):
    def normalize(text):
        return text.casefold() if entry.get("ignore_case", True) else text
    command, output = normalize(command), normalize(output)
    if entry.get("command_any") and not any(normalize(s) in command for s in entry["command_any"]):
        return False
    if entry.get("output_any") and not any(normalize(s) in output for s in entry["output_any"]):
        return False
    if entry.get("output_all") and not all(normalize(s) in output for s in entry["output_all"]):
        return False
    return True


def contexts(payload, config):
    command = event_command(payload)
    if command is None or not config.get("enabled"):
        return []
    output = response_text(payload)
    if BANNER in output:
        return []
    rows = config.get("pre" if payload["hook_event_name"] == "PreToolUse" else "post", [])
    hints = []
    for entry in rows:
        if matches(entry, command, output) and entry["hint"] not in hints:
            hints.append(entry["hint"])
            if len(hints) >= MAX_HINTS:
                break
    return hints


def emit(event, hints):
    unique = list(dict.fromkeys(hints))[:MAX_HINTS]
    if not unique:
        return
    text = (BANNER + "\n" + "\n".join("- " + h for h in unique))[:MAX_CONTEXT]
    json.dump({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def read_payload():
    raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise ValueError("input budget")
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("event object")
    return value


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    payload = read_payload()
    if event_command(payload) is None:
        return
    config = load_config(project_root(__file__))
    emit(payload["hook_event_name"], contexts(payload, config))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Hints are never a permission gate; malformed state is silent.
        sys.exit(0)
