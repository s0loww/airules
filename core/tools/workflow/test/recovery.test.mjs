import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, writeFile, rm, readdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { WorkflowHost } from '../index.mjs'
import { digest } from '../lib/contracts.mjs'
import { hashBytes } from '../lib/snapshot.mjs'

const principal = 'operator', targetId = 'fixture-target'
const proof = { complete: true, assertions: [{ id: 'fixture', passed: true }] }
async function fixture(t, { outcome = 'not-applied', authorize = async () => true, evidencePatch = value => value,
  reconciliation, appliedFailure = false } = {}) {
  const temporary = await mkdtemp(join(tmpdir(), 'workflow-recovery-'))
  t.after(() => rm(temporary, { recursive: true, force: true }))
  const root = join(temporary, 'project'), stateDir = join(temporary, 'state')
  await mkdir(join(root, 'src'), { recursive: true }); await writeFile(join(root, 'src/input.txt'), 'fixture')
  await writeFile(join(root, 'binding.json'), JSON.stringify({ schemaVersion: 1, projectId: 'fixture', providers: { deploy: { adapterId: 'stub' } } }))
  let success = false, calls = 0, providerHash = digest('reviewed-fixture-provider')
  const adapter = { descriptor: { protocolVersion: 1, id: 'stub', version: '1', operations: { apply: {
    inputSchema: { type: 'object', additionalProperties: false }, resultSchema: { type: 'object', additionalProperties: true },
    effects: ['changesMetadata'], validator: 'assertions', resourcesRequired: true,
  } } }, fingerprint: async () => digest('fixed-fixture-runner'), execute: async () => {
    if (success) return { data: proof, mutationState: 'applied' }
    if (appliedFailure) return { data: { ...proof, assertions: [{ id: 'fixture', passed: false }] }, mutationState: 'applied' }
    throw new Error('FIXTURE_UNCERTAIN')
  } }
  const provider = { effects: ['connectsTarget', 'writesFilesystem', 'destructiveRecovery'], fingerprint: async () => providerHash,
    async reconcile(context) {
      calls++
      if (reconciliation) await reconciliation(context)
      const bytes = Buffer.from(JSON.stringify({ verifiedFixtureState: outcome, targetId: context.targetId,
        targetFingerprint: context.targetFingerprint, sourceDigest: context.sourceDigest, runId: context.runId }))
      await writeFile(join(context.artifactDir, 'proof.json'), bytes)
      const value = { schemaVersion: 1, recoveryId: context.recoveryId, runId: context.runId, targetId: context.targetId,
        planDigest: context.planDigest, sourceDigest: context.sourceDigest, targetFingerprint: context.targetFingerprint,
        providerDigest: context.providerDigest, executorStopped: true, outcome, observedAt: Date.now(),
        artifact: { path: 'proof.json', digest: hashBytes(bytes), bytes: bytes.length } }
      return evidencePatch(value, context)
    } }
  const options = { stateDir, projects: { fixture: { root, bindingPath: 'binding.json', sourcePaths: ['src'], configPaths: [],
    resources: { target: { id: targetId, environment: 'test' } } } },
    workflows: { deploy: { schemaVersion: 1, id: 'deploy', version: '1', steps: [{ id: 'apply', adapter: 'deploy', operation: 'apply', resources: ['target'] }] } },
    adapters: { stub: adapter }, recoveryProviders: { reviewed: provider }, allowTargetMutations: true, authorize }
  const host = new WorkflowHost(options)
  const plan = await host.plan({ projectId: 'fixture', workflowId: 'deploy', principal })
  const result = await host.run({ planId: plan.id, planDigest: plan.planDigest, requestId: 'run', principal })
  const args = { runId: result.runId, targetId, providerId: 'reviewed', requestId: 'recover', principal }
  return { host, options, plan, result, args, stateDir, provider, root,
    calls: () => calls, success: () => { success = true }, setProviderHash: value => { providerHash = value } }
}

test('recovery verifies typed proof, preserves execution journal and releases only the owned lock', async t => {
  const f = await fixture(t), path = join(f.stateDir, 'runs', f.result.runId, 'result.json')
  const before = await readFile(path, 'utf8')
  assert.equal(f.result.retainedLocks, true)
  const receipt = await f.host.recover(f.args)
  assert.equal(receipt.phase, 'completed'); assert.equal(receipt.evidence.outcome, 'not-applied')
  assert.equal(await readFile(path, 'utf8'), before)
  const result = await f.host.result({ runId: f.result.runId, principal })
  assert.equal(result.verdict, 'INDETERMINATE'); assert.equal(result.mutationState, 'unknown')
  assert.equal(result.recoveryState, 'completed'); assert.equal(result.targets[0].recoveryState, 'completed')
  assert.equal(result.retainedLocks, false); assert.equal(result.recoveries.length, 1)
  assert.deepEqual(await readdir(join(f.stateDir, 'locks')), [])
  assert.equal((await f.host.recover(f.args)).recoveryId, receipt.recoveryId); assert.equal(f.calls(), 1)
  f.success()
  const plan = await f.host.plan({ projectId: 'fixture', workflowId: 'deploy', principal })
  assert.equal((await f.host.run({ planId: plan.id, planDigest: plan.planDigest, requestId: 'retry-after-proof', principal })).verdict, 'PASS')
})

test('known applied failure retains its target and requires a restored proof, not a not-applied assertion', async t => {
  const rejected = await fixture(t, { appliedFailure: true })
  assert.equal(rejected.result.retainedLocks, true)
  await assert.rejects(rejected.host.recover(rejected.args), /RECOVERY_RESTORE_REQUIRED/u)
  const f = await fixture(t, { appliedFailure: true, outcome: 'restored' })
  assert.equal((await f.host.recover(f.args)).evidence.outcome, 'restored')
  assert.equal((await f.host.result({ runId: f.result.runId, principal })).recoveryState, 'completed')
})

test('missing stop proof, mismatched identity, stale observation and corrupt artifact never release target', async t => {
  const patches = [value => ({ ...value, executorStopped: false }), value => ({ ...value, runId: randomUUID() }),
    value => ({ ...value, sourceDigest: 'a'.repeat(64) }), value => ({ ...value, observedAt: 1 }),
    value => ({ ...value, artifact: { ...value.artifact, digest: 'b'.repeat(64) } }),
    value => ({ ...value, artifact: { ...value.artifact, path: '../outside.json' } })]
  for (const evidencePatch of patches) {
    const f = await fixture(t, { evidencePatch })
    await assert.rejects(f.host.recover(f.args))
    assert.equal((await readdir(join(f.stateDir, 'locks'))).length, 1)
    assert.equal((await f.host.result({ runId: f.result.runId, principal })).recoveryState, 'required')
  }
})

test('recovery independently checks action authorization and execution ownership', async t => {
  const f = await fixture(t)
  await assert.rejects(f.host.recover({ ...f.args, principal: 'other' }), /NOT_AUTHORIZED/u)
  assert.equal(f.calls(), 0)
  const denied = await fixture(t, { authorize: async request => request.action !== 'recover' })
  await assert.rejects(denied.host.recover(denied.args), /NOT_AUTHORIZED/u)
  assert.equal(denied.calls(), 0)
  await assert.rejects(f.host.recover({ ...f.args, providerId: 'project-untrusted' }), /RECOVERY_PROVIDER_NOT_REGISTERED/u)
})

test('active executor and foreign lock ownership prevent reconciliation before any provider call', async t => {
  const f = await fixture(t)
  f.host.active.set(f.result.runId, {})
  await assert.rejects(f.host.recover(f.args), /RECOVERY_EXECUTOR_ACTIVE/u)
  f.host.active.delete(f.result.runId)
  await writeFile(join(f.stateDir, 'locks', digest(targetId), 'owner.json'), JSON.stringify({ runId: randomUUID(), principal, resourceId: targetId }))
  await assert.rejects(f.host.recover(f.args), /RECOVERY_TARGET_LOCK_NOT_OWNED/u)
  assert.equal(f.calls(), 0)
})

test('orphaned execution requires provider stop proof and retains immutable original journal', async t => {
  const f = await fixture(t, { outcome: 'restored' }), path = join(f.stateDir, 'runs', f.result.runId, 'result.json')
  const original = JSON.parse(await readFile(path, 'utf8')); original.finishedAt = null; original.verdict = 'RUNNING'
  await writeFile(path, JSON.stringify(original))
  const restarted = new WorkflowHost(f.options)
  assert.equal((await restarted.result({ runId: f.result.runId, principal })).observation, 'owner-not-attached')
  await restarted.recover(f.args)
  assert.deepEqual(JSON.parse(await readFile(path, 'utf8')), original)
  const recovered = await restarted.result({ runId: f.result.runId, principal })
  assert.equal(recovered.observation, 'reconciled')
  assert.equal(recovered.verdict, 'INDETERMINATE'); assert.equal(recovered.originalVerdict, 'RUNNING')
})

test('provider code drift invalidates evidence and a pending request cannot switch reviewed provider code', async t => {
  let f
  f = await fixture(t, { reconciliation: async () => { f.setProviderHash(digest('changed code')) } })
  await assert.rejects(f.host.recover(f.args), /RECOVERY_PROVIDER_CHANGED/u)
  await assert.rejects(f.host.recover(f.args), /RECOVERY_PROVIDER_CHANGED/u)
  assert.equal(f.calls(), 1)
  assert.equal((await readdir(join(f.stateDir, 'locks'))).length, 1)
})

test('concurrent recovery requests serialize the target and call a trusted provider only once', async t => {
  let enter, finish
  const entered = new Promise(resolve => { enter = resolve }), pending = new Promise(resolve => { finish = resolve })
  const f = await fixture(t, { reconciliation: async () => { enter(); await pending } })
  const first = f.host.recover(f.args)
  await entered
  await assert.rejects(new WorkflowHost(f.options).recover({ ...f.args, requestId: 'other-request' }), /RECOVERY_BUSY/u)
  finish(); await first
  assert.equal(f.calls(), 1)
})

test('timeout keeps reconciliation ownership until the provider has actually stopped', async t => {
  let finish
  const pending = new Promise(resolve => { finish = resolve })
  const f = await fixture(t, { reconciliation: async context => { assert.equal(context.timeoutMs, 100); assert.ok(context.deadline > 0); await pending } })
  f.provider.timeoutMs = 100
  await assert.rejects(f.host.recover(f.args), /RECOVERY_TIMEOUT/u)
  await assert.rejects(new WorkflowHost(f.options).recover({ ...f.args, requestId: 'retry-active' }), /RECOVERY_BUSY/u)
  finish(); await new Promise(resolve => setTimeout(resolve, 20))
  assert.equal((await readdir(join(f.stateDir, 'locks'))).length, 1)
})

test('prepared release resumes from its tombstone without re-running restore or touching a newer owner', async t => {
  const f = await fixture(t, { outcome: 'restored' }), receipt = await f.host.recover(f.args)
  const resourceName = digest(targetId), quarantine = join(f.stateDir, 'locks', `${resourceName}.recovered-${receipt.recoveryId}`)
  await mkdir(quarantine)
  await writeFile(join(quarantine, 'owner.json'), JSON.stringify({ runId: f.result.runId, principal, resourceId: targetId }))
  await mkdir(join(f.stateDir, 'locks', resourceName))
  const newOwner = { runId: randomUUID(), principal: 'new-owner', resourceId: targetId }
  await writeFile(join(f.stateDir, 'locks', resourceName, 'owner.json'), JSON.stringify(newOwner))
  const { receiptDigest, completedAt, ...prepared } = receipt
  prepared.phase = 'evidence-confirmed'
  await writeFile(join(f.stateDir, 'recoveries', `${digest({ principal, requestId: 'recover' })}.json`), JSON.stringify({ ...prepared, receiptDigest: digest(prepared) }))
  await rm(join(f.stateDir, 'runs', f.result.runId, 'recoveries', `${resourceName}.json`))
  await new WorkflowHost(f.options).recover(f.args)
  assert.equal(f.calls(), 1)
  assert.deepEqual(JSON.parse(await readFile(join(f.stateDir, 'locks', resourceName, 'owner.json'), 'utf8')), newOwner)
  assert.equal((await f.host.result({ runId: f.result.runId, principal })).recoveryState, 'completed')
})
