#!/usr/bin/env python3
"""Portable staging-smoke for the experimental DSH renderer."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = ROOT / "targets" / "dsh" / "deepseek" / "render.py"
SPEC = importlib.util.spec_from_file_location("airules_dsh_renderer", RENDERER_PATH)
assert SPEC is not None and SPEC.loader is not None
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)
SIMULATOR_SPEC = importlib.util.spec_from_file_location("airules_skill_install_simulator", ROOT / "ci" / "simulate_install.py")
assert SIMULATOR_SPEC is not None and SIMULATOR_SPEC.loader is not None
SIMULATOR = importlib.util.module_from_spec(SIMULATOR_SPEC)
sys.path.insert(0, str(ROOT / "ci"))
try:
    SIMULATOR_SPEC.loader.exec_module(SIMULATOR)
finally:
    sys.path.pop(0)
CORE_ADAPTATIONS = {"handoff", "skill-maintainer", "security-baseline", "architecture-evolution", "technical-debt", "memory-workspace"}
ONEC_ADAPTATIONS = {
    "1c-business-tests", "1c-ui-regression", "1c-verify-project",
    "1c-repository-manage", "1c-ai-merge", "v8unpack-cf", "1c-element",
}


class DshRendererTests(unittest.TestCase):
    def test_adapted_skill_bundles_arrive_in_both_target_layouts(self):
        with tempfile.TemporaryDirectory(prefix="airules-skill-layouts-") as temporary:
            base = Path(temporary)
            claude, dsh = base / "claude", base / "dsh"
            problems = []
            SIMULATOR.build(str(claude), problems)
            self.assertEqual([], problems)
            names, _ = RENDERER.copy_skills(ROOT, dsh)
            for layer, expected in (("core", CORE_ADAPTATIONS), ("overlays/1c", ONEC_ADAPTATIONS)):
                for name in expected:
                    self.assertIn(name, names)
                    source = ROOT / layer / "skills" / name
                    self.assertTrue((source / "SKILL.md").is_file(), name)
                    files = [path for path in source.rglob("*") if path.is_file()]
                    self.assertTrue(files, name)
                    for file in files:
                        relative = file.relative_to(source)
                        installed = claude / ".claude" / "skills" / name / relative
                        rendered = dsh / ".dsh" / "skills" / name / relative
                        self.assertEqual(file.read_bytes(), installed.read_bytes(), installed)
                        if file.suffix.lower() in RENDERER.TEXT_SKILL_EXTENSIONS:
                            self.assertEqual(RENDERER.transform_paths(RENDERER.read_text(file)),
                                             rendered.read_text(encoding="utf-8"), rendered)
                        else:
                            self.assertEqual(file.read_bytes(), rendered.read_bytes(), rendered)
            for entry in (ROOT / "targets" / "dsh" / "skills").glob("*/SKILL.md"):
                name = entry.parent.name
                self.assertIn(name, names)
                self.assertTrue((dsh / ".dsh" / "skills" / name / "SKILL.md").is_file())
                self.assertFalse((claude / ".claude" / "skills" / name).exists(), name)

    def test_target_skills_stay_native_and_cannot_shadow_portable_names(self):
        with tempfile.TemporaryDirectory(prefix="airules-target-skills-") as temporary:
            source, output = Path(temporary) / "source", Path(temporary) / "output"
            for base, name in (("core/skills", "portable"), ("targets/dsh/skills", "native-helper")):
                folder = source / base / name
                folder.mkdir(parents=True)
                (folder / "SKILL.md").write_text(
                    "---\nname: {0}\ndescription: Fixture\n---\nBody\n".format(name), encoding="utf-8")
            names, _ = RENDERER.copy_skills(source, output)
            self.assertEqual(["native-helper", "portable"], names)
            conflict = source / "targets/dsh/skills/portable"
            conflict.mkdir()
            (conflict / "SKILL.md").write_text("---\nname: portable\ndescription: Fixture\n---\nBody\n", encoding="utf-8")
            with self.assertRaisesRegex(RENDERER.RenderError, "conflicts with portable skill"):
                RENDERER.copy_skills(source, Path(temporary) / "conflict-output")

    def test_native_skill_identity_is_validated_before_copy(self):
        with tempfile.TemporaryDirectory(prefix="airules-skill-identity-") as temporary:
            skill = Path(temporary) / "fixture-skill"
            skill.mkdir()
            entry = skill / "SKILL.md"
            entry.write_text("---\nname: 'fixture-skill'\ndescription: Fixture\n---\nBody\n", encoding="utf-8")
            RENDERER.validate_skill(skill)
            entry.write_text("---\nname: another-skill\ndescription: Fixture\n---\nBody\n", encoding="utf-8")
            with self.assertRaisesRegex(RENDERER.RenderError, "does not match directory"):
                RENDERER.validate_skill(skill)
            entry.write_text("# Body\nname: fixture-skill\ndescription: Fixture\n", encoding="utf-8")
            with self.assertRaisesRegex(RENDERER.RenderError, "lacks YAML frontmatter"):
                RENDERER.validate_skill(skill)

    @staticmethod
    def bindings(path: Path, project_rules=None) -> Path:
        path.write_text(json.dumps({
            "placeholders": {
                "PROJECT_ID": "fixture",
                "PROJECT_NAME": "Fixture",
                "STACK": "1c",
                "SOURCE_OF_TRUTH": "`src/`",
                "PRIMARY_CODE_DIR": "`src/`",
                "PREFIX": "NOT CONFIGURED",
                "LANGUAGE_POLICY": "Russian replies",
                "MCP_ORDER": "facade -> source",
                "DISABLED_MCP": "legacy",
                "BACKUP_DIR": ".rules-backups/",
            },
            "project_rules": project_rules or [],
            "mcp_bindings": {},
        }), encoding="utf-8")
        return path

    def test_stage_candidate_without_mutating_project(self):
        with tempfile.TemporaryDirectory(prefix="airules-dsh-render-") as temporary:
            root = Path(temporary)
            project = root / "project"
            output = root / "output"
            project_rule = project / "project-rules" / "fixture-domain.md"
            project_rule.parent.mkdir(parents=True)
            project_rule.write_text(
                "---\ndescription: Fixture project domain rule\n---\n\n"
                "# Fixture\n\nRead `rules/test-model.md` when relevant.\n",
                encoding="utf-8",
            )
            (project / "USER-RULES.md").write_text(
                "# User rules\n\nSee `.codex/rules/fixture-domain.md`.\n",
                encoding="utf-8",
            )
            (project / ".mcp.json").write_text(
                json.dumps({"mcpServers": {"legacy": {"command": "fixture"}}}),
                encoding="utf-8",
            )
            (project / ".agents" / "skills" / "powershell-windows").mkdir(parents=True)
            bindings = self.bindings(root / "bindings.json", [{
                "name": "fixture-domain",
                "path": "project-rules/fixture-domain.md",
                "kind": "invariant",
            }])

            result = RENDERER.main([
                "render",
                "--source", str(ROOT),
                "--project", str(project),
                "--profile", "s0lo",
                "--bindings", str(bindings),
                "--output", str(output),
                "--skip-mcp",
            ])
            self.assertEqual(0, result)
            plan = json.loads((output / ".airules-render-plan.json").read_text(encoding="utf-8"))
            self.assertEqual("blocked-for-apply", plan["status"])
            self.assertIn("powershell-windows", plan["skill_collisions"])
            self.assertEqual("approximate", plan["instruction_probe"]["status"])
            self.assertEqual(0, RENDERER.main(["verify", "--output", str(output)]))
            rendered_rule = (output / ".dsh" / "rules-1c" / "fixture-domain.md").read_text(encoding="utf-8")
            self.assertIn(".dsh/rules-1c/test-model.md", rendered_rule)
            self.assertFalse((project / ".dsh").exists())
            self.assertFalse((project / ".airules-manifest.json").exists())

    def test_apply_backup_and_rollback(self):
        with tempfile.TemporaryDirectory(prefix="airules-dsh-apply-") as temporary:
            root = Path(temporary)
            project = root / "fixture-project"
            output = root / "output"
            backups = root / "backups"
            project.mkdir()
            original = "# Existing project instructions\n"
            (project / "AGENTS.md").write_text(original, encoding="utf-8")
            (project / "USER-RULES.md").write_text("# User rules\n", encoding="utf-8")
            old_skill = project / ".agents" / "skills" / "powershell-windows" / "SKILL.md"
            old_skill.parent.mkdir(parents=True)
            old_skill.write_text("old project skill\n", encoding="utf-8")
            bindings = self.bindings(root / "bindings.json")

            self.assertEqual(0, RENDERER.main([
                "render", "--source", str(ROOT), "--project", str(project),
                "--profile", "public", "--bindings", str(bindings),
                "--output", str(output), "--skip-mcp",
                "--accept-skill-collisions", "--replace-user-rules",
            ]))
            base_apply = [
                "apply", "--project", str(project), "--candidate", str(output),
                "--backup-root", str(backups), "--confirm", project.name,
                "--allow-dirty-source",
            ]
            self.assertEqual(1, RENDERER.main(base_apply))
            self.assertEqual(0, RENDERER.main(base_apply + ["--adopt-existing-instructions"]))
            self.assertNotEqual(original, (project / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertTrue((project / ".airules-manifest.json").is_file())
            self.assertFalse(old_skill.exists())
            self.assertTrue((project / ".dsh" / "skills" / "powershell-windows" / "SKILL.md").is_file())
            backup = next((backups / project.name).iterdir())
            self.assertEqual(0, RENDERER.main([
                "rollback", "--project", str(project), "--backup", str(backup),
                "--confirm", project.name,
            ]))
            self.assertEqual(original, (project / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertFalse((project / ".airules-manifest.json").exists())
            self.assertEqual("old project skill\n", old_skill.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
