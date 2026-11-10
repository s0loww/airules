#!/usr/bin/env python3
"""Contract tests for the embedded, secret-free DSH rulepack."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Iterable


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "targets" / "dsh" / "rulepack" / "build.py"
VERIFIER = ROOT / "targets" / "dsh" / "rulepack" / "verify.py"
CONTRACTS = ROOT / "targets" / "dsh" / "contracts"
MANIFEST_SCHEMA = CONTRACTS / "rulepack-manifest.schema.json"
CAPABILITY_SCHEMA = CONTRACTS / "capability-registry.schema.json"
CAPABILITY_REGISTRY = CONTRACTS / "1c-airules.json"
ADAPTED_CORE_SKILLS = {"handoff", "skill-maintainer", "security-baseline", "architecture-evolution", "technical-debt", "memory-workspace"}
ADAPTED_ONEC_SKILLS = {
    "1c-business-tests", "1c-ui-regression", "1c-verify-project",
    "1c-repository-manage", "1c-ai-merge", "v8unpack-cf", "1c-element",
}


def source_skill_ids():
    return {path.parent.name for base in (ROOT / "core" / "skills", ROOT / "overlays" / "1c" / "skills", ROOT / "targets" / "dsh" / "skills")
            for path in base.glob("*/SKILL.md")}

EXPECTED_PRECEDENCE = [
    "embedded-rulepack",
    "recipient-profile",
    "project-overlay",
    "machine-local-override",
]
EXPECTED_REQUIRED_CAPABILITIES = {
    "desktop.core",
    "development.core",
    "onec.local",
    "onec.project-settings",
    "project-wizard.neutral",
    "mcp.manager",
    "policy.airules",
    "memory.project",
    "orchestration.airules",
}
CONNECTION_KEYS = {
    "url",
    "uri",
    "endpoint",
    "command",
    "args",
    "env",
    "headers",
    "token",
    "api_key",
    "apikey",
    "secret",
    "password",
}
WINDOWS_ABSOLUTE = re.compile(r"(?i)(?:^|[\s\"'])(?:[a-z]:[\\/]|\\\\)")
WEB_URL = re.compile(r"(?i)\bhttps?://")


def read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise AssertionError("{0} must contain a JSON object".format(path))
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nested_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).lower()
            yield from nested_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_keys(child)


def validate_with_jsonschema(instance: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """Use jsonschema when available; core invariants are also checked below."""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(instance=instance, schema=schema)


def tree_bytes(root: Path) -> Dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class CapabilityRegistryTests(unittest.TestCase):
    def test_registry_is_logical_only_and_schema_valid(self) -> None:
        schema = read_json(CAPABILITY_SCHEMA)
        registry = read_json(CAPABILITY_REGISTRY)
        validate_with_jsonschema(registry, schema)

        self.assertEqual("1c-airules", registry["id"])
        required = registry["capabilities"]["required"]
        optional = registry["capabilities"]["optional"]
        self.assertTrue(EXPECTED_REQUIRED_CAPABILITIES.issubset(required))
        self.assertFalse(set(required) & set(optional))
        self.assertEqual(
            {"policy": "airules", "roles": "airules", "mcp": "airules", "verification": "airules"},
            registry["ownership"],
        )

        mcp = registry["mcp"]
        self.assertEqual("logical-only", mcp["mode"])
        self.assertIs(False, mcp["bindings_embedded"])
        roles = [item["role"] for item in mcp["logical_roles"]]
        self.assertEqual(len(roles), len(set(roles)))
        self.assertFalse(CONNECTION_KEYS & set(nested_keys(mcp)))
        serialized = json.dumps(mcp, ensure_ascii=False)
        self.assertIsNone(WEB_URL.search(serialized))
        self.assertIsNone(WINDOWS_ABSOLUTE.search(serialized))


class EmbeddedRulepackTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        if not BUILDER.is_file() or not VERIFIER.is_file():
            raise unittest.SkipTest("rulepack builder is being implemented in parallel")

    @staticmethod
    def build(output: Path) -> None:
        subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--source",
                str(ROOT),
                "--output",
                str(output),
                "--version",
                "test.1",
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

    def test_build_is_deterministic_and_verifiable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="airules-rulepack-test-") as temporary:
            base = Path(temporary)
            first, second = base / "first", base / "second"
            self.build(first)
            self.build(second)

            self.assertEqual(tree_bytes(first), tree_bytes(second))
            subprocess.run(
                [sys.executable, str(VERIFIER), "--output", str(first)],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )

            manifest = read_json(first / "manifest.json")
            schema = read_json(MANIFEST_SCHEMA)
            validate_with_jsonschema(manifest, schema)

            self.assertEqual(EXPECTED_PRECEDENCE, manifest["overlay_precedence"])
            self.assertEqual("logical-only", manifest["mcp"]["mode"])
            self.assertFalse(CONNECTION_KEYS & set(nested_keys(manifest["mcp"])))
            self.assertEqual("prompt-adapter", manifest["registration_status"]["roles"])
            self.assertEqual("declarative-only", manifest["registration_status"]["testing"])

            files = manifest["files"]
            self.assertNotIn("manifest.json", files)
            self.assertEqual(len(files), manifest["counts"]["files"])
            for relative, record in files.items():
                path = first / Path(relative)
                self.assertTrue(path.is_file(), relative)
                self.assertEqual(record["sha256"], sha256(path), relative)
                self.assertEqual(record["bytes"], path.stat().st_size, relative)

            inventories = manifest["inventories"]
            expected_counts = {"rules": 55, "roles": 13, "skills": len(source_skill_ids())}
            for kind, expected in expected_counts.items():
                rows = inventories[kind]
                ids = [item["id"] for item in rows]
                self.assertEqual(expected, len(rows), kind)
                self.assertEqual(expected, manifest["counts"][kind], kind)
                self.assertEqual(len(ids), len(set(ids)), kind)
                self.assertEqual(ids, sorted(ids), kind)
                for item in rows:
                    artifact = first / Path(item["path"])
                    self.assertTrue(artifact.is_file(), item["path"])
                    self.assertEqual(item["sha256"], sha256(artifact), item["path"])

            skill_ids = {item["id"] for item in inventories["skills"]}
            self.assertEqual(source_skill_ids(), skill_ids)
            self.assertTrue((ADAPTED_CORE_SKILLS | ADAPTED_ONEC_SKILLS).issubset(skill_ids))
            self.assertEqual({
                "openspec-propose", "openspec-apply-change", "openspec-update",
                "openspec-sync", "openspec-archive-change", "openspec-explore",
            }, {name for name in skill_ids if name.startswith("openspec-")})
            self.assertFalse(any(name.startswith("opsx-") for name in skill_ids))

            contract = (first / "contract" / "AGENTS.bundle.md").read_text(encoding="utf-8")
            self.assertIn("`airules_rule`", contract)
            self.assertIn("Call it without\n`id` only to list available rules", contract)
            self.assertNotRegex(contract, r"`rules/[A-Za-z0-9_-]+\.md`")
            self.assertNotIn("read via Read", contract)
            for item in inventories["rules"]:
                self.assertIn(
                    '`{{"id":"{0}"}}`'.format(item["id"]),
                    contract,
                )

            # JSON control-plane artifacts must be portable and connection-free.
            for relative in ("manifest.json", "testing/default.json"):
                text = (first / relative).read_text(encoding="utf-8")
                self.assertIsNone(WEB_URL.search(text), relative)
                self.assertIsNone(WINDOWS_ABSOLUTE.search(text), relative)
            self.assertFalse(CONNECTION_KEYS & set(nested_keys(manifest)))

    def test_continuity_policy_and_oracles_are_canonical_data(self) -> None:
        with tempfile.TemporaryDirectory(prefix="airules-continuity-pack-") as temporary:
            output = Path(temporary) / "pack"
            self.build(output)
            manifest = read_json(output / "manifest.json")
            for name in ("contract.json", "checkpoint.schema.json", "fixtures.json", "README.md"):
                relative = "contract/continuity/" + name
                self.assertIn(relative, manifest["files"])
                self.assertEqual((ROOT / "core/tools/continuity" / name).read_bytes(), (output / relative).read_bytes())
                self.assertEqual("contract", manifest["files"][relative]["kind"])

    def test_builder_refuses_nonempty_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="airules-rulepack-conflict-") as temporary:
            output = Path(temporary) / "output"
            output.mkdir()
            (output / "user-file.txt").write_text("preserve\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--source",
                    str(ROOT),
                    "--output",
                    str(output),
                    "--version",
                    "test.1",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("preserve\n", (output / "user-file.txt").read_text(encoding="utf-8"))

    def test_release_gate_refuses_dirty_source_state(self) -> None:
        spec = importlib.util.spec_from_file_location("airules_rulepack_builder_test", BUILDER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaisesRegex(module.RulepackError, "requires a clean source tree"):
            module._enforce_clean_source({"dirty": True}, True)
        module._enforce_clean_source({"dirty": True}, False)
        module._enforce_clean_source({"dirty": False}, True)


if __name__ == "__main__":
    unittest.main()
