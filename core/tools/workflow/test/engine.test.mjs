import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, writeFile, rm, readdir, symlink } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { WorkflowHost } from '../index.mjs'
import { digest } from '../lib/contracts.mjs'
import { createMcpAdapter } from '../lib/mcp-adapter.mjs'
import { createReportProcessAdapter } from '../lib/report-process.mjs'

const schema = { type: 'object', additionalProperties: false }
const proofSchema = { type: 'object', required: ['complete', 'assertions'], properties: {
  complete: { type: 'boolean' }, assertions: { type: 'array', items: { type: 'object', required: ['id', 'passed'],
    properties: { id: { type: 'string' }, passed: { type: 'boolean' } }, additionalProperties: false } },
}, additionalProperties: false }
const proof = (passed = true, state = 'not-applied') => ({ data: { complete: true, assertions: [{ id: 'fixture', passed }] }, mutationState: state })
function adapter(id = 'fixture', execute = async () => proof(), effects = ['readsSource']) {
  const descriptor = { protocolVersion: 1, id, version: '0.1.0', operations: {
    check: { inputSchema: schema, resultSchema: proofSchema, effects, validator: 'assertions' },
  } }
  return { descriptor, execute, fingerprint: async () => digest({ descriptor, implementation: execute.toString() }) }
}
async function fixture(t, { steps, adapters, allowTargetMutations = false, authorize = async () => true } = {}) {
  const temporary = await mkdtemp(join(tmpdir(), 'workflow-engine-'))
  t.after(() => rm(temporary, { recursive: true, force: true }))
  const root = join(temporary, 'project'), stateDir = join(temporary, 'state')
  await mkdir(join(root, 'src'), { recursive: true }); await writeFile(join(root, 'src', 'input.txt'), 'initial')
  await writeFile(join(root, 'profile.json'), '{"build":"fixture"}')
  const binding = { schemaVersion: 1, projectId: 'project', providers: { local: { adapterId: 'fixture' }, direct: { adapterId: 'direct-mcp' } } }
  await writeFile(join(root, 'binding.json'), JSON.stringify(binding))
  const options = { stateDir, projects: { project: { root, bindingPath: 'binding.json', sourcePaths: ['src'], configPaths: ['profile.json'],
    resources: { db: { id: 'shared-target', environment: 'test' }, alias: { id: 'shared-target', environment: 'test' } } } },
    workflows: { check: { schemaVersion: 1, id: 'check', version: '0.1.0', steps: steps ?? [{ id: 'source', adapter: 'local', operation: 'check' }] } },
    adapters: adapters ?? { fixture: adapter() }, authorize, allowTargetMutations }
  const host = new WorkflowHost(options)
  const plan = () => host.plan({ projectId: 'project', workflowId: 'check', principal: 'alice' })
  const run = (p, requestId = 'request') => host.run({ planId: p.id, planDigest: p.planDigest, principal: 'alice', requestId })
  return { host, options, plan, run, root, stateDir, binding }
}

test('data-only plan and two providers work without a facade; repeat plan does not execute', async t => {
  let calls = 0
  const f = await fixture(t, { adapters: { fixture: adapter('fixture', async () => { calls++; return proof() }),
    'direct-mcp': adapter('direct-mcp', async () => { calls++; return proof() }) }, steps: [
    { id: 'source', adapter: 'local', operation: 'check' },
    { id: 'domain', adapter: 'direct', operation: 'check', dependsOn: ['source'] },
  ] })
  const p = await f.plan(); assert.equal(calls, 0)
  const result = await f.run(p); assert.equal(result.verdict, 'PASS'); assert.equal(calls, 2)
  assert.equal((await f.run(p)).runId, result.runId)
  assert.equal((await f.run(p, 'new-request')).runId, result.runId); assert.equal(calls, 2)
})

test('source, profile, binding and adapter changes invalidate a plan', async t => {
  for (const changed of ['source', 'profile', 'binding', 'adapter']) {
    let invoked = false
    const a = adapter('fixture', async () => { invoked = true; return proof() })
    const f = await fixture(t, { adapters: { fixture: a } }); const p = await f.plan()
    if (changed === 'source') await writeFile(join(f.root, 'src', 'new-untracked.txt'), 'added')
    if (changed === 'profile') await writeFile(join(f.root, 'profile.json'), '{}')
    if (changed === 'binding') await writeFile(join(f.root, 'binding.json'), JSON.stringify({ ...f.binding, inputs: { source: {} } }))
    if (changed === 'adapter') a.fingerprint = async () => digest('new-adapter')
    const result = await f.run(p)
    assert.equal(result.verdict, 'BLOCKED'); assert.equal(result.reason, 'STALE_PLAN'); assert.equal(invoked, false)
  }
})

test('input changed during final execution cannot yield PASS', async t => {
  let root
  const f = await fixture(t, { adapters: { fixture: adapter('fixture', async () => {
    await writeFile(join(root, 'src', 'input.txt'), 'changed while running'); return proof()
  }) } }); root = f.root
  const result = await f.run(await f.plan())
  assert.equal(result.verdict, 'INDETERMINATE'); assert.equal(result.steps[0].reason, 'INPUT_CHANGED_DURING_EXECUTION')
  assert.equal(result.steps[0].evidence.validated, false)
})

test('ownership and effect authorization checked independently of plan digest', async t => {
  const f = await fixture(t, { authorize: async request => request.principal === 'alice' && request.action !== 'execute' })
  const p = await f.plan()
  await assert.rejects(f.host.run({ planId: p.id, planDigest: p.planDigest, requestId: 'foreign', principal: 'bob' }), /NOT_AUTHORIZED/u)
  const result = await f.run(p); assert.equal(result.verdict, 'BLOCKED'); assert.equal(result.reason, 'NOT_AUTHORIZED')
  await assert.rejects(f.host.result({ runId: result.runId, principal: 'bob' }), /NOT_AUTHORIZED/u)
})

test('target execution disabled by default and unknown environment never accepted', async t => {
  let calls = 0
  const f = await fixture(t, { adapters: { fixture: adapter('fixture', async () => { calls++; return proof(true, 'applied') }, ['changesMetadata']) },
    steps: [{ id: 'load', adapter: 'local', operation: 'check', resources: ['db'] }] })
  const result = await f.run(await f.plan())
  assert.equal(result.reason, 'TARGET_MUTATIONS_DISABLED'); assert.equal(calls, 0)
  f.host.projects.project.resources.db.environment = 'unknown'
  await assert.rejects(f.plan(), /UNKNOWN_ENVIRONMENT/u)
})

test('same physical target aliases lock across host instances', async t => {
  let release, entered
  const started = new Promise(resolve => { entered = resolve })
  const wait = new Promise(resolve => { release = resolve })
  const a = adapter('fixture', async () => { entered(); await wait; return proof() })
  const f = await fixture(t, { adapters: { fixture: a }, steps: [{ id: 'check', adapter: 'local', operation: 'check', resources: ['db'] }] })
  const firstPlan = await f.plan(), secondPlan = await f.plan()
  const first = f.run(firstPlan); await started
  const secondHost = new WorkflowHost(f.options)
  const busy = await secondHost.run({ planId: secondPlan.id, planDigest: secondPlan.planDigest, principal: 'alice', requestId: 'second' })
  assert.equal(busy.reason, 'RESOURCE_BUSY')
  const status = await secondHost.result({ runId: (await jsonRun(f.stateDir)).runId, principal: 'alice' })
  assert.equal(status.verdict, 'RUNNING'); assert.equal(status.observation, 'owner-not-attached')
  release(); assert.equal((await first).verdict, 'PASS')
})
async function jsonRun(stateDir) {
  for (const id of await readdir(join(stateDir, 'runs'))) {
    const result = JSON.parse(await readFile(join(stateDir, 'runs', id, 'result.json'), 'utf8'))
    if (!result.finishedAt) return result
  }
  throw new Error('running fixture missing')
}

test('applied state survives later failure and not-applied result', async t => {
  let calls = 0
  const f = await fixture(t, { allowTargetMutations: true,
    adapters: { fixture: adapter('fixture', async () => ++calls === 1 ? proof(true, 'applied') : proof(false, 'not-applied'), ['changesMetadata']) },
    steps: [{ id: 'load', adapter: 'local', operation: 'check', resources: ['db'] },
      { id: 'update', adapter: 'local', operation: 'check', resources: ['alias'], dependsOn: ['load'] }] })
  const result = await f.run(await f.plan())
  assert.equal(result.verdict, 'FAIL'); assert.equal(result.mutationState, 'applied')
  assert.equal(result.recoveryState, 'required'); assert.equal(result.targets[0].stages.length, 2)
  assert.deepEqual(result.targets[0].stages.map(stage => stage.mutationState), ['applied', 'not-applied'])
})

test('optional uncertain mutation excludes PASS, retains locks and blocks further execution', async t => {
  let calls = 0
  const f = await fixture(t, { allowTargetMutations: true, adapters: { fixture: adapter('fixture', async () => { calls++; throw new Error('SENSITIVE_ERROR') }, ['changesMetadata']) },
    steps: [{ id: 'optional-load', adapter: 'local', operation: 'check', resources: ['db'], required: false },
      { id: 'next', adapter: 'local', operation: 'check', resources: ['alias'] }] })
  const result = await f.run(await f.plan())
  assert.equal(result.verdict, 'INDETERMINATE'); assert.equal(result.mutationState, 'unknown')
  assert.equal(result.retainedLocks, true); assert.equal(calls, 1); assert.equal(result.steps[1].status, 'blocked')
  assert.equal(JSON.stringify(result).includes('SENSITIVE_ERROR'), false)
  assert.equal((await readdir(join(f.stateDir, 'locks'))).length, 1)
})

test('crash journal marks mutation unknown before adapter starts', async t => {
  let stateDir
  const f = await fixture(t, { allowTargetMutations: true, adapters: { fixture: adapter('fixture', async () => {
    const journal = await jsonRun(stateDir)
    assert.equal(journal.mutationState, 'unknown'); assert.equal(journal.targets[0].recoveryState, 'required')
    return proof(true, 'applied')
  }, ['changesMetadata']) }, steps: [{ id: 'load', adapter: 'local', operation: 'check', resources: ['db'] }] }); stateDir = f.stateDir
  assert.equal((await f.run(await f.plan())).verdict, 'PASS')
})

test('blocked required gate stops later unrelated writes', async t => {
  let called = false
  const f = await fixture(t, { allowTargetMutations: true, adapters: { fixture: adapter('fixture', async () => { called = true; return proof() }) }, steps: [
    { id: 'missing', adapter: 'absent', operation: 'check', required: false },
    { id: 'required', adapter: 'local', operation: 'check', dependsOn: ['missing'] },
    { id: 'later', adapter: 'local', operation: 'check' },
  ] })
  const result = await f.run(await f.plan()); assert.equal(result.verdict, 'BLOCKED'); assert.equal(called, false)
})

test('expired/tampered plans and inline credentials rejected without execution', async t => {
  const f = await fixture(t)
  const p = await f.host.plan({ projectId: 'project', workflowId: 'check', principal: 'alice', ttlMs: 100 })
  await new Promise(resolve => setTimeout(resolve, 120))
  assert.equal((await f.run(p)).reason, 'PLAN_EXPIRED')
  await assert.rejects(f.host.run({ planId: p.id, planDigest: 'changed', principal: 'alice', requestId: 'changed' }), /PLAN_MISMATCH/u)
  await writeFile(join(f.root, 'binding.json'), JSON.stringify({ ...f.binding, password: 'DO_NOT_RECORD' })) // airules:allow creds-password — synthetic rejection fixture
  await assert.rejects(f.plan(), /INLINE_SECRET_FORBIDDEN/u)
})

test('cancel only owned active run, cleanup confirmed and no subsequent steps', async t => {
  let entered
  const started = new Promise(resolve => { entered = resolve })
  const f = await fixture(t, { adapters: { fixture: adapter('fixture', async (_operation, _input, context) => {
    entered(context.runId)
    await new Promise(resolve => context.signal.addEventListener('abort', resolve, { once: true }))
    return proof()
  }) } })
  const execution = f.run(await f.plan()); const runId = await started
  await assert.rejects(f.host.cancel({ runId, principal: 'bob' }), /RUN_NOT_OWNED_OR_NOT_ACTIVE/u)
  await f.host.cancel({ runId, principal: 'alice' })
  assert.equal((await execution).verdict, 'INTERRUPTED')
})

test('symlinked source is rejected rather than hashed outside project', async t => {
  const f = await fixture(t)
  try { await symlink(join(f.root, 'profile.json'), join(f.root, 'src', 'link.txt')) }
  catch (error) { if (error.code === 'EPERM') { t.skip('host cannot create symlink'); return }; throw error }
  await assert.rejects(f.plan(), /SYMLINK_INPUT/u)
})

test('core deadline cannot turn a late successful adapter into PASS', async t => {
  const f = await fixture(t, { adapters: { fixture: adapter('fixture', async () => {
    await new Promise(resolve => setTimeout(resolve, 160)); return proof()
  }) }, steps: [{ id: 'slow', adapter: 'local', operation: 'check', timeoutMs: 100 }] })
  const result = await f.run(await f.plan())
  assert.equal(result.verdict, 'FAIL'); assert.equal(result.steps[0].reason, 'STEP_TIMEOUT')
})

test('cannot remove a lock transferred to a different owner during execution', async t => {
  let stateDir
  const f = await fixture(t, { adapters: { fixture: adapter('fixture', async () => {
    const lockId = (await readdir(join(stateDir, 'locks')))[0]
    await writeFile(join(stateDir, 'locks', lockId, 'owner.json'), JSON.stringify({ runId: 'different-run', principal: 'other' }))
    return proof()
  }) }, steps: [{ id: 'owned', adapter: 'local', operation: 'check', resources: ['db'] }] }); stateDir = f.stateDir
  const result = await f.run(await f.plan())
  assert.equal(result.verdict, 'INDETERMINATE'); assert.equal(result.retainedLocks, true)
  assert.equal((await readdir(join(stateDir, 'locks'))).length, 1)
})

test('capability status is passive, missing provider affects only its step', async t => {
  let called = false
  const f = await fixture(t, { adapters: { fixture: adapter('fixture', async () => { called = true; return proof() }) }, steps: [
    { id: 'local', adapter: 'local', operation: 'check' }, { id: 'missing', adapter: 'absent', operation: 'check', required: false },
  ] })
  const result = await f.host.capabilities({ projectId: 'project', workflowId: 'check', principal: 'alice' })
  assert.deepEqual(result.steps.map(step => step.status), ['configured', 'not-configured'])
  assert.equal(called, false); assert.equal(result.steps[0].availability, 'not-probed')
  await assert.rejects(readdir(f.stateDir), { code: 'ENOENT' })
})

test('same workflow and adapter serve a new project using only registry and binding data', async t => {
  const f = await fixture(t)
  const root = join(f.root, 'another-project')
  await mkdir(join(root, 'src'), { recursive: true }); await writeFile(join(root, 'src', 'file.txt'), 'another')
  await writeFile(join(root, 'profile.json'), '{}')
  await writeFile(join(root, 'binding.json'), JSON.stringify({ ...f.binding, projectId: 'second' }))
  const options = { ...f.options, projects: { ...f.options.projects,
    second: { ...f.options.projects.project, root } } }
  const host = new WorkflowHost(options)
  const p = await host.plan({ projectId: 'second', workflowId: 'check', principal: 'alice' })
  const r = await host.run({ planId: p.id, planDigest: p.planDigest, principal: 'alice', requestId: 'second-project' })
  assert.equal(r.verdict, 'PASS'); assert.equal(r.projectId, 'second')
})

test('unregistered validator blocks planning; changed custom validator invalidates accepted inputs', async t => {
  const a = adapter()
  a.descriptor.operations.check.validator = 'custom'
  const f = await fixture(t, { adapters: { fixture: a } })
  await assert.rejects(f.plan(), /VALIDATOR_NOT_REGISTERED/u)
  f.host.validators.custom = () => ({ status: 'passed' })
  const p = await f.plan()
  f.host.validators.custom = () => ({ status: 'failed' })
  assert.equal((await f.run(p)).reason, 'STALE_PLAN')
})

test('host runs two explicit direct MCP providers through injected callers without a facade', async t => {
  const calls = []
  const registration = (id, connectionRef) => createMcpAdapter({ id, connectionRef, connectionRevision: 'revision-1',
    call: async args => { calls.push(args); return { actualAssertion: true } },
    operations: { check: { tool: 'check-explicit', inputSchema: schema, resultSchema: proofSchema,
      effects: ['readsSource'], validator: 'assertions', mapResult: raw => proof(raw.actualAssertion) } } })
  const f = await fixture(t, { adapters: { fixture: registration('fixture', 'direct-source'), 'direct-mcp': registration('direct-mcp', 'direct-project') },
    steps: [{ id: 'source', adapter: 'local', operation: 'check' }, { id: 'project', adapter: 'direct', operation: 'check', dependsOn: ['source'] }] })
  const p = await f.plan(); assert.equal(calls.length, 0)
  const result = await f.run(p); assert.equal(result.verdict, 'PASS')
  assert.deepEqual(calls.map(call => call.connectionRef), ['direct-source', 'direct-project'])
  assert.equal(calls[0].context.runId, result.runId)
})

test('host accepts fresh normalized test report and rejects zero-test rerun', async t => {
  const f = await fixture(t)
  const runner = join(f.root, 'report-runner.mjs')
  await writeFile(runner, `import {writeFileSync} from 'node:fs';
const [path,runId,sourceDigest,count] = process.argv.slice(2);
writeFileSync(path, JSON.stringify({runId,sourceDigest,complete:true,tests:Number(count),failures:0,errors:0,skipped:0}));`)
  const resultSchema = { type: 'object', required: ['runId', 'sourceDigest', 'complete', 'tests', 'failures', 'errors', 'skipped'],
    properties: { runId: { type: 'string' }, sourceDigest: { type: 'string' }, complete: { type: 'boolean' },
      tests: { type: 'integer' }, failures: { type: 'integer' }, errors: { type: 'integer' }, skipped: { type: 'integer' } }, additionalProperties: false }
  f.host.adapters.fixture = createReportProcessAdapter({ id: 'fixture', fingerprintPaths: [runner], operations: {
    check: { command: process.execPath, args: (inputs, context) => [runner, join(context.artifactDir, 'summary.json'), context.runId, context.sourceDigest, String(inputs.tests)],
      inputSchema: { type: 'object', required: ['tests'], properties: { tests: { type: 'integer', minimum: 0 } }, additionalProperties: false },
      resultSchema, effects: ['startsProcess', 'writesFilesystem'], validator: 'test-summary', reportPath: 'summary.json' },
  } })
  await writeFile(join(f.root, 'binding.json'), JSON.stringify({ ...f.binding, inputs: { source: { tests: 2 } } }))
  const first = await f.run(await f.plan()); assert.equal(first.verdict, 'PASS')
  await writeFile(join(f.root, 'binding.json'), JSON.stringify({ ...f.binding, inputs: { source: { tests: 0 } } }))
  const second = await f.run(await f.plan(), 'zero-case'); assert.equal(second.verdict, 'FAIL')
  assert.notEqual(first.runId, second.runId)
})

test('passed assertion with unknown mutation stops all later steps', async t => {
  let calls = 0
  const f = await fixture(t, { allowTargetMutations: true, adapters: { fixture: adapter('fixture', async () => {
    calls++; return proof(true, 'unknown')
  }, ['changesMetadata']) }, steps: [
    { id: 'load', adapter: 'local', operation: 'check', resources: ['db'], required: false },
    { id: 'later', adapter: 'local', operation: 'check', resources: ['alias'] },
  ] })
  const result = await f.run(await f.plan())
  assert.equal(result.verdict, 'INDETERMINATE'); assert.equal(calls, 1)
  assert.equal(result.steps[0].reason, 'MUTATION_STATE_UNCONFIRMED'); assert.equal(result.steps[1].status, 'blocked')
})

test('unconfirmed termination after optional timeout cannot pass or release resource', async t => {
  const f = await fixture(t, { adapters: { fixture: adapter('fixture', async () => {
    await new Promise(resolve => setTimeout(resolve, 150))
    return { ...proof(), data: { terminationConfirmed: false } }
  }) }, steps: [{ id: 'timeout', adapter: 'local', operation: 'check', resources: ['db'], timeoutMs: 100, required: false }] })
  const result = await f.run(await f.plan())
  assert.equal(result.verdict, 'INDETERMINATE'); assert.equal(result.retainedLocks, true)
  assert.equal((await readdir(join(f.stateDir, 'locks'))).length, 1)
})

test('string false cannot enable target mutations', async t => {
  const f = await fixture(t)
  assert.throws(() => new WorkflowHost({ ...f.options, allowTargetMutations: 'false' }), /HOST_CONFIGURATION_REQUIRED/u)
})
