"""Shared oracle plus real native-hook boundary tests; fixtures contain no user data."""
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

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('continuity', ROOT / 'core/hooks/continuity.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
CONTRACT = json.loads((ROOT / 'core/tools/continuity/contract.json').read_text(encoding='utf-8'))


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='airules continuity ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'core/tools/continuity', self.root / 'tools/continuity')
        self.payload = {'session_id': 's', 'cwd': str(self.root), 'permission_mode': 'acceptEdits', 'hook_event_name': 'PreCompact'}

    def put(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')
        return path

    def config(self, **kwargs):
        self.put('.airules/continuity.json', json.dumps({'schemaVersion': 1, **kwargs}))

    def test_shared_oracles(self):
        fixture = json.loads((ROOT / 'core/tools/continuity/fixtures.json').read_text(encoding='utf-8'))
        for case in fixture['cases']:
            with self.subTest(case=case['id']):
                out = core.render_packet(CONTRACT, case['input'])
                expected = case['expected']
                self.assertEqual(expected['deliver'], out['deliver'])
                self.assertEqual(out['bytes'], len(out['text'].encode('utf-8')))
                self.assertLessEqual(out['bytes'], expected['maxBytes'])
                for text in expected['includes']:
                    self.assertIn(text, out['text'])
                for text in expected['excludes']:
                    self.assertNotIn(text, out['text'])

    def test_unicode_budget_and_secret_sources(self):
        packet = {'mode': 'balanced', 'scope': {'origin': 'lead'}, 'compact': {'complete': True},
            'refs': [{'kind': 'rule', 'path': 'р' * 500, 'version': 'v'}] * 20,
            'files': [{'path': 'src/x', 'text': 'password=fixture_secret', 'critical': True, 'allowed': True, 'lost': True}]}
        out = core.render_packet(CONTRACT, packet)
        self.assertLessEqual(out['bytes'], 12288)
        self.assertNotIn('fixture_secret', out['text'])

    def test_scope_isolates_projects_sessions_and_child_agents(self):
        lead = core.scope_for(self.root, self.payload)
        scopes = [lead, core.scope_for(self.root, {**self.payload, 'session_id': 'other'}),
            core.scope_for(self.root, {**self.payload, 'agent_id': 'a'}), core.scope_for(self.root, {**self.payload, 'agent_id': 'b'})]
        self.assertEqual(4, len({core.state_relative(scope) for scope in scopes}))
        with self.assertRaises(ValueError):
            core.scope_for(self.root, {**self.payload, 'cwd': str(self.root.parent)})
        with self.assertRaises(ValueError):
            core.scope_for(self.root, {**self.payload, 'session_id': ''})

    def test_unknown_read_only_and_default_never_write(self):
        core.handle_event(self.root, self.payload, 'claude')
        self.config(checkpoint=True)
        for adapter, values in [('codex', {}), ('claude', {'permission_mode': 'default'}),
            ('claude', {'permission_mode': 'plan'}), ('codex', {'sandbox_mode': 'read-only'})]:
            core.handle_event(self.root, {**self.payload, **values}, adapter)
        self.assertFalse((self.root / 'var').exists())

    def test_checkpoint_is_mechanical_bounded_and_never_restores_tree(self):
        self.config(checkpoint=True)
        self.put('openspec/changes/sample/tasks.md', '- [x] fixture done\n- [ ] fixture next\n')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        self.put('tracked.txt', 'before\n')
        subprocess.run(['git', '-C', str(self.root), 'add', 'tracked.txt'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True, capture_output=True)
        self.put('tracked.txt', 'after\n')
        core.handle_event(self.root, self.payload, 'claude')
        scope = core.scope_for(self.root, self.payload)
        value = core.load_state(self.root, scope)
        self.assertEqual('partial', value['state'])
        self.assertIn('exact-compact-id-unavailable', value['limitations'])
        self.assertIn('tracked.txt', value['git']['changedPaths'])
        self.assertEqual((2, 1), (value['openspec'][0]['total'], value['openspec'][0]['done']))
        self.assertNotIn('fixture next', json.dumps(value))
        self.assertIn('capturedAt', value)
        self.assertLessEqual((self.root / core.state_relative(scope)).stat().st_size, core.MAX_STATE)
        result = core.handle_event(self.root, {**self.payload, 'hook_event_name': 'SessionStart', 'source': 'compact'}, 'claude')
        self.assertIn('Historical checkpoint:', result)
        self.assertEqual('after\n', (self.root / 'tracked.txt').read_text())

    def test_read_receipts_are_bounded_but_balanced_python_remains_pointer_only(self):
        self.config(mode='balanced', checkpoint=True, taskFiles=['src/6.txt'])
        for index in range(7):
            name = 'src/%d.txt' % index
            self.put(name, 'BODY_NOT_REINJECTED_%d' % index)
            event = {**self.payload, 'hook_event_name': 'PostToolUse', 'tool_name': 'Read',
                'tool_input': {'file_path': str(self.root / name)}, 'tool_response': {'content': 'ignored'}, 'tool_use_id': 'read-%d' % index}
            core.handle_event(self.root, event, 'claude')
        state = core.load_state(self.root, core.scope_for(self.root, self.payload))
        self.assertEqual(5, len(state['files']))
        self.assertTrue(state['files'][-1]['critical'])
        self.put('src/6.txt', 'NEW_BODY_NOT_REINJECTED')
        result = core.handle_event(self.root, {**self.payload, 'hook_event_name': 'SessionStart', 'source': 'compact'}, 'claude')
        self.assertIn('src/6.txt', result)
        self.assertNotIn('BODY_NOT_REINJECTED', result)
        self.assertIn(core.reference(self.root, 'file', 'src/6.txt')['version'], result)

    def test_failed_read_and_private_paths_do_not_create_state(self):
        self.config(checkpoint=True)
        self.put('.env', 'fixture confidential data')
        for response, name in [({'isError': True}, 'missing'), ({}, '.env')]:
            core.handle_event(self.root, {**self.payload, 'hook_event_name': 'PostToolUse', 'tool_name': 'Read', 'tool_input': {'file_path': str(self.root / name)}, 'tool_response': response}, 'claude')
        self.assertFalse((self.root / 'var').exists())

    def test_linked_and_foreign_checkpoint_refused(self):
        scope = core.scope_for(self.root, self.payload)
        location = self.put(core.state_relative(scope), json.dumps({'schemaVersion': 1, **scope, 'sessionId': 'foreign', 'refs': [], 'files': []}))
        with self.assertRaises(ValueError):
            core.load_state(self.root, scope)
        location.unlink()
        outside = self.put('original.json', '{}')
        os.link(outside, location)
        with self.assertRaises(ValueError):
            core.load_state(self.root, scope)
        with self.assertRaises(ValueError):
            core.safe_path(self.root, '../outside')

    def test_native_entrypoints_emit_correct_envelopes_and_no_checkpoint_by_default(self):
        for adapter in ['claude', 'codex']:
            directory = self.root / ('.' + adapter) / 'hooks'
            directory.mkdir(parents=True, exist_ok=True)
            for name in ['rule-inject.py', 'continuity.py']:
                shutil.copy2(ROOT / 'core/hooks' / name, directory)
            if adapter == 'codex':
                shutil.copy2(ROOT / 'targets/codex/hooks/codex-hook.py', directory)
            script = directory / ('codex-hook.py' if adapter == 'codex' else 'rule-inject.py')
            command = [sys.executable, '-B', str(script)] + ([] if adapter == 'codex' else ['--session-start'])
            payload = {**self.payload, 'hook_event_name': 'SessionStart', 'source': 'compact'}
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
            proc = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True, encoding='utf-8', env=env)
            self.assertEqual(0, proc.returncode, proc.stderr)
            text = proc.stdout if adapter == 'claude' else json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
            self.assertIn('Context was just compacted', text)
            self.assertIn('Durable checkpoint unavailable', text)
            self.assertFalse((self.root / 'var').exists())
            self.config(mode='off')
            proc = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True, encoding='utf-8', env=env)
            self.assertEqual('', proc.stdout)
            (self.root / '.airules/continuity.json').unlink()


if __name__ == '__main__':
    unittest.main()
