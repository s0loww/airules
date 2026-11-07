#!/usr/bin/env python3
"""Registered Codex hook dispatch, native wire and launcher regressions.

Offline fixture processes only. No client hook trust, model, MCP, real project
installation or 1C action is performed. The registration's matcher chooses
whether the process runs; tests do not bypass that registration.
"""

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "targets/codex/hooks"
spec = importlib.util.spec_from_file_location("codex_hook_config", TARGET / "config.py")
config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_module)
CONFIG = config_module.render_config()


class RegisteredCodexHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="airules-codex-hook-")
        self.root = Path(self.temp.name) / "проект with spaces"
        self.directory = self.root / ".codex/hooks"
        self.directory.mkdir(parents=True)
        shutil.copyfile(ROOT / "core/hooks/rule-inject.py", self.directory / "rule-inject.py")
        shutil.copyfile(TARGET / "codex-hook.py", self.directory / "codex-hook.py")
        self.nested = self.root / "nested folder"
        self.nested.mkdir()
        self.mapping = {"budget_chars": 1400, "entries": [
            {"globs": ["**/*.bsl"], "rule": "rules/code.md", "invariant": "Read the code invariant."},
            {"globs": ["**/*.xml"], "rule": "rules/xml.md", "invariant": "XML invariant."},
            {"globs": ["**/Forms/**"], "rule": "rules/forms.md", "invariant": "Form invariant."},
        ]}
        self.map_path = self.directory / "rules-map.json"
        self.map_path.write_text(json.dumps(self.mapping), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, patch, cwd=None):
        return {"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                "cwd": str(cwd or self.root), "tool_input": {"command": patch}}

    def registered(self, payload):
        event = payload.get("hook_event_name")
        subject = payload.get("tool_name") if event == "PreToolUse" else payload.get("source")
        return [row for row in CONFIG["hooks"].get(event, [])
                if isinstance(subject, str) and re.search(row["matcher"], subject)]

    def run_wire(self, payload, *, raw=None, launcher=False, cwd=None):
        if raw is None and not self.registered(payload):
            return ""
        command = [sys.executable, "-B", str(self.directory / "codex-hook.py")]
        if launcher:
            handler = self.registered(payload)[0]["hooks"][0]
            if os.name == "nt":
                prefix = 'powershell.exe -NoProfile -Command "'
                self.assertTrue(handler["commandWindows"].startswith(prefix))
                command = ["powershell.exe", "-NoProfile", "-Command", handler["commandWindows"][len(prefix):-1]]
            else:
                command = ["sh", "-c", handler["command"]]
        body = raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        process = subprocess.run(command, input=body, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, cwd=cwd or self.root, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", errors="replace"))
        self.assertEqual(process.stderr, b"")
        text = process.stdout.decode("utf-8")
        if text:
            response = json.loads(text)
            self.assertEqual(set(response), {"hookSpecificOutput"})
            self.assertEqual(set(response["hookSpecificOutput"]), {"hookEventName", "additionalContext"})
            self.assertLessEqual(len(response["hookSpecificOutput"]["additionalContext"]), 4096)
        return text

    def context(self, payload, **kwargs):
        text = self.run_wire(payload, **kwargs)
        return json.loads(text)["hookSpecificOutput"]["additionalContext"] if text else ""

    def test_registered_patch_covers_add_update_delete_and_move_with_spaces(self):
        payload = self.payload("""*** Begin Patch
*** Add File: src/Новый модуль.bsl
+Процедура Тест()
+КонецПроцедуры
*** Update File: src/Old module.bsl
*** Move to: src/Forms/New form.xml
@@
-old
+new
*** Delete File: src/Deleted data.xml
*** End Patch""")
        self.assertTrue(self.registered(payload))
        context = self.context(payload)
        for rule in ("code", "xml", "forms"):
            self.assertEqual(context.count("rules/" + rule + ".md"), 1)

    def test_registered_file_alias_and_unrelated_tool(self):
        for name in ("Edit", "Write"):
            payload = {"hook_event_name": "PreToolUse", "tool_name": name,
                       "cwd": str(self.root), "tool_input": {"file_path": str(self.root / "Модуль.bsl")}}
            self.assertIn("rules/code.md", self.context(payload))
        payload["tool_name"] = "shell"
        self.assertEqual(self.registered(payload), [])
        self.assertEqual(self.run_wire(payload), "")

    def test_content_cannot_forge_patch_header_and_incomplete_patch_is_empty(self):
        patch = "*** Begin Patch\n*** Add File: notes.md\n+*** Update File: src/evil.bsl\n*** End Patch"
        self.assertEqual(self.context(self.payload(patch)), "")
        for patch in ("*** Begin Patch\n*** Update File: x.bsl", "*** Begin Patch\n*** Move to: x.bsl\n*** End Patch"):
            self.assertEqual(self.context(self.payload(patch)), "")

    def test_nested_cwd_absolute_paths_and_scope_escape(self):
        target = self.root / "src/Модуль с пробелом.bsl"
        patch = f"*** Begin Patch\n*** Update File: {target}\n@@\n-a\n+b\n*** End Patch"
        self.assertIn("rules/code.md", self.context(self.payload(patch, self.nested)))
        relative = "*** Begin Patch\n*** Update File: ../src/a.bsl\n@@\n-a\n+b\n*** End Patch"
        self.assertIn("rules/code.md", self.context(self.payload(relative, self.nested)))
        outside = "*** Begin Patch\n*** Update File: ../../outside.bsl\n@@\n-a\n+b\n*** End Patch"
        self.assertEqual(self.context(self.payload(outside, self.nested)), "")
        self.assertEqual(self.context(self.payload(patch, self.root.parent)), "")

    def test_compact_and_handoff_events_use_native_json_from_project_root(self):
        state = self.root / "var/tmp"
        state.mkdir(parents=True)
        (state / "orchestration.json").write_text('{"private":"not injected"}', encoding="utf-8")
        (state / "session-map-audit.md").write_text("private source body not injected", encoding="utf-8")
        (state / "handoff-active.md").write_text("Status: active\nprivate body not injected", encoding="utf-8")
        (state / "handoff-completed.md").write_text("Status: completed", encoding="utf-8")
        for source in ("compact", "startup", "resume", "clear", "fork"):
            payload = {"hook_event_name": "SessionStart", "source": source, "cwd": str(self.nested)}
            context = self.context(payload)
            self.assertNotIn("private", context)
            if source == "compact":
                self.assertIn("Context was just compacted", context)
                self.assertIn("orchestration.json", context)
                self.assertIn("session-map-audit.md", context)
            else:
                self.assertIn("handoff-active.md", context)
                self.assertNotIn("handoff-completed.md", context)
                self.assertIn("existing confirmed scope remains valid", context)

    def test_metadata_hardlink_is_ignored(self):
        state = self.root / "var/tmp"
        state.mkdir(parents=True)
        outside = self.root.parent / "external.md"
        outside.write_text("Status: active\nDO_NOT_READ_OR_INJECT", encoding="utf-8")
        os.link(outside, state / "handoff-linked.md")
        payload = {"hook_event_name": "SessionStart", "source": "resume", "cwd": str(self.root)}
        self.assertEqual(self.context(payload), "")

    def test_missing_map_malformed_and_oversized_input_are_silent(self):
        payload = self.payload("*** Begin Patch\n*** Add File: a.bsl\n+a\n*** End Patch")
        self.map_path.unlink()
        self.assertEqual(self.context(payload), "")
        for raw in (b"null", b"[]", b"invalid", b"x" * (1024 * 1024 + 1)):
            self.assertEqual(self.run_wire({}, raw=raw), "")

    def test_context_budget_is_hard_and_negative_disables_reminder(self):
        self.mapping["entries"][0]["invariant"] = "x" * 10000
        self.mapping["budget_chars"] = 50000
        self.map_path.write_text(json.dumps(self.mapping), encoding="utf-8")
        payload = self.payload("*** Begin Patch\n*** Add File: a.bsl\n+a\n*** End Patch")
        self.assertEqual(len(self.context(payload)), 4096)
        self.mapping["budget_chars"] = 40
        self.map_path.write_text(json.dumps(self.mapping), encoding="utf-8")
        self.assertLessEqual(len(self.context(payload)), 40)
        self.mapping["budget_chars"] = 0
        self.map_path.write_text(json.dumps(self.mapping), encoding="utf-8")
        # The legacy map loader interprets zero as its default. Adapter limits
        # still bound the result; negative values explicitly disable output.
        self.assertLessEqual(len(self.context(payload)), 4096)
        self.mapping["budget_chars"] = -1
        self.map_path.write_text(json.dumps(self.mapping), encoding="utf-8")
        self.assertEqual(self.context(payload), "")

    def test_registered_launcher_from_nested_git_directory_with_spaces(self):
        if not shutil.which("git") or (os.name == "nt" and not shutil.which("powershell.exe")):
            self.skipTest("Local Git / platform shell unavailable")
        subprocess.run(["git", "-c", "init.templateDir=", "init", "--quiet", str(self.root)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        patch = "*** Begin Patch\n*** Add File: generated.bsl\n+data\n*** End Patch"
        context = self.context(self.payload(patch, self.nested), launcher=True, cwd=self.nested)
        self.assertIn("rules/code.md", context)
        self.assertFalse(list(self.root.rglob("__pycache__")))
        self.assertFalse(list(self.root.rglob("*.pyc")))

    def test_claude_single_file_output_remains_compatible(self):
        payload = {"tool_name": "Edit", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / "a.bsl")}}
        process = subprocess.run([sys.executable, "-B", str(self.directory / "rule-inject.py")],
                                 input=json.dumps(payload).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(process.returncode, 0)
        self.assertIn("rules/code.md", json.loads(process.stdout)["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
