#!/usr/bin/env python3
"""Opt-in discovery probe with an isolated Codex home; never starts a turn.

Use only a disposable rendered fixture with no configured MCP servers. The
ordinary CI suite does not require an installed Codex executable.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time


def probe(project, executable, timeout=45):
    project = Path(project).resolve()
    version = subprocess.run([executable, "--version"], capture_output=True,
        text=True, encoding="utf-8", timeout=10, check=True).stdout.strip()
    if not (project / ".airules-codex-manifest.json").is_file():
        raise ValueError("A rendered disposable airules fixture is required")
    if not (project / ".git").exists():
        raise ValueError("Initialize a separate Git repository in the disposable fixture")
    import tomllib
    config = project / ".codex/config.toml"
    if config.is_file() and tomllib.loads(config.read_text(encoding="utf-8-sig")).get("mcp_servers"):
        raise ValueError("Native discovery fixture must have no MCP servers")
    expected = {p.parent.name for p in (project / ".agents/skills").glob("*/SKILL.md")}
    if not expected:
        raise ValueError("No rendered skills in fixture")
    with tempfile.TemporaryDirectory(prefix="airules-codex-native-") as home:
        env = {k: v for k, v in os.environ.items()
               if not any(s in k.upper() for s in ("API_KEY", "ACCESS_TOKEN", "AUTH_TOKEN"))}
        env["CODEX_HOME"] = home
        # Project-layer trust exists only in this fresh temporary home. Hook
        # definitions remain untrusted; no thread/turn or hook is executed.
        Path(home, "config.toml").write_text("[analytics]\nenabled = false\n\n[projects." +
            json.dumps(str(project)) + "]\ntrust_level = \"trusted\"\n", encoding="utf-8")
        process = subprocess.Popen([executable, "app-server", "--stdio", "--strict-config"],
            cwd=project, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        messages = queue.Queue()
        def read():
            for line in process.stdout:
                try:
                    messages.put(json.loads(line))
                except json.JSONDecodeError:
                    pass
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        serial = 0
        methods = []
        def send(method, params, notification=False):
            nonlocal serial
            if method not in {"initialize", "initialized", "skills/list", "hooks/list", "config/read"}:
                raise ValueError("Discovery-only protocol guard")
            serial += 1
            request = {"method": method, "params": params}
            if not notification:
                request["id"] = serial
            methods.append(method)
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            if notification:
                return None
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    message = messages.get(timeout=min(1, max(.01, deadline-time.monotonic())))
                except queue.Empty:
                    if process.poll() is not None:
                        raise RuntimeError("Native app-server exited before discovery response")
                    continue
                if message.get("id") == serial:
                    if "error" in message:
                        raise RuntimeError("Native discovery rejected " + method + ": " + str(message["error"].get("message")))
                    return message.get("result")
            raise TimeoutError("Native discovery timeout: " + method)
        try:
            send("initialize", {"clientInfo": {"name": "airules_discovery_probe", "version": "1.0.0"}, "capabilities": {"experimentalApi": True}})
            send("initialized", {}, True)
            skills = send("skills/list", {"cwds": [str(project)], "forceReload": True})
            hooks = send("hooks/list", {"cwds": [str(project)]})
            settings = send("config/read", {"cwd": str(project), "includeLayers": False})
            # Match only repository entries: user/system skills remain outside
            # this report and are neither changed nor represented as ours.
            records = []
            def visit(value):
                if isinstance(value, dict):
                    if isinstance(value.get("path"), str) and isinstance(value.get("name"), str):
                        p = Path(value["path"])
                        try:
                            p.resolve().relative_to(project / ".agents/skills")
                            records.append(value)
                        except ValueError:
                            pass
                    for item in value.values():
                        visit(item)
                elif isinstance(value, list):
                    for item in value:
                        visit(item)
            visit(skills)
            found = {item["name"] for item in records}
            missing = sorted(expected - found)
            hook_rows = [row for entry in hooks.get("data", []) for row in entry.get("hooks", [])
                         if Path(row.get("sourcePath", "")).resolve() == project / ".codex/hooks.json"]
            events = {row.get("eventName") for row in hook_rows}
            hook_errors = [error.get("message", "hook discovery error") for entry in hooks.get("data", []) for error in entry.get("errors", [])]
            config_parsed = isinstance(settings.get("config"), dict)
            hooks_found = {"preToolUse", "sessionStart"}.issubset(events)
            return {"passed": not missing and hooks_found and config_parsed and not hook_errors,
                "clientVersion": version,
                "expectedSkills": len(expected), "discoveredSkills": len(found),
                "missingSkills": missing, "methods": methods, "modelTurns": 0,
                "mcpCalls": 0, "hookExecution": "not-performed; trust not modified",
                "hooksDiscovery": [{"event": row["eventName"], "trust": row["trustStatus"], "enabled": row["enabled"]} for row in hook_rows],
                "hooksFound": hooks_found, "hookErrors": hook_errors, "configParsed": config_parsed,
                "rolesExecution": "not-performed", "isolatedHome": True}
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            reader.join(timeout=2)
            process.stdout.close()
            # Windows releases the freshly-created runtime directory shortly
            # after process exit. Retry only this verified owned temp root.
            owned = Path(home)
            if owned.parent.resolve() != Path(tempfile.gettempdir()).resolve() or not owned.name.startswith("airules-codex-native-"):
                raise RuntimeError("Owned temporary root changed")
            for attempt in range(15):
                try:
                    shutil.rmtree(owned)
                    break
                except FileNotFoundError:
                    break
                except PermissionError:
                    if attempt == 14:
                        raise RuntimeError("Native probe temporary cleanup unconfirmed")
                    time.sleep(.1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex", default=shutil.which("codex.exe" if os.name == "nt" else "codex"))
    args = parser.parse_args()
    if not args.codex:
        parser.error("Codex executable unavailable; provide --codex")
    result = probe(args.project, args.codex)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "hooksDiscovery"}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
