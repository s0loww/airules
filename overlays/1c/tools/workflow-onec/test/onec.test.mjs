import test from 'node:test'
import assert from 'node:assert/strict'
import { validateOnecProfile, createOnecProfileAdapter } from '../index.mjs'
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { WorkflowHost } from '../../../../../core/tools/workflow/index.mjs'

function profile(overrides = {}) {
  return { schemaVersion: 1, projectId: 'fixture', sourceDir: 'src', resultDir: 'reports',
    platform: { versionPrefix: '8.3.27', engine: 'auto' },
    extension: { name: 'FixtureExtension' }, testTarget: { kind: 'file', environment: 'test' }, ...overrides }
}
const facts = { sourceKind: 'extension', extensionName: 'FixtureExtension', exactBuild: '8.3.27.1989' }

test('offline domain gate runs in generic workflow host without platform or MCP', async t => {
  const temporary = await mkdtemp(join(tmpdir(), 'workflow-domain-'))
  t.after(() => rm(temporary, { recursive: true, force: true }))
  const root = join(temporary, 'project')
  await mkdir(join(root, 'src'), { recursive: true }); await writeFile(join(root, 'src', 'fixture.txt'), 'fixture')
  await writeFile(join(root, 'binding.json'), JSON.stringify({ schemaVersion: 1, projectId: 'fixture',
    providers: { profile: { adapterId: 'onec.profile' } }, inputs: { metadata: { profile: profile(), ...facts } } }))
  const host = new WorkflowHost({ stateDir: join(temporary, 'state'), authorize: () => true,
    projects: { fixture: { root, bindingPath: 'binding.json', sourcePaths: ['src'] } },
    workflows: { metadata: { schemaVersion: 1, id: 'metadata', version: '0.1.0', steps: [
      { id: 'metadata', adapter: 'profile', operation: 'validate-profile' },
    ] } }, adapters: { 'onec.profile': createOnecProfileAdapter() } })
  const p = await host.plan({ projectId: 'fixture', workflowId: 'metadata', principal: 'operator' })
  const result = await host.run({ planId: p.id, planDigest: p.planDigest, requestId: 'offline', principal: 'operator' })
  assert.equal(result.verdict, 'PASS'); assert.equal(result.mutationState, 'not-applied')
  assert.deepEqual(result.steps[0].effects, ['readsSource'])
})

test('file profile validates metadata without pretending execution or tests are configured', () => {
  const result = validateOnecProfile(profile(), facts)
  assert.equal(result.complete, true)
  assert.ok(result.assertions.every(x => x.passed))
  assert.equal(result.capabilities.execution.status, 'not-configured')
  assert.equal(result.capabilities.unit.status, 'not-configured')
  assert.equal(result.capabilities.postdeployProbe.status, 'not-configured')
  assert.equal(result.capabilities.vanessa.status, 'not-configured')
})

test('explicit unit/probe/Vanessa metadata is declared, never asserted as reachable', () => {
  const result = validateOnecProfile(profile({ unit: { launchParameter: 'RUN_TESTS' },
    probe: { checkModules: ['Server', 'ThinClient'] }, vanessa: { connection: 'ibsrv' } }), facts)
  assert.equal(result.capabilities.unit.status, 'declared')
  assert.equal(result.capabilities.postdeployProbe.status, 'declared')
  assert.equal(result.capabilities.vanessa.status, 'declared')
})

test('server supports Designer metadata but not file-only Vanessa', () => {
  const p = profile({ testTarget: { kind: 'server', environment: 'development' }, vanessa: { connection: 'file' } })
  assert.equal(validateOnecProfile(p, facts).capabilities.vanessa.status, 'unsupported')
  p.platform.engine = 'ibcmd'
  assert.throws(() => validateOnecProfile(p, facts), /CLUSTER_IBCMD_FORBIDDEN/u)
})

test('production is representable and explicitly flagged, not executed', () => {
  const result = validateOnecProfile(profile({ testTarget: { kind: 'file', environment: 'production' } }), facts)
  assert.equal(result.productionAuthorizationRequired, true)
  assert.equal(result.capabilities.execution.status, 'not-configured')
})

test('environment and target kind fail closed', () => {
  for (const environment of [undefined, '', 'prod', 'anything']) {
    assert.throws(() => validateOnecProfile(profile({ testTarget: { kind: 'file', environment } }), facts), /TARGET_ENVIRONMENT_REQUIRED/u)
  }
  assert.throws(() => validateOnecProfile(profile({ testTarget: { kind: 'none', environment: 'test' } }), facts), /TARGET_KIND_UNSUPPORTED/u)
})

test('source identity requires explicit kind and exact matching extension', () => {
  assert.throws(() => validateOnecProfile(profile(), { ...facts, sourceKind: undefined }), /SOURCE_KIND_REQUIRED/u)
  assert.throws(() => validateOnecProfile(profile(), { ...facts, extensionName: undefined }), /EXTENSION_NAME_REQUIRED/u)
  assert.throws(() => validateOnecProfile(profile(), { ...facts, extensionName: 'Other' }), /EXTENSION_NAME_MISMATCH/u)
  assert.throws(() => validateOnecProfile(profile(), { ...facts, sourceKind: 'configuration', extensionName: undefined }), /CONFIGURATION_EXTENSION_CONFLICT/u)
  const base = profile(); delete base.extension
  assert.equal(validateOnecProfile(base, { sourceKind: 'configuration', exactBuild: facts.exactBuild }).complete, true)
})

test('prefix alone is insufficient and fullbuild conflict is rejected', () => {
  assert.throws(() => validateOnecProfile(profile(), { ...facts, exactBuild: '8.3.27' }), /EXACT_BUILD_REQUIRED/u)
  assert.throws(() => validateOnecProfile(profile(), { ...facts, exactBuild: '8.3.28.1' }), /PLATFORM_BUILD_MISMATCH/u)
  assert.throws(() => validateOnecProfile(profile({ platform: { versionPrefix: '8.3.27.1786' } }), facts), /PLATFORM_BUILD_MISMATCH/u)
  assert.equal(validateOnecProfile(profile({ platform: { versionPrefix: '8.3.27.1989' } }), facts).complete, true)
})

test('malformed optional configurations do not become configured capabilities', () => {
  for (const patch of [{ probe: { checkModules: ['Invented'] } }, { probe: { checkModules: ['Server', 'Server'] } },
    { unit: { launchParameter: '' } }, { vanessa: { connection: 'server' } }, { extension: { name: 'FixtureExtension', safeMode: 'false' } },
    { extension: { name: 4 } }, { platform: { executable: 4 } }, { probe: { baseline: false } },
    { suspendServices: [''] }, { testTarget: { kind: 'file', environment: 'test', envSection: false } }]) {
    assert.throws(() => validateOnecProfile(profile(patch), facts))
  }
})

test('secret inputs, cycles and unsafe keys are rejected without echoing values', () => {
  const secret = 'fixture-sensitive-value' // airules:allow creds-token — synthetic rejection fixture
  const p = profile({ testTarget: { kind: 'file', environment: 'test', password: secret } }) // airules:allow creds-password — synthetic rejection fixture
  assert.throws(() => validateOnecProfile(p, facts), error => error.code === 'INLINE_CREDENTIALS_NOT_SUPPORTED' && !error.message.includes(secret))
  const cyclic = profile(); cyclic.loop = cyclic
  assert.throws(() => validateOnecProfile(cyclic, facts), /PROFILE_CYCLE/u)
  const unsafe = JSON.parse('{"__proto__":{}}')
  assert.throws(() => validateOnecProfile(unsafe, facts), /PROFILE_UNSAFE_KEY/u)
})

test('adapter has a nonmutating operation and returns only normalized evidence', async () => {
  const adapter = createOnecProfileAdapter()
  assert.equal(adapter.descriptor.id, 'onec.profile')
  assert.deepEqual(adapter.descriptor.operations['validate-profile'].effects, ['readsSource'])
  const result = await adapter.execute('validate-profile', { profile: profile(), ...facts })
  assert.equal(result.mutationState, 'not-applied')
  assert.equal(JSON.stringify(result).includes('FixtureExtension'), false)
  assert.equal(JSON.stringify(result).includes('sourceDir'), false)
  assert.throws(() => adapter.execute('deploy', {}), /OPERATION_UNSUPPORTED/u)
  const fingerprint = await adapter.fingerprint()
  assert.match(fingerprint, /^[a-f0-9]{64}$/u)
  assert.equal(await adapter.fingerprint(), fingerprint)
  adapter.descriptor.version = '0.1.1'
  assert.notEqual(await adapter.fingerprint(), fingerprint)
})
