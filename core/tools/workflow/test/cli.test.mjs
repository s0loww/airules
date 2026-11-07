import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, writeFile, rm, lstat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFile } from 'node:child_process'

const cli = fileURLToPath(new URL('../cli.mjs', import.meta.url))
const run = args => new Promise(resolve => {
  execFile(process.execPath, [cli, ...args], { windowsHide: true, timeout: 30000, maxBuffer: 1024 * 1024 },
    (error, stdout, stderr) => resolve({ code: error?.code ?? 0, output: JSON.parse(stdout), stderr }))
})
async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'workflow-cli-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const project = join(root, 'project'); await mkdir(project)
  await mkdir(join(project, 'src')); await writeFile(join(project, 'src', 'input.txt'), 'fixture')
  const marker = join(root, 'marker.txt'); const runner = join(root, 'runner.mjs')
  await writeFile(runner, `import {appendFileSync} from 'node:fs'; appendFileSync(process.argv[2], 'executed\\n'); console.log('DO_NOT_LEAK');`)
  await writeFile(join(project, 'binding.json'), JSON.stringify({ schemaVersion: 1, projectId: 'fixture',
    providers: { technical: { adapterId: 'node.fixture' } } }))
  const registryPath = join(root, 'host.json')
  const registry = {
    schemaVersion: 1, stateDir: join(root, 'state'),
    projects: { fixture: { root: project, bindingPath: 'binding.json', sourcePaths: ['src'], configPaths: [] } },
    workflows: { smoke: { schemaVersion: 1, id: 'smoke', version: '1.0.0', steps: [
      { id: 'technical-check', adapter: 'technical', operation: 'check', timeoutMs: 5000 },
    ] } },
    localAdapters: { 'node.fixture': { version: '1.0.0', operations: { check: {
      command: process.execPath, args: [runner, marker, ''], fingerprintPaths: [runner],
      inputSchema: { type: 'object', additionalProperties: false }, effects: ['startsProcess', 'writesFilesystem'], validator: 'process-exit',
    } } } },
  }
  const save = () => writeFile(registryPath, JSON.stringify(registry))
  await save()
  return { root, project, marker, runner, registryPath, registry, save }
}
async function plan(f) {
  const result = await run(['plan', '--registry', f.registryPath, '--project', 'fixture', '--workflow', 'smoke'])
  assert.equal(result.code, 0, JSON.stringify(result))
  return result.output.result
}
const executeArgs = (f, p, request = 'request-1') => ['run', '--registry', f.registryPath,
  '--plan', p.id, '--digest', p.planDigest, '--request', request, '--execute']

test('plan creates no child execution and works without MCP', async t => {
  const f = await fixture(t); const p = await plan(f)
  assert.equal(p.steps[0].configured, true)
  await assert.rejects(readFile(f.marker), { code: 'ENOENT' })
  assert.equal(JSON.stringify(p).includes('DO_NOT_LEAK'), false)
})

test('CLI capabilities reports declarations without execution or creating state', async t => {
  const f = await fixture(t)
  const result = await run(['capabilities', '--registry', f.registryPath, '--project', 'fixture', '--workflow', 'smoke'])
  assert.equal(result.code, 0)
  assert.equal(result.output.result.steps[0].status, 'configured')
  assert.equal(result.output.result.steps[0].availability, 'not-probed')
  await assert.rejects(readFile(f.marker), { code: 'ENOENT' })
  await assert.rejects(lstat(f.registry.stateDir), { code: 'ENOENT' })
})

test('run requires explicit execute, executes one safe process and deduplicates across CLI invocations', async t => {
  const f = await fixture(t); const p = await plan(f)
  const denied = await run(executeArgs(f, p).filter(arg => arg !== '--execute'))
  assert.equal(denied.output.error, 'EXECUTE_FLAG_REQUIRED')
  await assert.rejects(readFile(f.marker), { code: 'ENOENT' })
  const first = await run(executeArgs(f, p))
  assert.equal(first.code, 0, JSON.stringify(first))
  assert.equal(first.output.result.verdict, 'PASS')
  assert.equal(JSON.stringify(first.output).includes('DO_NOT_LEAK'), false)
  const second = await run(executeArgs(f, p))
  assert.equal(second.output.result.runId, first.output.result.runId)
  assert.equal(await readFile(f.marker, 'utf8'), 'executed\n')
  const result = await run(['result', '--registry', f.registryPath, '--run', first.output.result.runId])
  assert.equal(result.output.result.verdict, 'PASS')
})

test('registry changes seal captured arguments and block stale plan', async t => {
  const f = await fixture(t); const p = await plan(f)
  f.registry.localAdapters['node.fixture'].operations.check.args.push('changed')
  await f.save()
  const result = await run(executeArgs(f, p))
  assert.equal(result.code, 1)
  assert.equal(result.output.result.reason, 'STALE_PLAN')
  await assert.rejects(readFile(f.marker), { code: 'ENOENT' })
})

test('unknown registry fields and unsafe credentials stay out of error output', async t => {
  const f = await fixture(t)
  f.registry.clientSecret = 'SENSITIVE_FIXTURE_VALUE'; await f.save() // airules:allow creds-token — synthetic rejection fixture
  const result = await run(['plan', '--registry', f.registryPath, '--project', 'fixture', '--workflow', 'smoke'])
  assert.equal(result.code, 1)
  assert.equal(result.output.error, 'INVALID_REGISTRY')
  assert.equal(JSON.stringify(result).includes('SENSITIVE_FIXTURE_VALUE'), false)
})

test('target mutations stay disabled even with explicit execute', async t => {
  const f = await fixture(t)
  f.registry.localAdapters['node.fixture'].operations.check.effects.push('changesMetadata')
  f.registry.localAdapters['node.fixture'].operations.check.validator = 'assertions'
  f.registry.projects.fixture.resources = { target: { id: 'fixture-target', environment: 'test' } }
  f.registry.workflows.smoke.steps[0].resources = ['target']
  await f.save(); const p = await plan(f)
  const result = await run(executeArgs(f, p))
  assert.equal(result.output.result.reason, 'TARGET_MUTATIONS_DISABLED')
  await assert.rejects(readFile(f.marker), { code: 'ENOENT' })
})

test('CLI rejects relative registry, injected owner/command flags and missing values', async () => {
  for (const args of [[], ['plan', '--registry', 'relative.json', '--project', 'p', '--workflow', 'w'],
    ['plan', '--registry', cli, '--project', 'p', '--workflow', 'w', '--owner', 'admin'],
    ['plan', '--registry', cli, '--project', '--workflow', 'w']]) {
    const result = await run(args)
    assert.equal(result.code, 1)
    assert.equal(result.output.ok, false)
    assert.equal(result.stderr, '')
  }
})
