#!/usr/bin/env python3
"""Opt-in advisory before a configured deployment, never a deployment runner.

Installed beside command-advisory.py. Process inspection is an additional
explicit opt-in, bounded to a configured target and a fixed read-only probe.
"""
from __future__ import annotations

import importlib.util
import json
import ntpath
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
SPACE_MINUS = re.compile(r"(?i)(?:^|\s)-Dynamic\s+(?:\"-\"|'-'|-(?=\s|$))(?=\s|$)")
EXCLUSIVE = re.compile(r"(?i)(?:^|\s)-Dynamic(?::|\s)+(?:\"-\"|'-'|-(?=\s|$))(?=\s|$)")
FIELDS = {"enabled", "command_any", "dynamic_minus_hint", "targets", "probe_processes", "probe_timeout_seconds", "process_hint", "apache_hint"}
DEFAULT_DYNAMIC_HINT = "PowerShell -File can consume a space-separated -Dynamic minus as another parameter. Use the documented colon form -Dynamic:\"-\" and inspect the complete failure output."
DEFAULT_PROCESS_HINT = "A running client or Designer command line references the configured target. Inspect that target's sessions before an exclusive deployment; this observation alone does not prove a lock."
DEFAULT_APACHE_HINT = "An Apache service is running. Web sessions may be active; service presence does not prove that the configured target is locked."
PROBE = r"""$ErrorActionPreference='Stop'; [Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false); $p=@(Get-CimInstance Win32_Process -Filter "Name='1cv8.exe' OR Name='1cv8c.exe' OR Name='1cv8s.exe'" | Select-Object -First 64 Name,@{Name='CommandLine';Expression={if($_.CommandLine.Length -gt 2048){$_.CommandLine.Substring(0,2048)}else{$_.CommandLine}}}); $a=@(Get-Service -Name 'Apache*' -ErrorAction SilentlyContinue | Select-Object -First 32 Name,Status); @{processes=$p;apache=$a} | ConvertTo-Json -Depth 4 -Compress"""
MAX_INVENTORY = 160 * 1024


def shared(script):
    path = Path(script).absolute().parent / "command-advisory.py"
    spec = importlib.util.spec_from_file_location("airules_command_advisory", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(config, common):
    value = config.get("deploy", {})
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError("deployment configuration")
    if not isinstance(value.get("enabled", False), bool) or not isinstance(value.get("probe_processes", False), bool):
        raise ValueError("deployment switches")
    if not common.literal_list(value.get("command_any", [])):
        raise ValueError("command markers")
    if value.get("enabled") and not value.get("command_any"):
        raise ValueError("explicit deployment command markers required")
    timeout = value.get("probe_timeout_seconds", 1)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= timeout <= 2:
        raise ValueError("process probe timeout")
    for key in ("dynamic_minus_hint", "process_hint", "apache_hint"):
        if key in value and (not isinstance(value[key], str) or not 0 < len(value[key]) <= 1600 or common.BANNER in value[key]):
            raise ValueError("hint")
    targets = value.get("targets", [])
    if not isinstance(targets, list) or len(targets) > 16:
        raise ValueError("target budget")
    for target in targets:
        if not isinstance(target, dict) or set(target) != {"command_any", "path"}:
            raise ValueError("target shape")
        path = target["path"]
        if not isinstance(path, str) or not 1 < len(path) <= 512 or any(ord(c) < 32 for c in path):
            raise ValueError("target path")
        if not ntpath.isabs(path) and not Path(path).is_absolute():
            raise ValueError("absolute target path required")
        if not common.literal_list(target["command_any"]) or not target["command_any"]:
            raise ValueError("target selection markers")
    return value


def selected_target(command, targets):
    matches = {target["path"] for target in targets
               if any(marker.casefold() in command.casefold() for marker in target["command_any"])}
    return next(iter(matches)) if len(matches) == 1 else None


def references_target(command_line, target):
    """Require a whole path token; a neighbouring database is not this target."""
    if not isinstance(command_line, str) or not target:
        return False
    needle = target.replace("/", "\\").rstrip("\\").casefold()
    line = command_line.replace("/", "\\").casefold()
    pattern = r"(?<![\w.\\:-])" + re.escape(needle) + r"(?:\\)?(?=$|[\"'\s;])"
    # Platform /F tokens can put the quoted/unquoted path immediately after F.
    return bool(re.search(pattern, line) or re.search(r"(?:^|\s)\\f(?:[\"'])?" + re.escape(needle) + r"(?:\\)?(?=$|[\"'\s;])", line))


def probe_inventory(timeout):
    if os.name != "nt":
        return None
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PROBE],
                                capture_output=True, timeout=timeout)
        if result.returncode != 0 or len(result.stdout) > MAX_INVENTORY:
            return None
        value = json.loads(result.stdout.decode("utf-8-sig"))
        if not isinstance(value, dict):
            return None
        return value
    except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError):
        return None


def hints(payload, config, common, inventory_provider=probe_inventory):
    command = common.event_command(payload)
    if command is None or payload.get("hook_event_name") != "PreToolUse" or not config.get("enabled"):
        return []
    value = validate(config, common)
    if not value.get("enabled") or not any(marker.casefold() in command.casefold() for marker in value["command_any"]):
        return []
    result = []
    if re.search(r"(?i)(?:^|\s)-File(?:\s|$)", command) and SPACE_MINUS.search(command):
        result.append(value.get("dynamic_minus_hint", DEFAULT_DYNAMIC_HINT))
    # Unknown/ambiguous target means no OS query and no inference of a lock.
    target = selected_target(command, value.get("targets", []))
    if not target or not value.get("probe_processes"):
        return result
    inventory = inventory_provider(value.get("probe_timeout_seconds", 1))
    if not isinstance(inventory, dict):
        return result
    processes = inventory.get("processes", [])
    if not isinstance(processes, list):
        processes = [processes]
    if any(isinstance(p, dict) and str(p.get("Name", "")).casefold() in {"1cv8.exe", "1cv8c.exe", "1cv8s.exe"}
           and references_target(p.get("CommandLine"), target) for p in processes[:64]):
        result.append(value.get("process_hint", DEFAULT_PROCESS_HINT))
    apache = inventory.get("apache", [])
    if not isinstance(apache, list):
        apache = [apache]
    if EXCLUSIVE.search(command) and any(isinstance(a, dict) and str(a.get("Name", "")).casefold().startswith("apache")
                                         and a.get("Status") in (4, "Running") for a in apache[:32]):
        result.append(value.get("apache_hint", DEFAULT_APACHE_HINT))
    return result


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    common = shared(__file__)
    payload = common.read_payload()
    if common.event_command(payload) is None:
        return
    config = common.load_config(common.project_root(__file__))
    common.emit("PreToolUse", hints(payload, config, common))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
