#!/usr/bin/env python3
"""Assertion-based command-advisory regressions; no live deployment or services."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


core = module(ROOT / "core/hooks/command-advisory.py", "advisory_core_test")
deploy = module(ROOT / "overlays/1c/hooks/deploy-advisory.py", "advisory_deploy_test")


class AdvisoryFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="airules-advisory-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "проект with spaces"
        self.hooks = self.root / ".codex/hooks"
        self.hooks.mkdir(parents=True)
        shutil.copyfile(ROOT / "core/hooks/command-advisory.py", self.hooks / "command-advisory.py")
        shutil.copyfile(ROOT / "overlays/1c/hooks/deploy-advisory.py", self.hooks / "deploy-advisory.py")
        self.config = self.root / core.CONFIG
        self.config.parent.mkdir()
        self.settings = {"schema_version": 1, "enabled": True, "pre": [], "post": [
            {"id": "contention", "command_any": ["project-deploy"], "output_any": ["BUSY", "exclusive lock"],
             "output_all": ["failed", "operation"], "hint": "Проверьте активные сеансы."}
        ]}
        self.save()

    def save(self):
        self.config.write_text(json.dumps(self.settings, ensure_ascii=False), encoding="utf-8")

    def payload(self, output="operation failed: busy", command="project-deploy", event="PostToolUse", tool="Bash"):
        return {"hook_event_name": event, "tool_name": tool, "tool_input": {"command": command},
                "tool_response": output, "cwd": str(self.root / "nested"), "session_id": "fixture"}

    def cli(self, payload=None, *, raw=None, script="command-advisory.py"):
        if raw is None:
            raw = json.dumps(payload or self.payload(), ensure_ascii=False).encode("utf-8")
        proc = subprocess.run([sys.executable, "-B", str(self.hooks / script)], input=raw,
                              capture_output=True, cwd=self.root, timeout=5)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual(b"", proc.stderr)
        self.assertFalse(list(self.root.rglob("__pycache__")))
        return proc.stdout.decode("utf-8")

    def context(self, text):
        value = json.loads(text)
        self.assertEqual({"hookSpecificOutput"}, set(value))
        self.assertEqual({"hookEventName", "additionalContext"}, set(value["hookSpecificOutput"]))
        return value["hookSpecificOutput"]["additionalContext"]

class CommandAdvisoryTests(AdvisoryFixture, unittest.TestCase):
    def test_literal_any_all_command_filter_and_case(self):
        self.assertIn("Проверьте", self.context(self.cli()))
        self.assertEqual("", self.cli(self.payload("operation busy")))
        self.assertEqual("", self.cli(self.payload(command="unrelated-command")))
        self.assertEqual("", self.cli(self.payload("operation failed: ready")))
        self.settings["post"][0]["ignore_case"] = False
        self.save()
        self.assertEqual("", self.cli())
        self.assertIn("Проверьте", self.context(self.cli(self.payload("operation failed: BUSY"))))

    def test_string_object_list_and_nested_response_envelopes(self):
        for response in ["operation failed: busy", {"stdout": "operation", "stderr": "failed: busy"},
                         [{"type": "text", "text": "operation failed: busy"}],
                         {"content": [{"text": "operation failed: busy"}]}]:
            with self.subTest(response=response):
                self.assertIn("Проверьте", self.context(self.cli(self.payload(response))))

    def test_tool_and_event_dispatch(self):
        for tool in ["Bash", "PowerShell"]:
            self.assertTrue(self.cli(self.payload(tool=tool)))
        for tool in ["Read", "exec_command", "apply_patch", "BashExtended", None]:
            self.assertEqual("", self.cli(self.payload(tool=tool)))
        for event in ["SessionStart", "PreCompact", "PostToolUseFailure", None]:
            self.assertEqual("", self.cli(self.payload(event=event)))
        self.settings["pre"] = [{"id": "preflight", "command_any": ["project-deploy"], "hint": "Use the reviewed target."}]
        self.save()
        self.assertIn("reviewed target", self.context(self.cli(self.payload(event="PreToolUse"))))

    def test_malformed_disabled_absent_and_unknown_config_silent(self):
        for raw in [b"", b"{", b"[]", b"null", b"\xff", b" " * (core.MAX_INPUT + 1)]:
            with self.subTest(raw_length=len(raw)):
                self.assertEqual("", self.cli(raw=raw))
        self.settings["enabled"] = False
        self.save()
        self.assertEqual("", self.cli())
        self.settings["enabled"] = True
        self.settings["schema_version"] = 2
        self.save()
        self.assertEqual("", self.cli())
        self.settings["schema_version"] = True
        self.save()
        self.assertEqual("", self.cli())
        self.config.write_bytes(b"{")
        self.assertEqual("", self.cli())
        self.config.unlink()
        self.assertEqual("", self.cli())

    def test_invalid_tables_and_budgets_silent(self):
        original = copy.deepcopy(self.settings)
        mutations = [
            lambda c: c.update(unrecognized=True),
            lambda c: c.update(post="bad"),
            lambda c: c["post"][0].update(regex=".*"),
            lambda c: c["post"][0].update(output_any=[""]),
            lambda c: c["post"][0].update(hint="h" * 1601),
            lambda c: c["post"].append(copy.deepcopy(c["post"][0])),
            lambda c: c.update(post=[{"id": "e-" + str(i), "output_any": ["busy"], "hint": "h"} for i in range(65)]),
            lambda c: c.update(pre=[{"id": "bad-pre", "hint": "Missing command marker"}]),
        ]
        for mutate in mutations:
            self.settings = copy.deepcopy(original)
            mutate(self.settings)
            self.save()
            self.assertEqual("", self.cli())
        self.config.write_bytes(b" " * (core.MAX_TABLE + 1))
        self.assertEqual("", self.cli())

    def test_unicode_bom_input_output_and_no_response_echo(self):
        payload = self.payload("operation failed busy; password=private-test-sentinel")
        text = self.cli(raw=b"\xef\xbb\xbf" + json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        self.assertIn("Проверьте", self.context(text))
        self.assertNotIn("private-test-sentinel", text)
        self.assertNotIn("project-deploy", text)

    def test_own_banner_suppression_and_duplicate_hints(self):
        self.assertEqual("", self.cli(self.payload("operation failed busy " + core.BANNER)))
        self.assertEqual("", self.cli(self.payload(command="project-deploy echo " + core.BANNER)))
        second = dict(self.settings["post"][0], id="duplicate-message")
        self.settings["post"].append(second)
        self.save()
        text = self.context(self.cli())
        self.assertEqual(1, text.count("Проверьте"))

    def test_output_and_input_extraction_bounded(self):
        self.settings["post"] = [{"id": "entry-" + str(i), "output_any": ["busy"], "hint": str(i) + "h" * 1500} for i in range(8)]
        self.save()
        text = self.context(self.cli())
        self.assertLessEqual(len(text), core.MAX_CONTEXT)
        self.assertLessEqual(text.count("\n- "), core.MAX_HINTS)
        self.assertEqual("", self.cli(self.payload("x" * core.MAX_TEXT + "operation failed busy")))
        self.assertEqual("", self.cli(self.payload(command="project-deploy" + "x" * core.MAX_COMMAND)))

    def test_symlink_and_hardlink_config_fail_open(self):
        original = self.config.read_bytes()
        outside = Path(self.temp.name) / "outside.json"
        outside.write_bytes(original)
        self.config.unlink()
        try:
            self.config.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.config.write_bytes(original)
        else:
            self.assertEqual("", self.cli())
            self.config.unlink()
            self.config.write_bytes(original)
        self.config.unlink()
        try:
            os.link(outside, self.config)
        except OSError:
            self.config.write_bytes(original)
        else:
            self.assertEqual("", self.cli())


class DeploymentAdvisoryTests(AdvisoryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.settings["deploy"] = {"enabled": True, "command_any": ["project-deploy.ps1"], "probe_processes": False, "targets": []}
        self.save()
        self.command = 'powershell.exe -File "tools/project-deploy.ps1" -Dynamic "-"'

    def event(self, command=None):
        return self.payload(command=command or self.command, event="PreToolUse")

    def test_distributed_examples_are_valid_and_disabled(self):
        examples = [ROOT / "core/hooks/command-advisories.example.json",
                    ROOT / "overlays/1c/hooks/deploy-advisories.example.json"]
        for file in examples:
            with self.subTest(example=file.name):
                self.settings = json.loads(file.read_text(encoding="utf-8"))
                self.save()
                loaded = core.load_config(self.root)
                self.assertFalse(loaded["enabled"])
                deploy.validate(loaded, core)
                self.assertEqual("", self.cli(self.event()))
                self.assertEqual("", self.cli(self.event(), script="deploy-advisory.py"))
        # Both shipped schemas must themselves be readable JSON resources.
        for file in [ROOT / "core/hooks/command-advisories.schema.json",
                     ROOT / "overlays/1c/hooks/deploy-advisories.schema.json"]:
            value = json.loads(file.read_text(encoding="utf-8"))
            self.assertEqual("object", value["type"])

    def test_configured_deploy_wire_and_non_deploy_silence(self):
        text = self.cli(self.event(), script="deploy-advisory.py")
        self.assertIn("colon form", self.context(text))
        self.assertEqual("", self.cli(self.event("git status"), script="deploy-advisory.py"))
        self.assertEqual("", self.cli(self.event(self.command.replace('-Dynamic "-"', '-Dynamic:"-"')), script="deploy-advisory.py"))
        self.assertEqual("", self.cli(self.payload(command=self.command), script="deploy-advisory.py"))

    def test_syntax_variants_and_quoted_paths(self):
        for value in ['-Dynamic "-"', "-Dynamic '-'", '-Dynamic -', '-dynamic "-"']:
            hints = deploy.hints(self.event('pwsh -File "folder with spaces/project-deploy.ps1" ' + value), self.settings, core)
            self.assertEqual(1, len(hints), value)
        for value in ['-Dynamic:"-"', "-Dynamic:'-'", '-Dynamic:-', '-Dynamic "+"', '-Dynamic --other']:
            hints = deploy.hints(self.event('pwsh -File "folder with spaces/project-deploy.ps1" ' + value), self.settings, core)
            self.assertEqual([], hints, value)
        self.assertEqual([], deploy.hints(self.event('pwsh -Command project-deploy.ps1 -Dynamic "-"'), self.settings, core))

    def test_unknown_or_ambiguous_target_never_probes_or_infers_lock(self):
        self.settings["deploy"]["probe_processes"] = True
        with patch.object(deploy, "probe_inventory", side_effect=AssertionError("must not probe")):
            # Inject explicitly: function defaults are bound at definition time.
            result = deploy.hints(self.event(), self.settings, core, lambda timeout: self.fail("unknown target probed"))
            self.assertEqual(1, len(result))
        self.settings["deploy"]["targets"] = [{"command_any": ["project-deploy"], "path": r"C:\db\one"}, {"command_any": ["project-deploy"], "path": r"C:\db\two"}]
        self.assertEqual(1, len(deploy.hints(self.event(), self.settings, core, lambda timeout: self.fail("ambiguous target probed"))))

    def probe_config(self):
        self.settings["deploy"].update(probe_processes=True, targets=[{"command_any": ["--fixture"], "path": r"C:\bases\demo"}])
        return self.event(self.command + " --fixture")

    def test_target_scoped_process_hint_and_no_neighbouring_database_match(self):
        event = self.probe_config()
        data = {"processes": [{"Name": "1cv8.exe", "CommandLine": r'1cv8.exe DESIGNER /F"C:\bases\demo" /Psecret-never-echo'}]}
        result = deploy.hints(event, self.settings, core, lambda timeout: data)
        self.assertEqual(2, len(result))
        self.assertIn("does not prove a lock", result[1])
        self.assertNotIn("secret-never-echo", " ".join(result))
        data["processes"][0]["CommandLine"] = r'1cv8.exe DESIGNER /F"C:\bases\demo-other"'
        self.assertEqual(1, len(deploy.hints(event, self.settings, core, lambda timeout: data)))
        for line in [r'1cv8.exe /FC:\bases\demo', r'1cv8.exe /F"C:\bases\demo\"', r'1cv8.exe /F"C:/bases/demo"']:
            self.assertTrue(deploy.references_target(line, r"C:\bases\demo"), line)

    def test_apache_presence_is_not_proof_and_only_for_known_exclusive_target(self):
        event = self.probe_config()
        data = {"processes": [], "apache": [{"Name": "Apache24", "Status": "Running"}]}
        result = deploy.hints(event, self.settings, core, lambda timeout: data)
        self.assertEqual(2, len(result))
        self.assertIn("does not prove", result[1])
        plus = self.event(event["tool_input"]["command"].replace('-Dynamic "-"', '-Dynamic "+"'))
        self.assertEqual([], deploy.hints(plus, self.settings, core, lambda timeout: data))

    def test_probe_failure_and_unsupported_platform_do_not_block_syntax_hint(self):
        event = self.probe_config()
        self.assertEqual(1, len(deploy.hints(event, self.settings, core, lambda timeout: None)))
        with patch.object(deploy.os, "name", "posix"), patch.object(deploy.subprocess, "run", side_effect=AssertionError("unsupported OS probe")):
            self.assertIsNone(deploy.probe_inventory(1))
        with patch.object(deploy.os, "name", "nt"), patch.object(deploy.subprocess, "run", side_effect=subprocess.TimeoutExpired("fixture", 1)):
            self.assertIsNone(deploy.probe_inventory(1))
        with patch.object(deploy.os, "name", "nt"), patch.object(deploy.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b'x' * (deploy.MAX_INVENTORY + 1))):
            self.assertIsNone(deploy.probe_inventory(1))

    def test_probe_command_is_fixed_read_only_and_never_uses_payload_as_code(self):
        response = json.dumps({"processes": [], "apache": []}).encode("utf-8")
        with patch.object(deploy.os, "name", "nt"), patch.object(deploy.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, response)) as run:
            self.assertEqual({"processes": [], "apache": []}, deploy.probe_inventory(0.5))
        args, kwargs = run.call_args
        self.assertEqual(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", deploy.PROBE], args[0])
        self.assertEqual(0.5, kwargs["timeout"])
        self.assertNotIn("shell", kwargs)
        self.assertNotRegex(deploy.PROBE, r"(?i)(Stop-Process|Restart-Service|Stop-Service|Remove-Item|UpdateDBCfg|LoadConfigFromFiles)")

    def test_invalid_deploy_settings_fail_open(self):
        for changes in [{"process_command": "arbitrary"}, {"probe_timeout_seconds": 20}, {"targets": [{"command_any": ["project"], "path": "relative"}]}, {"command_any": []}]:
            with self.subTest(changes=changes):
                original = copy.deepcopy(self.settings)
                self.settings["deploy"].update(changes)
                self.save()
                self.assertEqual("", self.cli(self.event(), script="deploy-advisory.py"))
                self.settings = original


if __name__ == "__main__":
    unittest.main()
