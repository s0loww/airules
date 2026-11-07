#!/usr/bin/env python3
"""Verify hashes, inventories and portability of an embedded rulepack."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("JSON object expected: {0}".format(path))
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(output: Path) -> List[str]:
    failures: List[str] = []
    output = output.resolve()
    manifest_path = output / "manifest.json"
    if not manifest_path.is_file():
        return ["manifest.json is missing"]
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != 1:
        failures.append("unsupported schema_version")
    if manifest.get("package", {}).get("id") != "airules-dsh-rulepack":
        failures.append("unexpected package id")

    files = manifest.get("files")
    if not isinstance(files, dict):
        return failures + ["manifest.files must be an object"]
    actual = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*") if path.is_file() and path.name != "manifest.json"
    }
    declared = set(files)
    for relative in sorted(declared - actual):
        failures.append("missing file: {0}".format(relative))
    for relative in sorted(actual - declared):
        failures.append("undeclared file: {0}".format(relative))
    for relative in sorted(actual & declared):
        path = output / relative
        record = files[relative]
        if not isinstance(record, dict):
            failures.append("invalid file record: {0}".format(relative))
            continue
        if sha256(path) != record.get("sha256"):
            failures.append("hash mismatch: {0}".format(relative))
        if path.stat().st_size != record.get("bytes"):
            failures.append("size mismatch: {0}".format(relative))

    inventories = manifest.get("inventories", {})
    for kind in ("rules", "roles", "skills"):
        rows = inventories.get(kind)
        if not isinstance(rows, list):
            failures.append("inventories.{0} must be a list".format(kind))
            continue
        ids = [row.get("id") for row in rows if isinstance(row, dict)]
        if len(ids) != len(rows) or ids != sorted(ids) or len(ids) != len(set(ids)):
            failures.append("inventories.{0} must have sorted unique ids".format(kind))
        for row in rows:
            if not isinstance(row, dict) or row.get("path") not in declared:
                failures.append("invalid {0} inventory path: {1}".format(kind, row))
                continue
            if row.get("sha256") != files[row["path"]].get("sha256"):
                failures.append("inventory hash mismatch: {0}".format(row["path"]))

    counts = manifest.get("counts", {})
    expected_counts = {
        "files": len(files),
        "rules": len(inventories.get("rules", [])),
        "roles": len(inventories.get("roles", [])),
        "skills": len(inventories.get("skills", [])),
    }
    if counts != expected_counts:
        failures.append("counts mismatch: expected {0}".format(expected_counts))

    contract_path = output / "contract" / "AGENTS.bundle.md"
    if contract_path.is_file():
        contract = contract_path.read_text(encoding="utf-8-sig")
        if re.search(r"\{\{[A-Za-z0-9_]+\}\}", contract):
            failures.append("contract has unresolved placeholders")
        references = set(re.findall(r"`rules/([A-Za-z0-9_-]+)\.md`", contract))
        missing = sorted(rule_id for rule_id in references if not (output / "rules" / (rule_id + ".md")).is_file())
        if missing:
            failures.append("contract references missing rules: " + ", ".join(missing))

    mcp = manifest.get("mcp")
    if not isinstance(mcp, dict) or set(mcp) != {"mode", "logical_roles"} or mcp.get("mode") != "logical-only":
        failures.append("mcp must be logical-only and contain only mode/logical_roles")
    mcp_text = json.dumps(mcp, ensure_ascii=False).lower()
    if any(token in mcp_text for token in ("url", "command", "headers", "token", "secret", "api_key", "apikey", "env")):
        failures.append("mcp contains binding or secret data")

    for relative in actual:
        lowered = relative.lower()
        if lowered.endswith((".env", ".mcp.json", ".credentials.yaml")):
            failures.append("local configuration present: {0}".format(relative))
    return failures


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="verify an embedded airules DSH rulepack")
    result.add_argument("--output", type=Path, required=True)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    try:
        failures = verify(args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("rulepack verify: ERROR: {0}".format(exc), file=sys.stderr)
        return 1
    if failures:
        for failure in failures:
            print("FAIL: " + failure)
        return 1
    manifest = read_json(args.output / "manifest.json")
    print("PASS {0} {1}: {2}".format(
        manifest["package"]["id"], manifest["package"]["version"], manifest["counts"]
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
