"""Execute registered launchers in disposable projects, without client/model calls."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci"))
import simulate_install

spec = importlib.util.spec_from_file_location("advisory_target", ROOT / "targets/codex/render.py")
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


class RegisteredAdvisoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="registered-advisory-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "проект with spaces"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        self.nested = self.root / "nested folder"
        self.nested.mkdir()
        self.table = {
            "schema_version": 1, "enabled": True,
            "pre": [{"id": "preflight", "command_any": ["demo-task"], "hint": "Read the reviewed plan."}],
            "post": [{"id": "diagnosis", "output_any": ["fixture symptom"], "hint": "Inspect the fixture report."}],
        }

    def configure_table(self, enabled=True):
        value = dict(self.table, enabled=enabled)
        path = self.root / ".airules/command-advisories.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def probe(self, handlers, *, claude=False):
        for event, expected in (("PreToolUse", "Read the reviewed plan."),
                                ("PostToolUse", "Inspect the fixture report.")):
            handler = next(h for g in handlers["hooks"][event] for h in g["hooks"]
                           if "command-advisory.py" in str(h))
            payload = {"hook_event_name": event, "tool_name": "Bash", "cwd": str(self.nested),
                       "tool_input": {"command": "demo-task --value never-echo"},
                       "tool_response": {"stdout": "fixture symptom"}}
            if claude:
                command = [sys.executable] + [a.replace("${CLAUDE_PROJECT_DIR}", str(self.root)) for a in handler["args"]]
                shell = False
            else:
                command = handler["commandWindows"] if os.name == "nt" else handler["command"]
                shell = os.name != "nt"
            proc = subprocess.run(command, shell=shell, cwd=self.nested,
                                  input=json.dumps(payload), capture_output=True, text=True,
                                  encoding="utf-8", timeout=15)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertEqual("", proc.stderr)
            if self.table["enabled"]:
                result = json.loads(proc.stdout)["hookSpecificOutput"]
                self.assertEqual(event, result["hookEventName"])
                self.assertIn(expected, result["additionalContext"])
                self.assertNotIn("never-echo", proc.stdout)
            else:
                self.assertEqual("", proc.stdout)

    def test_codex_registered_commands_work_from_nested_unicode_path(self):
        candidate = Path(self.temp.name) / "candidate"
        bindings = target.load_json(ROOT / "targets/codex/bindings.example.json")
        target.build(ROOT, self.root, candidate, dict(bindings, command_advisories=True))
        target.apply(self.root, candidate, Path(self.temp.name) / "backups")
        config = target.load_json(self.root / ".codex/hooks.json")
        self.configure_table()
        self.probe(config)
        self.table["enabled"] = False
        self.configure_table(False)
        self.probe(config)

    def test_claude_registered_args_work_without_a_shell(self):
        for source in (ROOT / "core/rules", ROOT / "overlays/1c/rules"):
            shutil.copytree(source, self.root / "rules", dirs_exist_ok=True)
        problems = []
        simulate_install.install_hook(str(self.root), problems, command_advisories=True)
        self.assertEqual([], problems)
        config = target.load_json(self.root / ".claude/settings.json")
        self.configure_table()
        self.probe(config, claude=True)

    def test_claude_default_has_no_active_advisory_registration(self):
        for source in (ROOT / "core/rules", ROOT / "overlays/1c/rules"):
            shutil.copytree(source, self.root / "rules", dirs_exist_ok=True)
        problems = []
        simulate_install.install_hook(str(self.root), problems)
        self.assertEqual([], problems)
        config = target.load_json(self.root / ".claude/settings.json")
        self.assertNotIn("command-advisory.py", json.dumps(config))
        self.assertFalse((self.root / ".airules/command-advisories.json").exists())


if __name__ == "__main__":
    unittest.main()
