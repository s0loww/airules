#!/usr/bin/env python3
"""Build a deterministic embedded airules package for DSH.

The package contains policy content only.  MCP endpoints, credentials and
machine-local bindings deliberately remain outside the artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


PACKAGE_ID = "airules-dsh-rulepack"
SCHEMA_VERSION = 1
COMPOSITION = {
    "stack": "1c",
    "project_layer": "common",
    "profile": "public",
    "target": "dsh-deepseek",
}
OVERLAY_PRECEDENCE = [
    "embedded-rulepack",
    "recipient-profile",
    "project-overlay",
    "machine-local-override",
]
LOGICAL_MCP_ROLES = ["code-facade", "memory", "project-data", "qa"]
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]*$")

DEFAULT_VALUES = {
    "PROJECT_ID": "embedded",
    "PROJECT_NAME": "Embedded airules policy",
    "STACK": "1c",
    "SOURCE_OF_TRUTH": "the source tree declared by the active project",
    "PRIMARY_CODE_DIR": "project-defined",
    "MCP_ORDER": "project binding; no bundled endpoints",
    "DISABLED_MCP": "all unbound logical roles",
    "PREFIX": "project-defined",
    "LANGUAGE_POLICY": "Russian for user-facing text; API and code identifiers unchanged",
}


class RulepackError(ValueError):
    pass


def _load_dsh_renderer(source: Path):
    path = source / "targets" / "dsh" / "deepseek" / "render.py"
    if not path.is_file():
        raise RulepackError("DSH renderer not found: {0}".format(path))
    spec = importlib.util.spec_from_file_location("airules_dsh_renderer", path)
    if spec is None or spec.loader is None:
        raise RulepackError("cannot load DSH renderer: {0}".format(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8", newline="\n")


def _write_json(path: Path, value: Any) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_state(source: Path) -> Dict[str, Any]:
    def run(*args: str) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=str(source), capture_output=True, text=True, encoding="utf-8"
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""

    return {
        "revision": run("rev-parse", "HEAD"),
        "dirty": bool(run("status", "--porcelain")),
    }


def _package_path(text: str) -> str:
    """Convert project-layout references produced by the DSH renderer."""
    return text.replace(".dsh/rules-1c/", "rules/").replace(".dsh/skills/", "skills/")


def _copy_rules(source: Path, stage: Path, renderer: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    bodies, meta, overrides = renderer.collect_rules(source, source, {})
    if overrides:
        raise RulepackError("embedded baseline unexpectedly contains project rule overrides")
    inventory: List[Dict[str, Any]] = []
    for rule_id in sorted(bodies):
        target = stage / "rules" / (rule_id + ".md")
        _write_text(target, _package_path(bodies[rule_id]))
        kind, description = meta[rule_id]
        inventory.append({
            "id": rule_id,
            "path": "rules/{0}.md".format(rule_id),
            "sha256": _sha256(target),
            "kind": kind,
            "description": description,
        })
    return inventory, meta


def _role_source(source: Path, role_id: str) -> Path:
    overlay = source / "overlays" / "1c" / "agents" / (role_id + ".md")
    if overlay.is_file():
        return overlay
    core = source / "core" / "agents" / "roles" / (role_id + ".md")
    if core.is_file():
        return core
    raise RulepackError("role body not found: {0}".format(role_id))


def _copy_roles(source: Path, stage: Path, renderer: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    roles = renderer.parse_roles(source)
    inventory: List[Dict[str, Any]] = []
    for role in sorted(roles, key=lambda row: row["role"]):
        role_id = role["role"]
        target = stage / "roles" / (role_id + ".md")
        text = renderer.transform_paths(_read_text(_role_source(source, role_id)))
        _write_text(target, _package_path(text))
        inventory.append({
            "id": role_id,
            "path": "roles/{0}.md".format(role_id),
            "sha256": _sha256(target),
            "tier": role["tier"],
            "effort": role["effort"],
            "purpose": role["purpose"],
            "registration_status": "prompt-adapter",
        })
    return inventory, roles


def _copy_skills(source: Path, stage: Path, renderer: Any) -> List[Dict[str, Any]]:
    scratch = stage / ".skill-stage"
    names, _ = renderer.copy_skills(source, scratch)
    rendered = scratch / ".dsh" / "skills"
    destination = stage / "skills"
    if rendered.is_dir():
        shutil.move(str(rendered), str(destination))
    shutil.rmtree(scratch, ignore_errors=True)

    inventory: List[Dict[str, Any]] = []
    for name in sorted(names):
        entry = destination / name / "SKILL.md"
        if not entry.is_file():
            raise RulepackError("rendered skill lacks SKILL.md: {0}".format(name))
        files = sorted(path for path in (destination / name).rglob("*") if path.is_file())
        inventory.append({
            "id": name,
            "path": "skills/{0}/SKILL.md".format(name),
            "sha256": _sha256(entry),
            "files": len(files),
        })
    return inventory


def _write_contract(
    source: Path,
    stage: Path,
    renderer: Any,
    meta: Mapping[str, Tuple[str, str]],
    roles: List[Dict[str, str]],
) -> None:
    rendered = renderer.render_agents(
        source, DEFAULT_VALUES, renderer.render_index(meta), roles
    )
    rendered = _package_path(rendered)
    rendered = rendered.replace(
        "Project-owned facts, access policy and verification bindings live in `USER-RULES.md`.",
        "Project facts and local overrides are optional and live in the active project overlay.",
    )
    rendered = rendered.replace(
        "Rule bodies live in `rules/` and are read via Read **when they match the\n"
        "task**. Do **not** preload rules — neither in bulk \"for context\" nor as a\n"
        "list at session start.",
        "Rule bodies are embedded in the DSH rulepack and are loaded through the\n"
        "runtime tool `airules_rule` **when they match the task**. Call it without\n"
        "`id` only to list available rules; call it with `{\"id\":\"<rule-id>\"}` to\n"
        "load one rule. Do **not** preload rules — neither in bulk \"for context\"\n"
        "nor as a list at session start.",
    )
    rendered = re.sub(
        r"`rules/([A-Za-z0-9_-]+)\.md`",
        lambda match: "`{0}` via `airules_rule` with `{{\"id\":\"{0}\"}}`".format(match.group(1)),
        rendered,
    )
    _write_text(stage / "contract" / "AGENTS.bundle.md", rendered)


def _write_testing_default(stage: Path) -> None:
    _write_json(stage / "testing" / "default.json", {
        "schema_version": 1,
        "id": "default",
        "policy": "project-overridable",
        "checks": [
            {"id": "doctor", "required": False, "binding": "project-defined"},
            {"id": "analyze", "required": True, "binding": "project-defined"},
            {"id": "deploy", "required": False, "binding": "project-defined"},
            {"id": "test", "required": True, "binding": "project-defined"},
        ],
        "mutations": {
            "test_contour_required": True,
            "production_requires_explicit_approval": True,
        },
    })


def _file_identity(relative: str) -> Tuple[str, str]:
    parts = relative.split("/")
    if parts[0] == "rules":
        return "rule", Path(parts[-1]).stem
    if parts[0] == "roles":
        return "role", Path(parts[-1]).stem
    if parts[0] == "skills":
        return "skill", parts[1]
    if parts[0] == "testing":
        return "testing", Path(parts[-1]).stem
    return "contract", "root-contract"


def _managed_files(stage: Path) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for path in sorted(candidate for candidate in stage.rglob("*") if candidate.is_file()):
        relative = path.relative_to(stage).as_posix()
        if relative == "manifest.json":
            continue
        kind, artifact_id = _file_identity(relative)
        result[relative] = {
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
            "kind": kind,
            "id": artifact_id,
        }
    return result


def _assert_portable(stage: Path, source: Path) -> None:
    source_marker = str(source.resolve()).replace("\\", "/").lower()
    forbidden_names = {".mcp.json", ".dev.env", ".env", "credentials.json", ".credentials.yaml"}
    for path in (candidate for candidate in stage.rglob("*") if candidate.is_file()):
        if path.name.lower() in forbidden_names:
            raise RulepackError("local configuration leaked into rulepack: {0}".format(path))
        if path.suffix.lower() not in {".md", ".json", ".txt", ".yaml", ".yml", ".ps1", ".py", ".js", ".mjs"}:
            continue
        text = _read_text(path).replace("\\", "/").lower()
        if source_marker and source_marker in text:
            raise RulepackError("source machine path leaked into rulepack: {0}".format(path))
    manifest = json.loads(_read_text(stage / "manifest.json"))
    if set(manifest["mcp"]) != {"mode", "logical_roles"}:
        raise RulepackError("manifest.mcp may contain only mode and logical_roles")
    serialized = json.dumps(manifest["mcp"], ensure_ascii=False).lower()
    for token in ("url", "command", "headers", "token", "secret", "api_key", "apikey", "env"):
        if token in serialized:
            raise RulepackError("forbidden MCP binding data in manifest: {0}".format(token))


def _enforce_clean_source(state: Mapping[str, Any], require_clean: bool) -> None:
    if require_clean and state.get("dirty"):
        raise RulepackError("release build requires a clean source tree")


def build(
    source: Path,
    output: Path,
    version: Optional[str],
    require_clean: bool = False,
) -> Dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    if not (source / "VERSION").is_file():
        raise RulepackError("not an airules source tree: {0}".format(source))
    if output.exists():
        raise RulepackError("output already exists; use a fresh directory: {0}".format(output))
    package_version = version or _read_text(source / "VERSION").strip()
    if not VERSION_RE.fullmatch(package_version):
        raise RulepackError("invalid rulepack version: {0}".format(package_version))
    state = _git_state(source)
    _enforce_clean_source(state, require_clean)

    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".rulepack-", dir=str(output.parent)))
    renderer = _load_dsh_renderer(source)
    try:
        rule_inventory, meta = _copy_rules(source, stage, renderer)
        role_inventory, roles = _copy_roles(source, stage, renderer)
        skill_inventory = _copy_skills(source, stage, renderer)
        _write_contract(source, stage, renderer, meta, roles)
        _write_testing_default(stage)
        # Canonical continuity policy/data only; native DSH owns the executor.
        continuity = stage / "contract" / "continuity"
        continuity.mkdir(parents=True)
        for name in ("contract.json", "checkpoint.schema.json", "fixtures.json", "README.md"):
            shutil.copy2(source / "core" / "tools" / "continuity" / name, continuity / name)
        files = _managed_files(stage)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "package": {"id": PACKAGE_ID, "version": package_version},
            "source": {
                "revision": state["revision"],
                "dirty": state["dirty"],
            },
            "registration_status": {
                "rules": "lazy-adapter-required",
                "roles": "prompt-adapter",
                "skills": "native",
                "testing": "declarative-only",
            },
            "composition": COMPOSITION,
            "overlay_precedence": OVERLAY_PRECEDENCE,
            "mcp": {"mode": "logical-only", "logical_roles": LOGICAL_MCP_ROLES},
            "counts": {
                "files": len(files),
                "rules": len(rule_inventory),
                "roles": len(role_inventory),
                "skills": len(skill_inventory),
            },
            "inventories": {
                "rules": rule_inventory,
                "roles": role_inventory,
                "skills": skill_inventory,
            },
            "files": files,
        }
        _write_json(stage / "manifest.json", manifest)
        _assert_portable(stage, source)
        os.replace(str(stage), str(output))
        return manifest
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="build an embedded airules DSH rulepack")
    result.add_argument("--source", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--version")
    result.add_argument(
        "--require-clean",
        action="store_true",
        help="refuse a release artifact when the source Git tree is dirty",
    )
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    try:
        manifest = build(args.source, args.output, args.version, args.require_clean)
        print(json.dumps({
            "status": "built",
            "output": str(args.output.resolve()),
            "package": manifest["package"],
            "counts": manifest["counts"],
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, RulepackError, ValueError, json.JSONDecodeError) as exc:
        print("rulepack: ERROR: {0}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
