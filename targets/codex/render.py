#!/usr/bin/env python3
"""Render and transactionally install the Codex target (Python 3.11+, stdlib).

Shared content is always read from the current canonical distribution. Runtime
formats reuse the reviewed separate Codex port; that checkout is not required.
No model, MCP connection, service, shell helper or client setting is executed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import urlsplit
import uuid

MANIFEST = ".airules-codex-manifest.json"
KINDS = ("invariant", "case", "recipe", "process", "router")
REQUIRED = ("PROJECT_ID", "PROJECT_NAME", "STACK", "SOURCE_OF_TRUTH", "PRIMARY_CODE_DIR", "PREFIX", "LANGUAGE_POLICY", "MCP_ORDER", "DISABLED_MCP", "BACKUP_DIR")
IGNORED = {".git", "node_modules", "__pycache__", ".env", ".dev.env", "agent-1c.json"}
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MCP_BEGIN = "# BEGIN AIRULES CODEX MCP\n"
MCP_END = "# END AIRULES CODEX MCP\n"


class RenderError(ValueError):
    pass


def read(path):
    return Path(path).read_text(encoding="utf-8-sig")


def put(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def data_hash(value):
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())


def load_json(path):
    value = json.loads(read(path))
    if not isinstance(value, dict):
        raise RenderError("JSON object required")
    return value


def checked_root(value):
    root = Path(os.path.abspath(value))
    for ancestor in [*reversed(root.parents), root]:
        if ancestor.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(ancestor)):
            raise RenderError("links are not supported")
    return root


def safe(root, rel, allow_root=False):
    root = checked_root(root)
    if not isinstance(rel, str) or "\\" in rel or ":" in rel or not rel or "\0" in rel:
        raise RenderError("portable relative path required")
    raw = PurePosixPath(rel)
    if raw.is_absolute() or any(x in ("", ".", "..") for x in rel.split("/")):
        raise RenderError("path traversal rejected")
    current = root
    for part in ["", *raw.parts]:
        current = current / part if part else current
        if current.is_symlink() or (current.exists() and current.is_file() and current.stat().st_nlink != 1):
            raise RenderError("links are not supported")
    if not allow_root and current == root:
        raise RenderError("root path rejected")
    try:
        current.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise RenderError("path escapes root") from exc
    return current


def object_fields(text):
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.S)
    fields = {}
    if not match:
        return fields, text
    for line in match[1].splitlines():
        key, sep, val = line.partition(":")
        if sep:
            val = val.strip()
            try:
                val = json.loads(val)
            except (ValueError, TypeError):
                val = val.strip("\"'")
            fields[key.strip()] = val
    return fields, text[match.end():]


def adapt(text):
    return text.replace(".claude/skills/", ".agents/skills/").replace(".claude/agents/", ".codex/agents/").replace("**AskUserQuestion tool**", "available question interface (or ask in chat)")


def expand(text, facts):
    for name, value in facts.items():
        if isinstance(value, str):
            text = text.replace("{{" + name + "}}", value)
    return re.sub(r"\{\{([A-Z][A-Z0-9_]*)\}\}", lambda m: "NOT CONFIGURED: " + m[1], text)


def files(root):
    result = {}
    for current, directories, names in os.walk(root, followlinks=False):
        directories.sort()
        for name in directories + names:
            path = Path(current) / name
            if path.is_symlink():
                raise RenderError("source or candidate link rejected")
        for name in sorted(names):
            path = Path(current) / name
            if not path.is_file() or path.stat().st_nlink != 1:
                raise RenderError("regular files required")
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def copy_tree(source, target):
    source = Path(source)
    if not source.exists():
        return
    if source.is_symlink():
        raise RenderError("source link rejected")
    for current, directories, names in os.walk(source, followlinks=False):
        directories[:] = sorted(n for n in directories if n not in IGNORED)
        for name in directories + names:
            if (Path(current) / name).is_symlink():
                raise RenderError("source link rejected")
        for name in sorted(names):
            if name in IGNORED or name.endswith((".pyc", ".local.json")):
                continue
            src = Path(current) / name
            if not src.is_file() or src.stat().st_nlink != 1 or src.stat().st_size > 64 * 1024 * 1024:
                raise RenderError("source resource rejected")
            dest = Path(target) / src.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def composition(source, profile, stack):
    resolver = module(source / "ci/composition.py", "_airules_codex_composition")
    return resolver.resolve_composition(resolver.load_catalog(source, stack), "codex", profile, stack, "common")


def validate_bindings(bindings):
    allowed = {"placeholders", "models", "mcp_servers", "mcp_bindings"}
    if set(bindings) - allowed:
        raise RenderError("unsupported binding keys")
    facts = bindings.get("placeholders", {})
    if not isinstance(facts, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in facts.items()):
        raise RenderError("placeholders must be strings")
    if any(k not in facts for k in REQUIRED) or not ID.fullmatch(facts["PROJECT_ID"]) or not ID.fullmatch(facts["STACK"]):
        raise RenderError("required project facts are missing or invalid")
    if any(re.search(r"password|secret|credential|token", key, re.I) for key in facts):
        raise RenderError("secrets do not belong in project facts")
    safe(Path.cwd(), facts["BACKUP_DIR"].rstrip("/"))
    servers = bindings.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise RenderError("mcp_servers must be an object")
    for name, server in servers.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or not isinstance(server, dict):
            raise RenderError("MCP server identity invalid")
        if bool(server.get("url")) == bool(server.get("command")):
            raise RenderError("MCP needs exactly one URL or command")
        allowed_server = {"url", "command", "args", "env_vars", "bearer_token_env_var", "env_http_headers", "enabled_tools", "disabled_tools", "startup_timeout_sec", "tool_timeout_sec"}
        if set(server) - allowed_server:
            raise RenderError("unsupported MCP fields; use environment references")
        parsed = urlsplit(server.get("url", ""))
        if server.get("url") and (parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise RenderError("MCP URL must not embed credentials, queries or fragments")
        if "command" in server and (not isinstance(server["command"], str) or not server["command"].strip()):
            raise RenderError("invalid MCP command")
        for key in ("args", "env_vars", "enabled_tools", "disabled_tools"):
            if key in server and (not isinstance(server[key], list) or any(not isinstance(v, str) or "\0" in v for v in server[key])):
                raise RenderError("invalid MCP list")
        if any(re.search(r"password|token|secret|\bsk-[A-Za-z0-9_-]{16,}", arg, re.I) for arg in server.get("args", [])):
            raise RenderError("credential-bearing MCP arguments rejected")
        for key in ("bearer_token_env_var",):
            if key in server and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", server[key]):
                raise RenderError("invalid environment reference")
        for var in server.get("env_vars", []):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", var):
                raise RenderError("invalid environment reference")
        headers = server.get("env_http_headers", {})
        if not isinstance(headers, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v) for k, v in headers.items()):
            raise RenderError("invalid environment header reference")
        for key in ("startup_timeout_sec", "tool_timeout_sec"):
            if key in server and (type(server[key]) not in (int, float) or server[key] <= 0):
                raise RenderError("invalid MCP timeout")
    return facts


def render_mcp(servers):
    lines = [MCP_BEGIN.rstrip()]
    for name, server in sorted(servers.items()):
        section = "mcp_servers." + json.dumps(name)
        lines += ["", "[" + section + "]"]
        for key, value in server.items():
            if key != "env_http_headers":
                lines.append(key + " = " + json.dumps(value, ensure_ascii=False))
        if server.get("env_http_headers"):
            lines.append("[" + section + ".env_http_headers]")
            lines += [json.dumps(k) + " = " + json.dumps(v) for k, v in server["env_http_headers"].items()]
    lines.append(MCP_END.rstrip())
    result = "\n".join(lines) + "\n"
    tomllib.loads(result)
    return result


def roles(source):
    pattern = r"^\| ([a-z][a-z-]+) \| (\w+)(\*?) \| (\w+) \| (ro|rw) \| (\S+) \| (.+?) \|$"
    registry = []
    for name, tier, deep, effort, access, override, purpose in re.findall(pattern, read(source / "core/agents/ROLES.md"), re.M):
        row = dict(name=name, tier=tier, effort=effort, access=access, override=override, purpose=purpose, base=name)
        registry.append(row)
        if deep:
            registry.append(dict(row, name=name + "-deep", tier="high", effort="xhigh", purpose=purpose + " (raw-source analysis)"))
    if len(registry) < 1:
        raise RenderError("role registry empty")
    return registry


def render_roles(source, output, stack, bindings):
    mapping = load_json(source / "targets/codex/models.json")
    overrides = bindings.get("models", {})
    if not isinstance(overrides, dict) or set(overrides) - {"tiers", "efforts"}:
        raise RenderError("invalid model mapping override")
    for axis in ("tiers", "efforts"):
        if not isinstance(overrides.get(axis, {}), dict):
            raise RenderError("invalid model mapping override")
        mapping[axis].update(overrides.get(axis, {}))
    rows = []
    for role in roles(source):
        tier = role["override"] if role["override"] in mapping["tiers"] else role["tier"]
        model = mapping["tiers"].get(tier)
        effort = mapping["efforts"].get(role["effort"])
        if not isinstance(model, str) or not model.strip() or effort not in ("low", "medium", "high", "xhigh"):
            raise RenderError("invalid resolved model or effort")
        common = source / "core/agents/roles" / (role["base"] + ".md")
        domain = source / "overlays" / stack / "agents" / (role["base"] + ".md")
        body = object_fields(read(common))[1]
        if domain.exists():
            body += "\n\n" + object_fields(read(domain))[1]
        body += "\n\n## Execution boundary\n\nExecute the bounded task with the current tools. Collect completion of every started command. Project memory writes belong to the lead. "
        body += "Read-only role: return evidence to the lead without writing a report file or mutating data.\n" if role["access"] == "ro" else "Return evidence and the assigned handoff.\n"
        values = dict(name=role["name"], description=role["purpose"], developer_instructions=adapt(body))
        dynamic = role["base"] in mapping["dynamic_roles"]
        if not dynamic:
            values.update(model=model, model_reasoning_effort=effort)
        put(output / ".codex/agents" / (role["name"] + ".toml"), "\n".join(k + " = " + json.dumps(v, ensure_ascii=False) for k, v in values.items()) + "\n")
        rows.append({**role, "model": model, "resolved_effort": effort, "dynamic": dynamic})
    return rows


def git_source(source):
    def run(*args):
        proc = subprocess.run(["git", *args], cwd=source, capture_output=True, text=True, encoding="utf-8")
        return proc.stdout.strip() if proc.returncode == 0 else ""
    return {"revision": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain"))}


def build(source, project, output, bindings, profile="public"):
    source, project, output = map(checked_root, (source, project, output))
    source_area = output.relative_to(source).parts[0] if source in output.parents else None
    if output.exists() or output == source or source_area not in (None, "var") or output == project or project in output.parents:
        raise RenderError("use a fresh staging directory outside source and project")
    if not project.is_dir():
        raise RenderError("project directory required")
    facts = validate_bindings(bindings)
    stack = facts["STACK"]
    composed = composition(source, profile, stack)
    output.mkdir(parents=True)
    meta = {}
    try:
        for base in (source / "core/rules", source / "overlays" / stack / "rules"):
            for rule in sorted(base.glob("*.md")):
                fields, _ = object_fields(read(rule))
                if fields.get("kind") not in KINDS or not fields.get("description"):
                    raise RenderError("invalid rule metadata: " + rule.name)
                meta[rule.stem] = fields
                put(output / "rules" / rule.name, adapt(read(rule)))
        for base in (source / "core/tools", source / "overlays" / stack / "tools"):
            copy_tree(base, output / "tools")
        skill_names = set()
        for base in (source / "core/skills", source / "overlays" / stack / "skills"):
            for skill in sorted(base.glob("*/SKILL.md")):
                fields, _ = object_fields(read(skill))
                name = fields.get("name", skill.parent.name)
                if name != skill.parent.name or not ID.fullmatch(name) or not fields.get("description") or name in skill_names:
                    raise RenderError("invalid or duplicate skill: " + skill.parent.name)
                skill_names.add(name)
                dest = output / ".agents/skills" / name
                copy_tree(skill.parent, dest)
                # Preserve implementation bytes; only the installed routing text changes paths.
                put(dest / "SKILL.md", adapt(read(skill)))
        commands = []
        for base in (source / "core/commands", source / "overlays" / stack / "commands"):
            for command in sorted(base.glob("*.md")):
                fields, body = object_fields(read(command))
                name = fields.get("id", command.stem)
                if not isinstance(name, str) or not ID.fullmatch(name) or not fields.get("description") or name in skill_names:
                    raise RenderError("invalid or colliding command skill")
                skill_names.add(name)
                commands.append(name)
                put(output / ".agents/skills" / name / "SKILL.md", "---\nname: " + name + "\ndescription: " + json.dumps(fields["description"], ensure_ascii=False) + "\n---\n\n" + adapt(body))
        registry = render_roles(source, output, stack, bindings)
        index = []
        for kind in KINDS:
            index.append("\n**" + kind + "**\n")
            index.extend("- `rules/" + name + ".md` — " + fields["description"] for name, fields in sorted(meta.items()) if fields["kind"] == kind)
        table = ["| Role | Model / effort | Definition |", "| --- | --- | --- |"]
        table += ["| {name} | {model} / {resolved_effort} | {mode} |".format(**r, mode="dynamic launch" if r["dynamic"] else "fixed TOML") for r in registry]
        values = dict(facts, RULE_INDEX="\n".join(index), AGENTS_TABLE="\n".join(table))
        contract = adapt(expand(read(source / "core/templates/AGENTS.md"), values)) + "\n\n" + read(source / "targets/codex/contract.md")
        instruction_bytes = len(contract.encode("utf-8"))
        if instruction_bytes > 32768:
            raise RenderError("AGENTS.md exceeds the default 32768-byte Codex instruction budget; reduce the root contract before installing")
        put(output / "AGENTS.md", contract)
        for name in ("project-context.md", "testing-contour.md"):
            put(output / ".airules" / name, expand(read(source / "project-layer/common/templates" / name), facts))
        copy_tree(source / "project-template/openspec", output / "openspec")
        for file in (output / "openspec").rglob("*.md"):
            put(file, expand(read(file), facts))
        copy_tree(source / "core/hooks", output / ".codex/hooks")
        hook_root = source / "targets/codex/hooks"
        if not (hook_root / "config.py").is_file():
            raise RenderError("Codex hook configuration helper unavailable")
        helper = module(hook_root / "config.py", "_airules_codex_hook_config")
        for file in hook_root.glob("*.py"):
            if file.name != "config.py":
                dest = output / ".codex/hooks" / file.name
                shutil.copy2(file, dest)
        map_file = source / "overlays" / stack / "hooks/rules-map.json"
        if map_file.exists():
            shutil.copy2(map_file, output / ".codex/hooks/rules-map.json")
        put(output / ".codex/hooks.json", json.dumps(helper.render_config(), ensure_ascii=False, indent=2) + "\n")
        if bindings.get("mcp_servers"):
            put(output / ".codex/config.toml", render_mcp(bindings["mcp_servers"]))
        mcp_bindings = bindings.get("mcp_bindings", {})
        if not isinstance(mcp_bindings, dict):
            raise RenderError("mcp_bindings must be an object")
        missing = [row["role"] for row in composed["profile"].get("mcp", {}).get("logical_servers", []) if row.get("required") and mcp_bindings.get(row["role"]) not in bindings.get("mcp_servers", {})]
        manifest = {"schema_version": 1, "target": "codex", "version": read(source / "VERSION").strip(), "project_id": facts["PROJECT_ID"],
            "composition": composed, "source": git_source(source), "bindings_sha256": data_hash(bindings),
            "port_provenance": {"version": "0.13.0-dev.1", "upstream_version": "0.12.0", "upstream_commit": "05181aa", "scope": "runtime adapter only; canonical content from current source"},
            "counts": {"rules": len(meta), "agents": len(registry), "skills": len(skill_names), "canonical_skills": len(skill_names) - len(commands), "converted_commands": len(commands)},
            "converted_commands": commands, "instruction_budget": {"bytes": instruction_bytes, "default_max_bytes": 32768, "truncated": False}, "mcp_required_unbound": missing, "files": files(output)}
        manifest["integrity_sha256"] = data_hash(manifest)
        put(output / MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        verify(output)
        return manifest
    except BaseException:
        # Only the brand-new staging tree created above is removed.
        shutil.rmtree(output)
        raise


def manifest_valid(manifest):
    check = dict(manifest)
    expected = check.pop("integrity_sha256", None)
    if manifest.get("target") != "codex" or manifest.get("schema_version") != 1 or expected != data_hash(check):
        raise RenderError("manifest integrity rejected")
    if not isinstance(manifest.get("files"), dict) or any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value) for value in manifest["files"].values()):
        raise RenderError("invalid manifest files")
    for rel in manifest["files"]:
        if not isinstance(rel, str) or not artifact_path(rel):
            raise RenderError("file outside the Codex target artifact scope")


def artifact_path(rel):
    if rel in ("AGENTS.md", ".codex/hooks.json", ".codex/config.toml", ".airules/project-context.md", ".airules/testing-contour.md"):
        return True
    return bool(re.fullmatch(r"rules/[a-z0-9-]+\.md|\.codex/agents/[a-z0-9-]+\.toml", rel) or rel.startswith((".agents/skills/", ".codex/hooks/", "tools/", "openspec/")))


def verify(output):
    output = checked_root(output)
    manifest = load_json(safe(output, MANIFEST))
    manifest_valid(manifest)
    expected = manifest["files"]
    actual = files(output)
    actual.pop(MANIFEST, None)
    if actual != expected:
        raise RenderError("candidate file inventory or hashes changed")
    for rel in expected:
        safe(output, rel)
    for path in (output / ".codex/agents").glob("*.toml"):
        role = tomllib.loads(read(path))
        if not all(isinstance(role.get(key), str) and role[key] for key in ("name", "description", "developer_instructions")):
            raise RenderError("invalid native custom agent")
        if set(role) - {"name", "description", "developer_instructions", "model", "model_reasoning_effort"}:
            raise RenderError("unsupported custom-agent field")
    if (output / ".codex/config.toml").exists():
        tomllib.loads(read(output / ".codex/config.toml"))
    body = read(output / "AGENTS.md")
    refs = set(re.findall(r"`rules/([A-Za-z0-9_-]+)\.md`", body))
    if refs != {p.stem for p in (output / "rules").glob("*.md")} or "{{" in body or ".claude/skills/" in body:
        raise RenderError("instruction index, placeholders or runtime paths invalid")
    for role in (output / ".codex/agents").glob("*.toml"):
        if "| " + role.stem + " |" not in body:
            raise RenderError("native role missing from routing table")
    return manifest


def maybe_hash(path):
    return sha(path) if path.exists() and path.is_file() else None


def project_owned(rel):
    return rel.startswith("openspec/") or rel in (".airules/project-context.md", ".airules/testing-contour.md")


def plan(project, candidate):
    project, candidate = checked_root(project), checked_root(candidate)
    if project == candidate or candidate in project.parents or project in candidate.parents:
        raise RenderError("project and candidate must be separate")
    if (project / "core/rules").is_dir() and (project / "VERSION").is_file():
        raise RenderError("installing into a distribution checkout is not supported")
    manifest = verify(candidate)
    old_path = safe(project, MANIFEST)
    old = load_json(old_path) if old_path.exists() else None
    if old:
        manifest_valid(old)
        if old["project_id"] != manifest["project_id"]:
            raise RenderError("installed project identity differs")
    operations, preserved, conflicts = [], [], []
    if old and ".codex/config.toml" in old.get("files", {}) and ".codex/config.toml" not in manifest["files"]:
        conflicts.append("previously managed MCP needs an explicit reviewed removal")
    for rel, new_hash in manifest["files"].items():
        path = safe(project, rel)
        if path.exists() and not path.is_file():
            conflicts.append(rel)
            continue
        current = maybe_hash(path)
        if current and project_owned(rel):
            preserved.append(rel)
            continue
        content = (candidate / rel).read_bytes()
        if current == new_hash:
            continue
        tracked = old.get("files", {}).get(rel) if old else None
        if current and tracked != current:
            # Existing project config is not replaced: add only a disjoint block.
            if rel == ".codex/config.toml" and tracked is None:
                original = path.read_bytes()
                existing = tomllib.loads(original.decode("utf-8-sig"))
                incoming = tomllib.loads(content.decode("utf-8"))
                if MCP_BEGIN.encode() in original or set(existing.get("mcp_servers", {})) & set(incoming.get("mcp_servers", {})):
                    conflicts.append(rel)
                    continue
                content = original + (b"\n" if not original.endswith(b"\n") else b"") + content
                tomllib.loads(content.decode("utf-8-sig"))
            else:
                conflicts.append(rel)
                continue
        elif current and rel == ".codex/config.toml" and tracked:
            original = path.read_bytes()
            text = original.decode("utf-8-sig")
            if text.count(MCP_BEGIN.rstrip()) != 1 or text.count(MCP_END.rstrip()) != 1:
                conflicts.append(rel)
                continue
            start = text.index(MCP_BEGIN.rstrip()); end = text.index(MCP_END.rstrip()) + len(MCP_END.rstrip())
            content = (text[:start] + content.decode("utf-8").rstrip("\n") + text[end:]).encode("utf-8")
            if original.startswith(b"\xef\xbb\xbf"):
                content = b"\xef\xbb\xbf" + content
            tomllib.loads(content.decode("utf-8-sig"))
        operations.append({"path": rel, "before": current, "after": digest(content), "content": content})
    if manifest.get("mcp_required_unbound"):
        conflicts.append("required MCP roles: " + ", ".join(manifest["mcp_required_unbound"]))
    return {"manifest": manifest, "old": old, "operations": operations, "preserved": preserved, "conflicts": conflicts, "status": "blocked" if conflicts else "ready"}


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".airules-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def save_receipt(path, receipt):
    value = {key: item for key, item in receipt.items() if key != "integrity_sha256"}
    value["integrity_sha256"] = data_hash(value)
    atomic(path, (json.dumps(value, indent=2) + "\n").encode())


def owned_restore(path, expected, before):
    """Compensate only bytes still owned by this exact transaction."""
    current = maybe_hash(path)
    if current != expected:
        raise RenderError("concurrent edit preserved: " + str(path))
    if before is None:
        if path.exists():
            path.unlink()
    else:
        atomic(path, before)


def apply(project, candidate, backup_root, fail_after=None):
    project = checked_root(project)
    selected = plan(project, candidate)
    if selected["conflicts"]:
        raise RenderError("apply conflicts; no files written: " + ", ".join(selected["conflicts"]))
    backup_root = Path(backup_root).absolute()
    safe(backup_root, "preflight")
    if backup_root == project or backup_root == Path(candidate).resolve() or project in backup_root.parents or backup_root in project.parents or Path(candidate).resolve() in backup_root.parents or backup_root in Path(candidate).resolve().parents:
        raise RenderError("backup root rejected")
    backup = backup_root / ("codex-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex)
    backup.mkdir(parents=True)
    records = []
    for op in selected["operations"]:
        path = safe(project, op["path"])
        if maybe_hash(path) != op["before"]:
            raise RenderError("project changed after preflight")
        if op["before"]:
            saved = backup / "before" / op["path"]
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
        records.append({key: op[key] for key in ("path", "before", "after")})
    old_manifest = safe(project, MANIFEST)
    manifest_before = maybe_hash(old_manifest)
    if manifest_before:
        shutil.copy2(old_manifest, backup / "manifest.before.json")
    installed = dict(selected["manifest"])
    installed["files"] = dict(selected["old"].get("files", {}) if selected["old"] else {})
    for rel, value in selected["manifest"]["files"].items():
        if rel not in selected["preserved"]:
            installed["files"][rel] = value
    for op in selected["operations"]:
        installed["files"][op["path"]] = op["after"]
    for rel in selected["preserved"]:
        installed["files"].pop(rel, None)
    installed["integrity_sha256"] = data_hash({key: value for key, value in installed.items() if key != "integrity_sha256"})
    manifest_bytes = (json.dumps(installed, ensure_ascii=False, indent=2) + "\n").encode()
    receipt = {"schema_version": 1, "target": "codex", "project": str(project), "status": "prepared", "operations": records,
        "manifest_before": manifest_before, "manifest_after": digest(manifest_bytes)}
    save_receipt(backup / "receipt.json", receipt)
    written = []
    try:
        for op in selected["operations"]:
            path = safe(project, op["path"])
            if maybe_hash(path) != op["before"]:
                raise RenderError("project changed during apply")
            atomic(path, op["content"])
            written.append(op)
            if fail_after and len(written) == fail_after:
                raise RenderError("injected apply failure")
        if maybe_hash(old_manifest) != manifest_before:
            raise RenderError("installed manifest changed during apply")
        atomic(old_manifest, manifest_bytes)
        receipt["status"] = "applied"
        save_receipt(backup / "receipt.json", receipt)
    except BaseException as error:
        recovery = []
        for op in reversed(written):
            try:
                owned_restore(safe(project, op["path"]), op["after"], (backup / "before" / op["path"]).read_bytes() if op["before"] else None)
            except (OSError, RenderError):
                recovery.append(op["path"])
        current_manifest = maybe_hash(old_manifest)
        if current_manifest == digest(manifest_bytes):
            try:
                owned_restore(old_manifest, current_manifest, (backup / "manifest.before.json").read_bytes() if manifest_before else None)
            except (OSError, RenderError):
                recovery.append(MANIFEST)
        elif current_manifest != manifest_before:
            recovery.append(MANIFEST)
        receipt["status"] = "recovery-required" if recovery else "failed-restored"
        receipt["recovery_paths"] = recovery
        save_receipt(backup / "receipt.json", receipt)
        if recovery:
            raise RenderError("apply failed; concurrent edits or recovery errors preserved; inspect receipt: " + str(backup)) from error
        raise
    return {"status": "applied", "backup": str(backup), "operations": len(records), "preserved": selected["preserved"]}


def rollback(project, backup, fail_after=None):
    project, backup = checked_root(project), checked_root(backup)
    receipt = load_json(safe(backup, "receipt.json"))
    signature = receipt.pop("integrity_sha256", None)
    if signature != data_hash(receipt):
        raise RenderError("rollback receipt integrity rejected")
    if receipt.get("status") != "applied" or receipt.get("project") != str(project):
        raise RenderError("rollback receipt scope rejected")
    if not isinstance(receipt.get("operations"), list) or any(not isinstance(op, dict) or not isinstance(op.get("path"), str) or not artifact_path(op["path"]) for op in receipt["operations"]):
        raise RenderError("rollback artifact scope rejected")
    manifest = safe(project, MANIFEST)
    if maybe_hash(manifest) != receipt["manifest_after"]:
        raise RenderError("installed manifest changed after apply")
    for op in receipt["operations"]:
        if maybe_hash(safe(project, op["path"])) != op["after"]:
            raise RenderError("rollback would erase a local edit: " + op["path"])
        if op["before"] and maybe_hash(safe(backup, "before/" + op["path"])) != op["before"]:
            raise RenderError("rollback backup changed")
    if receipt["manifest_before"] and maybe_hash(safe(backup, "manifest.before.json")) != receipt["manifest_before"]:
        raise RenderError("rollback manifest backup changed")
    attempt = backup / ("rollback-" + uuid.uuid4().hex)
    attempt.mkdir()
    for op in receipt["operations"]:
        current = safe(project, op["path"])
        saved = safe(attempt, "after/" + op["path"])
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, saved)
        if sha(saved) != op["after"]:
            raise RenderError("project changed during rollback preflight")
    manifest_bytes = manifest.read_bytes()
    restored = []
    try:
        for op in reversed(receipt["operations"]):
            path = safe(project, op["path"])
            owned_restore(path, op["after"], (backup / "before" / op["path"]).read_bytes() if op["before"] else None)
            restored.append(op)
            if fail_after and len(restored) == fail_after:
                raise RenderError("injected rollback failure")
        owned_restore(manifest, receipt["manifest_after"], (backup / "manifest.before.json").read_bytes() if receipt["manifest_before"] else None)
        receipt["status"] = "rolled-back"
        save_receipt(backup / "receipt.json", receipt)
    except BaseException as error:
        recovery = []
        for op in reversed(restored):
            try:
                owned_restore(safe(project, op["path"]), op["before"], (attempt / "after" / op["path"]).read_bytes())
            except (OSError, RenderError):
                recovery.append(op["path"])
        current_manifest = maybe_hash(manifest)
        if current_manifest == receipt["manifest_before"]:
            try:
                owned_restore(manifest, current_manifest, manifest_bytes)
            except (OSError, RenderError):
                recovery.append(MANIFEST)
        elif current_manifest != receipt["manifest_after"]:
            recovery.append(MANIFEST)
        receipt["status"] = "recovery-required" if recovery else "applied"
        receipt["recovery_paths"] = recovery
        save_receipt(backup / "receipt.json", receipt)
        if recovery:
            raise RenderError("rollback failed; concurrent edits or recovery errors preserved; inspect receipt: " + str(backup)) from error
        raise
    return {"status": "rolled-back", "operations": len(receipt["operations"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    render = commands.add_parser("render")
    for name in ("source", "project", "bindings", "output"):
        render.add_argument("--" + name, type=Path, required=True)
    render.add_argument("--profile", default="public")
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--output", type=Path, required=True)
    for name in ("plan", "apply"):
        sub = commands.add_parser(name)
        sub.add_argument("--project", type=Path, required=True)
        sub.add_argument("--candidate", type=Path, required=True)
        if name == "apply":
            sub.add_argument("--backup-root", type=Path, required=True)
            sub.add_argument("--confirm", required=True)
    sub = commands.add_parser("rollback")
    sub.add_argument("--project", type=Path, required=True)
    sub.add_argument("--backup", type=Path, required=True)
    sub.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "render":
            m = build(args.source, args.project, args.output, load_json(args.bindings), args.profile)
            result = {"status": "staged", "counts": m["counts"], "mcp_required_unbound": m["mcp_required_unbound"]}
        elif args.action == "verify":
            result = {"status": "verified", "counts": verify(args.output)["counts"]}
        elif args.action == "plan":
            value = plan(args.project, args.candidate)
            result = {"status": value["status"], "operations": len(value["operations"]), "conflicts": value["conflicts"], "preserved": value["preserved"]}
        elif args.action == "apply":
            if args.confirm != "APPLY_CODEX":
                raise RenderError("apply confirmation required")
            result = apply(args.project, args.candidate, args.backup_root)
        else:
            if args.confirm != "ROLLBACK_CODEX":
                raise RenderError("rollback confirmation required")
            result = rollback(args.project, args.backup)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print("codex-target: ERROR: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
