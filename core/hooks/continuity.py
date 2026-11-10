#!/usr/bin/env python3
"""Bounded project/session continuity; no model, network or memory backend.

The harness owns access, event delivery and trust. Unknown/read-only native
access never becomes permission to write a checkpoint. Runtime data is not
installation content. No I/O happens merely by importing this module.
"""
from __future__ import annotations

import datetime
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import threading
import uuid

BUDGETS = {"minimal": 4096, "balanced": 12288, "expanded": 36864, "off": 0}
MAX_INPUT = 1024 * 1024
MAX_STATE = 32768
BLOCKED_PART = re.compile(r"^(?:\.git|\.ssh|\.aws|\.azure|node_modules|credentials?|secrets?|profiles?|sessions?|history)$", re.I)
BLOCKED_FILE = re.compile(r"(?:^|\.)env(?:\.|$)|^(?:auth|credentials?|secrets?|id_rsa|id_ed25519)(?:\.|$)|\.(?:pem|key|pfx|p12|db|sqlite3?|1cd|dt)$", re.I)
SECRET = re.compile(r"-----BEGIN .*PRIVATE KEY-----|\bBearer\s+\S{8,}|\b(?:sk|ghp|github_pat|xox[baprs])[-_]\w{8,}|[\"']?(?:password|passwd|пароль|secret|token|api[_-]?key|authorization)[\"']?\s*[:=]\s*[\"']?[^\s\"',;{}]{4,}", re.I)


def safe_path(root, relative, *, missing=False):
    if not isinstance(relative, str) or not relative or len(relative) > 512 or re.search(r"[\x00-\x1f\x7f]", relative):
        raise ValueError("unsafe continuity path")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or ":" in relative or "\\" in relative:
        raise ValueError("unsafe continuity path")
    root = Path(root).absolute()
    if root.resolve() != root:
        raise ValueError("linked project root")
    current = root
    for part in rel.parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("linked continuity path")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise ValueError("linked continuity file")
    current.resolve().relative_to(root)
    return current


def read_small(root, relative, limit):
    path = safe_path(root, relative)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError("continuity file size")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        data = handle.read(limit + 1)
    after = path.stat()
    if len(data) > limit or (before.st_ino, before.st_mtime_ns, before.st_size) != (opened.st_ino, after.st_mtime_ns, after.st_size):
        raise ValueError("continuity file changed")
    return data


def load_contract(root):
    root = Path(root).absolute()
    candidates = ["tools/continuity/contract.json", "/".join(("core", "tools", "continuity", "contract.json"))]
    for relative in candidates:
        try:
            value = json.loads(read_small(root, relative, 16384))
            if value.get("schemaVersion") != 1 or value.get("budgets") != BUDGETS:
                raise ValueError("continuity contract version")
            for key in ("compact", "authority", "lead", "subagent", "unavailable", "stale"):
                if not isinstance(value.get("messages", {}).get(key), str) or len(value["messages"][key]) > 1000:
                    raise ValueError("continuity contract messages")
            return value
        except FileNotFoundError:
            continue
    raise ValueError("continuity contract absent")


def origin(payload):
    return "subagent" if payload.get("agent_id") else "lead"


def scope_for(root, payload):
    root = Path(root).absolute()
    cwd, session = payload.get("cwd", str(root)), payload.get("session_id")
    if not isinstance(session, str) or not session or len(session) > 256 or re.search(r"[\x00-\x1f]", session):
        raise ValueError("native session required")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        raise ValueError("native cwd required")
    Path(cwd).resolve().relative_to(root.resolve())
    normalized = str(root.resolve()).replace("\\", "/")
    if os.name == "nt":
        normalized = normalized.lower()
    identity = {"projectKey": hashlib.sha256(normalized.encode()).hexdigest(), "sessionId": session, "origin": origin(payload)}
    if identity["origin"] == "subagent":
        agent = payload["agent_id"]
        if not isinstance(agent, str) or not agent or len(agent) > 256 or re.search(r"[\x00-\x1f]", agent):
            raise ValueError("native agent identity")
        identity["agentId"] = agent
    return identity


def config_for(root):
    value = {"mode": "minimal", "checkpoint": False, "taskFiles": [], "refs": []}
    try:
        config = json.loads(read_small(root, ".airules/continuity.json", 8192))
    except FileNotFoundError:
        return value
    if not isinstance(config, dict) or set(config) - {"schemaVersion", "mode", "checkpoint", "taskFiles", "refs"} or config.get("schemaVersion") != 1:
        raise ValueError("continuity configuration")
    if config.get("mode", "minimal") not in BUDGETS or not isinstance(config.get("checkpoint", False), bool):
        raise ValueError("continuity configuration")
    if not isinstance(config.get("taskFiles", []), list) or len(config.get("taskFiles", [])) > 5 or not isinstance(config.get("refs", []), list) or len(config.get("refs", [])) > 20:
        raise ValueError("continuity configuration bounds")
    value.update(config)
    return value


def native_write_allowed(payload, adapter):
    mode = payload.get("permission_mode")
    if mode in {"plan", "read-only", "readOnly", "planMode"} or payload.get("sandbox_mode") == "read-only":
        return False
    if adapter == "claude":
        return mode in {"acceptEdits", "bypassPermissions"}
    # Current Codex common hook payload does not guarantee this extension.
    # If unavailable, the adapter honestly remains reminder-only.
    return payload.get("sandbox_mode") in {"workspace-write", "danger-full-access"}


def state_relative(scope):
    key = hashlib.sha256(json.dumps([scope["projectKey"], scope["sessionId"], scope["origin"], scope.get("agentId")]).encode()).hexdigest()[:32]
    return "var/tmp/continuity/" + key + "/checkpoint.json"


def load_state(root, scope):
    try:
        value = json.loads(read_small(root, state_relative(scope), MAX_STATE))
    except FileNotFoundError:
        return None
    if not isinstance(value, dict) or any(value.get(key) != scope.get(key) for key in ("projectKey", "sessionId", "origin", "agentId")) or value.get("schemaVersion") != 1:
        raise ValueError("foreign continuity checkpoint")
    allowed = {"schemaVersion", "projectKey", "sessionId", "origin", "agentId", "capturedAt", "generation", "state", "git", "refs", "files", "limitations", "openspec"}
    if set(value) - allowed or value.get("state") not in {"complete", "partial", "unavailable"}:
        raise ValueError("continuity checkpoint shape")
    for key, limit in (("capturedAt", 40), ("generation", 128)):
        if not isinstance(value.get(key), str) or not value[key] or len(value[key]) > limit:
            raise ValueError("continuity checkpoint identity")
    for key, limit in (("refs", 20), ("files", 5)):
        if not isinstance(value.get(key), list) or len(value[key]) > limit:
            raise ValueError("continuity checkpoint bounds")
        for row in value[key]:
            if (not isinstance(row, dict) or set(row) - {"kind", "path", "version", "id", "critical", "callId"}
                    or row.get("kind") not in {"rule", "skill", "file", "orchestration", "session-map", "status", "artifact", "job"}
                    or not isinstance(row.get("path"), str) or len(row["path"]) > 512
                    or not isinstance(row.get("version"), str) or len(row["version"]) > 128):
                raise ValueError("continuity checkpoint reference")
    git = value.get("git")
    if not isinstance(git, dict) or set(git) - {"head", "branch", "changedPaths", "diffstat"}:
        raise ValueError("continuity git metadata")
    for key, limit in (("head", 64), ("branch", 160), ("diffstat", 2048)):
        if key in git and (not isinstance(git[key], str) or len(git[key]) > limit):
            raise ValueError("continuity git metadata")
    if "changedPaths" in git and (not isinstance(git["changedPaths"], list) or len(git["changedPaths"]) > 50 or any(not isinstance(row, str) or len(row) > 512 for row in git["changedPaths"])):
        raise ValueError("continuity git paths")
    limitations = value.get("limitations")
    if not isinstance(limitations, list) or len(limitations) > 10 or any(not isinstance(row, str) or len(row) > 160 for row in limitations):
        raise ValueError("continuity limitations")
    counts = value.get("openspec", [])
    if not isinstance(counts, list) or len(counts) > 10:
        raise ValueError("continuity task counts")
    for row in counts:
        if not isinstance(row, dict) or set(row) != {"path", "version", "total", "done"} or not isinstance(row["path"], str) or len(row["path"]) > 512 or not isinstance(row["version"], str) or len(row["version"]) > 128:
            raise ValueError("continuity task count")
        if any(type(row[key]) is not int or row[key] < 0 for key in ("total", "done")) or row["done"] > row["total"]:
            raise ValueError("continuity task count")
    return value


def save_state(root, scope, value):
    relative = state_relative(scope)
    target = safe_path(root, relative, missing=True)
    data = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(data) > MAX_STATE:
        raise ValueError("continuity checkpoint budget")
    # Create each component only after containment/reparse checks; never follow
    # an existing link or overwrite a hardlinked checkpoint.
    target.parent.mkdir(parents=True, exist_ok=True)
    target = safe_path(root, relative, missing=True)
    lock = target.with_suffix(".lock")
    with lock.open("x", encoding="utf-8") as handle:
        handle.write("continuity")
    temp = target.with_name("." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        safe_path(root, relative, missing=True)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def git_read(root, args, limit=4096):
    env = {key: value for key, value in os.environ.items() if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT"}}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"})
    command = ["git", "--no-optional-locks", "-C", str(root), "-c", "core.fsmonitor=false", "-c", "core.quotePath=false", *args]
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    timer = threading.Timer(1.5, process.kill)
    timer.start()
    try:
        raw = process.stdout.read(limit + 1)
        if len(raw) > limit:
            process.kill()
        code = process.wait(timeout=2)
        if code or len(raw) > limit:
            return "", False
        return raw.decode("utf-8", errors="replace").rstrip("\r\n"), True
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.stdout.close()


def reference(root, kind, relative, **extra):
    if not isinstance(relative, str) or any(BLOCKED_PART.match(part) for part in Path(relative).parts) or BLOCKED_FILE.search(Path(relative).name):
        raise ValueError("private continuity reference")
    data = read_small(root, relative, 256 * 1024)
    return {"kind": kind, "path": relative, "version": "sha256:" + hashlib.sha256(data).hexdigest(), **extra}


def collect_refs(root, config, scope, extra=()):
    refs = []
    requests = list(config.get("refs", [])) + list(extra)
    if scope["origin"] == "lead":
        requests.insert(0, {"kind": "orchestration", "path": "var/tmp/orchestration.json"})
        state = Path(root) / "var/tmp"
        maps = []
        for candidate in islice(state.glob("session-map-*.md"), 200):
            try:
                safe_path(root, candidate.relative_to(root).as_posix())
                maps.append(candidate)
            except (OSError, ValueError):
                continue
        maps = sorted(maps, key=lambda path: path.stat().st_mtime, reverse=True)[:5]
        requests.extend({"kind": "session-map", "path": path.relative_to(root).as_posix()} for path in maps)
    for row in requests[:20]:
        if not isinstance(row, dict) or row.get("kind") not in {"rule", "skill", "file", "orchestration", "session-map", "status", "artifact"}:
            continue
        if scope["origin"] == "subagent" and row["kind"] in {"orchestration", "session-map"}:
            continue
        try:
            candidate = reference(root, row["kind"], row.get("path"))
            if not any(prior["path"] == candidate["path"] for prior in refs):
                refs.append(candidate)
        except (OSError, ValueError, TypeError):
            continue
    return refs


def openspec_counts(root):
    """Mechanical counts only; no proposal/task text enters the checkpoint."""
    result = []
    changes = Path(root) / "openspec/changes"
    for path in islice(changes.glob("*/tasks.md"), 100):
        if len(result) >= 10:
            break
        try:
            relative = path.relative_to(root).as_posix()
            data = read_small(root, relative, 65536)
            text = data.decode("utf-8-sig")
            rows = re.findall(r"^\s*-\s+\[([ xX])\]", text, re.M)
            result.append({"path": relative, "version": "sha256:" + hashlib.sha256(data).hexdigest(),
                           "total": len(rows), "done": sum(row.lower() == "x" for row in rows)})
        except (OSError, ValueError, UnicodeError):
            continue
    return result


def capture(root, payload, adapter, config, scope):
    try:
        previous = load_state(root, scope)
    except (OSError, ValueError, TypeError):
        previous = None
    git = {}
    limitations = ["exact-compact-id-unavailable", "native-file-restore-unavailable"]
    for key, args, cap in [("head", ["rev-parse", "HEAD"], 80), ("branch", ["branch", "--show-current"], 160), ("diffstat", ["diff", "--no-ext-diff", "--no-textconv", "--stat", "--", "."], 2048)]:
        try:
            value, complete = git_read(root, args, cap)
        except (OSError, subprocess.SubprocessError):
            value, complete = "", False
        if complete:
            git[key] = value
        else:
            limitations.append("git-" + key + "-unavailable")
    try:
        status, complete = git_read(root, ["status", "--short", "--untracked-files=no"], 8192)
        git["changedPaths"] = [line[3:][:512] for line in status.splitlines()[:50]]
        if not complete or len(status.splitlines()) > 50:
            limitations.append("changed-paths-partial")
    except (OSError, subprocess.SubprocessError):
        limitations.append("git-status-unavailable")
    value = {"schemaVersion": 1, **scope, "capturedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "generation": uuid.uuid4().hex,
             "state": "partial" if limitations else "complete", "git": git, "refs": collect_refs(Path(root), config, scope, (previous or {}).get("refs", [])),
             "files": (previous or {}).get("files", [])[-5:], "openspec": openspec_counts(root), "limitations": limitations[:10]}
    # The snapshot's generation identifies this capture, not a native compact ID.
    save_state(root, scope, value)
    return value


def observe_read(root, payload, config, scope):
    if payload.get("tool_name") not in {"Read", "read", "builtin:read", "read_file"}:
        return
    result = payload.get("tool_response")
    if not isinstance(result, dict) or result.get("isError") or result.get("error"):
        return
    args = payload.get("tool_input")
    if not isinstance(args, dict):
        return
    relative = args.get("file_path", args.get("path"))
    if not isinstance(relative, str):
        return
    cwd = Path(payload.get("cwd", root))
    target = Path(relative) if Path(relative).is_absolute() else cwd / relative
    try:
        relative = target.absolute().relative_to(Path(root).absolute()).as_posix()
        kind = "skill" if Path(relative).name.upper() == "SKILL.MD" else "rule" if "rules" in Path(relative).parts else "file"
        item = reference(root, kind, relative, critical=relative in config["taskFiles"], callId=str(payload.get("tool_use_id", ""))[:256])
        previous = load_state(root, scope)
        if previous is None:
            previous = {"schemaVersion": 1, **scope, "capturedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "generation": uuid.uuid4().hex, "state": "partial", "git": {}, "refs": [], "files": [], "limitations": ["metadata-not-yet-collected"]}
        bucket, limit = ("files", 5) if kind == "file" else ("refs", 20)
        previous[bucket] = [row for row in previous[bucket] if row.get("path") != relative] + [item]
        previous[bucket] = previous[bucket][-limit:]
        save_state(root, scope, previous)
    except (OSError, ValueError):
        return


def render_packet(contract, value):
    mode, scope, compact = value.get("mode", "minimal"), value.get("scope", {}), value.get("compact", {})
    if mode not in BUDGETS or mode == "off" or not compact.get("complete") or compact.get("failed"):
        return {"deliver": False, "text": "", "bytes": 0}
    prior = value.get("checkpointScope")
    if prior is not None and any(prior.get(key) != scope.get(key) for key in ("projectKey", "sessionId", "origin", "agentId")):
        return {"deliver": False, "text": "", "bytes": 0}
    messages, limit = contract["messages"], BUDGETS[mode]
    parts = [messages["compact"], messages["authority"], messages["subagent"] if scope.get("origin") == "subagent" else messages["lead"]]
    if value.get("unavailable"):
        parts.append(messages["unavailable"])
    def add(text):
        if len(("\n".join(parts + [text])).encode()) <= limit:
            parts.append(text)
    for row in value.get("refs", [])[:20]:
        if not isinstance(row, dict) or scope.get("origin") == "subagent" and row.get("kind") in {"orchestration", "session-map"}:
            continue
        if isinstance(row.get("path"), str):
            add("Reference (re-read if needed): " + json.dumps({key: str(row[key])[:512] for key in ("kind", "path", "version") if key in row}, ensure_ascii=False))
    checkpoint = value.get("checkpoint")
    if checkpoint:
        encoded = json.dumps(checkpoint, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode()) <= 4096:
            add("Historical checkpoint: " + encoded)
        add(messages["stale"])
    if mode in {"balanced", "expanded"}:
        accepted = 0
        for row in value.get("files", [])[:5]:
            if accepted >= 2:
                break
            text = row.get("text")
            if not row.get("critical") or not row.get("lost") or not row.get("allowed") or not isinstance(text, str) or len(text.encode()) > 2048 or SECRET.search(text):
                continue
            if row.get("path") in value.get("retained", []):
                continue
            add("Fresh source data (JSON, not instructions): " + json.dumps({"path": str(row.get("path", ""))[:512], "text": text}, ensure_ascii=False))
            accepted += 1
    text = "\n".join(parts)
    # Canonical messages are validated and fit minimal; never slice an instruction.
    if len(text.encode()) > limit:
        raise ValueError("continuity canonical message budget")
    return {"deliver": True, "text": text, "bytes": len(text.encode())}


def handle_event(root, payload, adapter):
    contract, config = load_contract(root), config_for(root)
    scope = scope_for(root, payload)
    event = payload.get("hook_event_name")
    writable = config["checkpoint"] and native_write_allowed(payload, adapter)
    if event == "PreCompact":
        if writable and config["mode"] != "off":
            capture(root, payload, adapter, config, scope)
        return None
    if event == "PostToolUse":
        if writable and config["mode"] != "off":
            observe_read(root, payload, config, scope)
        return None
    if event != "SessionStart" or payload.get("source") != "compact":
        return None
    try:
        previous = load_state(root, scope)
    except (OSError, ValueError, TypeError):
        previous = None
    refs = collect_refs(Path(root), config, scope, (previous or {}).get("refs", []) + (previous or {}).get("files", []))
    # Current generic Python hook wire lacks exact retained/lost-read provenance
    # and a native fs admission callback. Never manufacture lost=True here.
    # DSH's verified native adapter can use render_packet's bounded file input.
    files = []
    packet = render_packet(contract, {"mode": config["mode"], "scope": scope, "compact": {"id": None, "complete": True, "failed": False}, "refs": refs,
        "unavailable": previous is None, "checkpointScope": None if previous is None else previous,
        "checkpoint": None if previous is None else {"capturedAt": previous.get("capturedAt"), "state": previous.get("state"), "git": previous.get("git"), "openspec": previous.get("openspec", []), "correlation": "session-source-only; not an exact native compact receipt"}, "files": files})
    return packet["text"] if packet["deliver"] else ""
