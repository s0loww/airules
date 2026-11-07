#!/usr/bin/env python3
"""Offline native formatting, canonical resources and installer ownership."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("codex_target_render", ROOT / "targets/codex/render.py")
target = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(target)


class CodexTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="airules-codex-tests-")
        cls.base = Path(cls.workspace.name)
        cls.original = cls.base / "canonical-stage"
        cls.initial_project = cls.base / "initial-project"
        cls.initial_project.mkdir()
        cls.bindings = target.load_json(ROOT / "targets/codex/bindings.example.json")
        cls.manifest = target.build(ROOT, cls.initial_project, cls.original, cls.bindings)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=self.base)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.project = self.work / "project"
        self.project.mkdir()
        self.stage = self.work / "stage"
        shutil.copytree(self.original, self.stage)
        self.backups = self.work / "backups"

    def save(self, path, content):
        target.put(path, content)

    def reseal(self):
        value = target.load_json(self.stage / target.MANIFEST)
        inventory = target.files(self.stage)
        inventory.pop(target.MANIFEST)
        value["files"] = inventory
        value.pop("integrity_sha256")
        value["integrity_sha256"] = target.data_hash(value)
        self.save(self.stage / target.MANIFEST, json.dumps(value))
        return value

    def add_mcp(self):
        server = {"direct-code": {"url": "http://127.0.0.1:8101/mcp", "bearer_token_env_var": "CODE_MCP_AUTH", "env_http_headers": {"X-Project": "PROJECT_ID_ENV"}}}
        self.save(self.stage / ".codex/config.toml", target.render_mcp(server))
        self.reseal()

    def test_current_canonical_skills_and_every_resource_are_installed(self):
        expected = set()
        for base in (ROOT / "core/skills", ROOT / "overlays/1c/skills"):
            for skill in base.glob("*/SKILL.md"):
                expected.add(skill.parent.name)
                dest = self.stage / ".agents/skills" / skill.parent.name
                self.assertEqual(target.adapt(target.read(skill)), target.read(dest / "SKILL.md"))
                for source in skill.parent.rglob("*"):
                    if not source.is_file() or any(part in target.IGNORED for part in source.relative_to(skill.parent).parts):
                        continue
                    if source.name != "SKILL.md":
                        self.assertEqual(source.read_bytes(), (dest / source.relative_to(skill.parent)).read_bytes(), str(source))
        self.assertEqual(46, len(expected))
        self.assertEqual(46, self.manifest["counts"]["canonical_skills"])
        self.assertFalse((self.stage / ".agents/skills/creating-dsh-plugins").exists())
        self.assertFalse((self.stage / ".agents/skills/telegram").exists())

    def test_native_roles_table_and_dynamic_fixed_selection(self):
        mapping = target.load_json(ROOT / "targets/codex/models.json")
        native = sorted((self.stage / ".codex/agents").glob("*.toml"))
        self.assertEqual(14, len(native))
        body = target.read(self.stage / "AGENTS.md")
        for file in native:
            role = tomllib.loads(target.read(file))
            self.assertEqual(file.stem, role["name"])
            self.assertIn("| " + file.stem + " |", body)
            self.assertNotIn("cacheTtl", role["developer_instructions"])
            self.assertNotIn("sandbox_mode", role)
            if file.stem in mapping["dynamic_roles"]:
                self.assertNotIn("model", role)
                self.assertNotIn("model_reasoning_effort", role)
            else:
                self.assertIn(role["model"], mapping["tiers"].values())
                self.assertIn(role["model_reasoning_effort"], mapping["efforts"].values())
        self.assertIn("gpt-6.1-sol", body)
        self.assertNotIn("NOT CONFIGURED: AGENTS_TABLE", body)

    def test_common_composition_budget_and_no_default_mcp(self):
        self.assertEqual("codex", self.manifest["composition"]["target"]["id"])
        self.assertEqual("public", self.manifest["composition"]["profile"]["id"])
        self.assertLessEqual(len((self.stage / "AGENTS.md").read_bytes()), 32768)
        self.assertEqual(False, self.manifest["instruction_budget"]["truncated"])
        self.assertTrue((self.stage / ".airules/project-context.md").is_file())
        self.assertTrue((self.stage / ".airules/testing-contour.md").is_file())
        self.assertFalse((self.stage / ".codex/config.toml").exists())
        self.assertFalse((self.stage / ".claude").exists())

    def test_apply_rollback_preserve_project_context_openspec_and_config(self):
        preserved = {"openspec/project.md": "# Existing project passport\n", ".airules/project-context.md": "Keep local project facts\n", ".codex/config.toml": 'model = "user-selected-model"\n'}
        for rel, value in preserved.items():
            self.save(self.project / rel, value)
        before = target.files(self.project)
        result = target.apply(self.project, self.stage, self.backups)
        self.assertEqual("applied", result["status"])
        for rel, value in preserved.items():
            self.assertEqual(value, target.read(self.project / rel))
        target.rollback(self.project, result["backup"])
        self.assertEqual(before, target.files(self.project))

    def test_existing_unmanaged_instructions_conflict_before_any_write(self):
        self.save(self.project / "AGENTS.md", "# User contract\n")
        before = target.files(self.project)
        self.assertEqual("blocked", target.plan(self.project, self.stage)["status"])
        with self.assertRaisesRegex(target.RenderError, "apply conflicts"):
            target.apply(self.project, self.stage, self.backups)
        self.assertEqual(before, target.files(self.project))
        self.assertFalse(self.backups.exists())

    def test_update_replaces_owned_files_but_refuses_local_edits(self):
        first = target.apply(self.project, self.stage, self.backups)
        body = target.read(self.stage / ".codex/agents/developer.toml")
        self.save(self.stage / ".codex/agents/developer.toml", body.replace("## Execution boundary", "## Updated execution boundary"))
        self.reseal()
        update = target.apply(self.project, self.stage, self.backups)
        self.assertIn("Updated execution", target.read(self.project / ".codex/agents/developer.toml"))
        target.rollback(self.project, update["backup"])
        self.assertNotIn("Updated execution", target.read(self.project / ".codex/agents/developer.toml"))
        self.save(self.project / ".codex/agents/developer.toml", "# Local role edit\n")
        before = target.files(self.project)
        with self.assertRaisesRegex(target.RenderError, "apply conflicts"):
            target.apply(self.project, self.stage, self.backups)
        self.assertEqual(before, target.files(self.project))

    def test_partial_apply_failure_restores_every_original_byte(self):
        before = target.files(self.project)
        with self.assertRaisesRegex(target.RenderError, "injected apply failure"):
            target.apply(self.project, self.stage, self.backups, fail_after=3)
        self.assertEqual(before, target.files(self.project))
        receipts = list(self.backups.glob("*/receipt.json"))
        self.assertEqual("failed-restored", target.load_json(receipts[0])["status"])

    def test_rollback_refuses_later_local_changes(self):
        result = target.apply(self.project, self.stage, self.backups)
        self.save(self.project / "AGENTS.md", "# Later user edit\n")
        before = target.files(self.project)
        with self.assertRaisesRegex(target.RenderError, "local edit"):
            target.rollback(self.project, result["backup"])
        self.assertEqual(before, target.files(self.project))

    def test_failed_rollback_compensates_and_can_be_retried(self):
        first = target.apply(self.project, self.stage, self.backups)
        # A real update gives rollback overwritten bytes, not just newly-created files.
        self.save(self.stage / ".codex/agents/developer.toml", target.read(self.stage / ".codex/agents/developer.toml") + "\n# updated fixture\n")
        self.save(self.stage / ".codex/agents/tester.toml", target.read(self.stage / ".codex/agents/tester.toml") + "\n# updated fixture\n")
        self.reseal()
        update = target.apply(self.project, self.stage, self.backups)
        before = target.files(self.project)
        with self.assertRaisesRegex(target.RenderError, "injected rollback failure"):
            target.rollback(self.project, update["backup"], fail_after=1)
        self.assertEqual(before, target.files(self.project))
        self.assertEqual("applied", target.load_json(Path(update["backup"]) / "receipt.json")["status"])
        target.rollback(self.project, update["backup"])
        self.assertNotIn("updated fixture", target.read(self.project / ".codex/agents/developer.toml"))

    def test_compensation_preserves_concurrent_local_edit(self):
        original = target.atomic
        calls = []
        changed = []
        def fail_with_local_edit(path, content):
            if str(path).startswith(str(self.project)) and path.name != target.MANIFEST:
                calls.append(path)
                if len(calls) == 2:
                    calls[0].write_bytes(b"local edit during failed apply\n")
                    changed.append(calls[0])
                    raise OSError("injected write failure")
            return original(path, content)
        with patch.object(target, "atomic", side_effect=fail_with_local_edit):
            with self.assertRaisesRegex(target.RenderError, "concurrent edits"):
                target.apply(self.project, self.stage, self.backups)
        self.assertEqual(b"local edit during failed apply\n", changed[0].read_bytes())
        receipt = target.load_json(next(self.backups.glob("*/receipt.json")))
        self.assertEqual("recovery-required", receipt["status"])
        self.assertEqual([changed[0].relative_to(self.project).as_posix()], receipt["recovery_paths"])

    def test_mcp_appends_disjoint_native_tables_preserving_original_bytes(self):
        self.add_mcp()
        original = b'\xef\xbb\xbf# local config\r\nmodel = "user-model"\r\n[mcp_servers.keep]\r\ncommand = "existing-server"\r\n'
        path = self.project / ".codex/config.toml"
        path.parent.mkdir(parents=True)
        path.write_bytes(original)
        result = target.apply(self.project, self.stage, self.backups)
        self.assertTrue(path.read_bytes().startswith(original))
        value = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        self.assertEqual("user-model", value["model"])
        self.assertEqual("CODE_MCP_AUTH", value["mcp_servers"]["direct-code"]["bearer_token_env_var"])
        target.rollback(self.project, result["backup"])
        self.assertEqual(original, path.read_bytes())

    def test_mcp_server_collision_and_inline_secrets_are_rejected(self):
        self.add_mcp()
        self.save(self.project / ".codex/config.toml", '[mcp_servers.direct-code]\ncommand = "existing"\n')
        self.assertEqual("blocked", target.plan(self.project, self.stage)["status"])
        for server in ({"url":"https://example.invalid/mcp?token=fake"}, {"command":"server","env":{"PASSWORD":"fixture"}}, {"command":"server","args":["--password","fixture"]}):
            bindings = json.loads(json.dumps(self.bindings))
            bindings["mcp_servers"] = {"direct":server}
            with self.assertRaises(target.RenderError):
                target.validate_bindings(bindings)

    def test_tampered_candidate_and_manifest_paths_fail_closed(self):
        self.save(self.stage / "rules/testing-1c.md", "# Not reviewed\n")
        with self.assertRaisesRegex(target.RenderError, "hashes changed"):
            target.verify(self.stage)
        for rel in ("../escape", "C:/escape", "/absolute", ".codex/../config.toml", ".codex\\config.toml"):
            with self.assertRaises(target.RenderError):
                target.safe(self.project, rel)

    def test_fresh_stage_required_and_distribution_not_a_target_project(self):
        with self.assertRaisesRegex(target.RenderError, "fresh staging"):
            target.build(ROOT, self.project, self.stage, self.bindings)
        with self.assertRaisesRegex(target.RenderError, "distribution checkout"):
            target.plan(ROOT, self.stage)


if __name__ == "__main__":
    unittest.main()
