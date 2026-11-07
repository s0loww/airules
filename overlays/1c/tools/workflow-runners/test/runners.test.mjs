import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, readFile, rm, symlink } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { inspectRunnerBinding, compileRunnerCommand } from '../index.mjs'

const runner = 'tools/agent-1c/agent-1c.ps1'
const agentHeader = "param([ValidateSet('bootstrap','doctor','analyze','deploy','test','unit','serve','stop')] [string]$Command='doctor', [string]$Profile, [switch]$Apply, [switch]$Hidden)\nfunction Placeholder {}"
const profile = () => ({ schemaVersion: 1, projectId: 'fixture', sourceDir: 'src', resultDir: 'reports',
  platform: { engine: 'auto', versionPrefix: '8.3.27' }, extension: { name: 'Fixture' },
  testTarget: { kind: 'file', environment: 'test', envFile: '../SECRET_MUST_NOT_READ.env', envSection: 'TEST' } })
const binding = () => ({ schemaVersion: 1, kind: 'agent-1c', runnerPath: runner, profilePath: 'agent-1c.json',
  sourceKind: 'extension', extensionName: 'Fixture', exactBuild: '8.3.27.1989' })
async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'workflow-runners-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  await mkdir(join(root, 'tools/agent-1c/lib'), { recursive: true }); await mkdir(join(root, 'scripts'))
  await writeFile(join(root, runner), agentHeader)
  for (const name of ['1c-guard.ps1', 'hidden-desktop.ps1']) await writeFile(join(root, 'tools/agent-1c/lib', name), '# fixture only')
  await writeFile(join(root, 'tools/agent-1c/toolchain.lock.json'), '{}')
  await writeFile(join(root, 'agent-1c.json'), JSON.stringify(profile()))
  await writeFile(join(root, 'scripts/RunUnitTests.ps1'), 'param()\n. "$PSScriptRoot/TestEnv.ps1"')
  await writeFile(join(root, 'scripts/TestEnv.ps1'), '# Fixture only. Never executed.')
  return root
}

test('inspection discovers declaration metadata without reading external credentials or enabling execution', async t => {
  const root = await fixture(t)
  const result = await inspectRunnerBinding({ root, binding: binding() })
  assert.equal(result.operations.doctor.supported, true)
  assert.equal(result.operations.unit.supported, true)
  assert.equal(result.operations.unit.configured, false)
  assert.equal(result.operations['test-hidden'].supported, true)
  assert.equal(result.operations['test-hidden'].configured, false)
  assert.equal(result.operations['deploy-preview'].readsCredentialReferences, true)
  assert.equal(result.credentialsResolved, false)
  assert.equal(result.sourceFactsVerified, false)
  assert.equal(result.pinnedBuildVerified, false)
  assert.ok(Object.values(result.operations).every(op => op.enabled === false))
  assert.equal(result.deployEnabled, false)
  assert.equal(JSON.stringify(result).includes('SECRET_MUST_NOT_READ'), false)
  assert.equal(result.dependencies.length, 3)
  assert.match(result.closureDigest, /^[a-f0-9]{64}$/u)
  assert.equal(result.codeClosure.reviewRequired, true)
  assert.ok(result.fingerprintPaths.includes(runner))
  assert.ok(result.fingerprintPaths.includes('agent-1c.json'))
})

test('old agent runner does not acquire newer commands from another installed copy', async t => {
  const root = await fixture(t)
  await writeFile(join(root, runner), "param([ValidateSet('doctor','analyze','deploy','test')] [string]$Command='doctor', [string]$Profile, [switch]$Apply)\n")
  const result = await inspectRunnerBinding({ root, binding: binding() })
  assert.equal(result.operations.unit.supported, false)
  assert.equal(result.operations['test-hidden'].supported, false)
  assert.equal(result.operations.serve.supported, false)
})

test('server target refuses ibcmd and declares file-only scenarios unsupported', async t => {
  const root = await fixture(t); const p = profile(); p.testTarget.kind = 'server'
  await writeFile(join(root, 'agent-1c.json'), JSON.stringify(p))
  const result = await inspectRunnerBinding({ root, binding: binding() })
  assert.equal(result.operations.test.supported, false)
  assert.equal(result.operations.serve.supported, false)
  p.platform.engine = 'ibcmd'; await writeFile(join(root, 'agent-1c.json'), JSON.stringify(p))
  await assert.rejects(inspectRunnerBinding({ root, binding: binding() }), /CLUSTER_IBCMD_FORBIDDEN/u)
})

test('TestEnv is a distinct unit adapter with import/update effects and no automated UI', async t => {
  const root = await fixture(t)
  const result = await inspectRunnerBinding({ root, binding: { schemaVersion: 1, kind: 'test-env', runnerPath: 'scripts/RunUnitTests.ps1' } })
  assert.equal(result.operations.unit.supported, true)
  assert.equal(result.operations.unit.enabled, false)
  assert.equal(result.operations.unit.needsIsolation, true)
  assert.ok(result.operations.unit.effects.includes('changesMetadata'))
  assert.equal(result.operations.test.supported, false)
  assert.equal(result.dependencies[0].path, 'scripts/TestEnv.ps1')
})

test('runner/profile/dependency changes alter the inspection fingerprint', async t => {
  const root = await fixture(t)
  const inspect = () => inspectRunnerBinding({ root, binding: binding() })
  const first = await inspect()
  await writeFile(join(root, 'tools/agent-1c/lib/extra.psm1'), '# extra local module')
  const added = await inspect(); assert.notEqual(added.closureDigest, first.closureDigest)
  assert.ok(added.fingerprintPaths.includes('tools/agent-1c/lib/extra.psm1'))
  await writeFile(join(root, 'tools/agent-1c/secret.env'), 'UNREAD_SECRET_CONTENT')
  const untrackedEnv = await inspect(); assert.equal(untrackedEnv.closureDigest, added.closureDigest)
  assert.equal(untrackedEnv.fingerprintPaths.some(path => path.endsWith('.env')), false)
  await writeFile(join(root, 'tools/agent-1c/lib/1c-guard.ps1'), '# changed guard')
  const second = await inspect(); assert.notEqual(second.fingerprint, first.fingerprint)
  const p = profile(); p.unit = { launchParameter: 'RUN_TESTS' }; await writeFile(join(root, 'agent-1c.json'), JSON.stringify(p))
  const third = await inspect(); assert.notEqual(third.fingerprint, second.fingerprint)
  assert.equal(third.closureDigest, second.closureDigest)
  assert.equal(third.operations.unit.configured, true)
})

test('compile produces argv arrays, never Apply or arbitrary argument interpolation', async t => {
  const root = await fixture(t); const pwshPath = resolve(root, 'pwsh.exe')
  const options = { runnerKind: 'agent-1c', operation: 'deploy-preview', root, runnerPath: runner,
    profilePath: 'agent-1c.json', pwshPath }
  const result = compileRunnerCommand(options)
  assert.deepEqual(result.args, ['-NoLogo', '-NoProfile', '-NonInteractive', '-File', resolve(root, runner), 'deploy', '-Profile', resolve(root, 'agent-1c.json')])
  assert.equal(result.args.includes('-Apply'), false)
  assert.equal(result.enabled, false)
  assert.throws(() => compileRunnerCommand({ ...options, operation: 'deploy' }), /RUNNER_OPERATION_UNSUPPORTED/u)
  assert.throws(() => compileRunnerCommand({ ...options, apply: true }), /RUNNER_BINDING_INVALID/u)
  assert.throws(() => compileRunnerCommand({ ...options, args: ['-Apply'] }), /RUNNER_BINDING_INVALID/u)
  const hidden = compileRunnerCommand({ ...options, operation: 'test-hidden' })
  assert.ok(hidden.args.includes('-Hidden'))
  assert.equal(hidden.args.includes('-Apply'), false)
})

test('TestEnv compiler accepts only its fixed unit entrypoint', async t => {
  const root = await fixture(t); const options = { runnerKind: 'test-env', operation: 'unit', root,
    runnerPath: 'scripts/RunUnitTests.ps1', pwshPath: resolve(root, 'pwsh.exe') }
  assert.equal(compileRunnerCommand(options).args.at(-1), resolve(root, 'scripts/RunUnitTests.ps1'))
  assert.throws(() => compileRunnerCommand({ ...options, runnerPath: 'scripts/RunAllTests.ps1' }), /RUNNER_NOT_ALLOWLISTED/u)
  assert.throws(() => compileRunnerCommand({ ...options, operation: 'test' }), /RUNNER_OPERATION_UNSUPPORTED/u)
})

test('malformed metadata, unknown fields and traversal fail without secret values', async t => {
  const root = await fixture(t)
  for (const patch of [{ runnerPath: '../outside.ps1' }, { runnerPath: 'other.ps1' }, { profilePath: '../profile.json' },
    { profilePath: '.env' }, { args: ['-Apply'] }, { kind: 'unknown' }]) {
    await assert.rejects(inspectRunnerBinding({ root, binding: { ...binding(), ...patch } }))
  }
  const p = profile(); p.testTarget.password = 'DO_NOT_DISCLOSE' // airules:allow creds-password — synthetic rejection fixture
  await writeFile(join(root, 'agent-1c.json'), JSON.stringify(p))
  await assert.rejects(inspectRunnerBinding({ root, binding: binding() }), error => !error.message.includes('DO_NOT_DISCLOSE'))
  assert.throws(() => compileRunnerCommand({ runnerKind: 'agent-1c', operation: 'doctor', root,
    runnerPath: runner, profilePath: 'agent-1c.json', pwshPath: resolve(root, 'cmd.exe') }), /TRUSTED_POWERSHELL_REQUIRED/u)
})

test('symlink profile and missing declared dependency are rejected', async t => {
  const root = await fixture(t)
  await rm(join(root, 'tools/agent-1c/lib/hidden-desktop.ps1'))
  await assert.rejects(inspectRunnerBinding({ root, binding: binding() }))
  await writeFile(join(root, 'tools/agent-1c/lib/hidden-desktop.ps1'), '# restored')
  const contents = await readFile(join(root, 'agent-1c.json'))
  await writeFile(join(root, 'outside.json'), contents); await rm(join(root, 'agent-1c.json'))
  try { await symlink(join(root, 'outside.json'), join(root, 'agent-1c.json'), 'file') }
  catch (error) { if (['EPERM', 'EACCES'].includes(error.code)) { t.skip('Host does not permit file symlinks'); return } throw error }
  await assert.rejects(inspectRunnerBinding({ root, binding: binding() }), /SYMLINK_INPUT/u)
})

test('oversized and invalid UTF-8 metadata are rejected before interpretation', async t => {
  const root = await fixture(t)
  await writeFile(join(root, 'agent-1c.json'), Buffer.alloc(512 * 1024 + 1, 32))
  await assert.rejects(inspectRunnerBinding({ root, binding: binding() }), /UNSAFE_INPUT_FILE|INPUT_LIMIT/u)
  await writeFile(join(root, 'agent-1c.json'), Buffer.from([0xff, 0xfe]))
  await assert.rejects(inspectRunnerBinding({ root, binding: binding() }), /RUNNER_UTF8_REQUIRED/u)
})
