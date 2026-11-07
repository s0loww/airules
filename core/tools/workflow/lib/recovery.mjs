import { randomUUID } from 'node:crypto'
import { lstat, mkdir, readFile, readdir, rename, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { canonical, digest, EFFECTS } from './contracts.mjs'
import { fail, hashBytes, projectPath, safeRead } from './snapshot.mjs'

const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u
const SHA = /^[a-f0-9]{64}$/u
const PROCESS_INSTANCE = randomUUID()
const active = new Set()
const plain = value => value && typeof value === 'object' && !Array.isArray(value)
const sealed = value => ({ ...value, receiptDigest: digest(value) })
function verify(value) {
  if (!plain(value)) fail('RECOVERY_RECEIPT_INVALID')
  const { receiptDigest, ...content } = value
  if (!SHA.test(receiptDigest ?? '') || digest(content) !== receiptDigest) fail('RECOVERY_RECEIPT_INVALID')
  return value
}
async function json(root, relative) {
  const path = await projectPath(root, relative)
  return JSON.parse((await safeRead(root, path, 1024 * 1024)).toString('utf8').replace(/^\uFEFF/u, ''))
}
async function save(path, value, exclusive = false) {
  const bytes = `${canonical(value)}\n`
  if (exclusive) return writeFile(path, bytes, { flag: 'wx', mode: 0o600 })
  const temporary = `${path}.${randomUUID()}.tmp`
  await writeFile(temporary, bytes, { flag: 'wx', mode: 0o600 }); await rename(temporary, path)
}
const exists = path => lstat(path).then(() => true, error => { if (error.code === 'ENOENT') return false; throw error })
function stopped(pid) {
  if (!Number.isSafeInteger(pid) || pid <= 0) return false
  try { process.kill(pid, 0); return false } catch (error) { return error.code === 'ESRCH' }
}

// A nonempty directory is atomically promoted. Reaping a dead owner first takes a
// nonce-specific guard and rechecks its identity, so a concurrent reaper never renames a new owner.
async function mutex(root, key) {
  if (active.has(key)) fail('RECOVERY_BUSY')
  active.add(key)
  const path = join(root, 'recovery-locks', digest(key)), owner = { pid: process.pid, instance: PROCESS_INSTANCE, nonce: randomUUID() }
  try {
    for (let attempt = 0; attempt < 3; attempt++) {
      const stage = `${path}.${owner.nonce}.stage`
      await mkdir(stage, { mode: 0o700 }); await save(join(stage, 'owner.json'), owner, true)
      try { await rename(stage, path); return async () => {
        const current = await json(root, `recovery-locks/${digest(key)}/owner.json`)
        if (digest(current) !== digest(owner)) fail('RECOVERY_LOCK_OWNERSHIP_LOST')
        await rm(path, { recursive: true }); active.delete(key)
      } } catch (error) {
        await rm(stage, { recursive: true, force: true })
        if (!['EEXIST', 'ENOTEMPTY', 'EPERM'].includes(error.code)) throw error
      }
      const current = await json(root, `recovery-locks/${digest(key)}/owner.json`)
      if (!stopped(current.pid)) fail('RECOVERY_OWNER_NOT_STOPPED')
      if (typeof current.nonce !== 'string' || !ID.test(current.nonce)) fail('RECOVERY_LOCK_INVALID')
      const guard = join(path, `reap-${current.nonce}`)
      try { await mkdir(guard) } catch { fail('RECOVERY_BUSY') }
      const checked = await json(root, `recovery-locks/${digest(key)}/owner.json`)
      if (digest(checked) !== digest(current)) { await rm(guard); fail('RECOVERY_BUSY') }
      const abandoned = `${path}.${current.nonce}.abandoned`
      await rename(path, abandoned)
      await rm(abandoned, { recursive: true })
    }
    fail('RECOVERY_BUSY')
  } catch (error) { active.delete(key); throw error }
}

async function originalPlan(host, report) {
  if (report.planId !== undefined && !ID.test(report.planId)) fail('RECOVERY_PLAN_REQUIRED')
  const names = report.planId ? [`${report.planId}.json`] : await readdir(join(host.stateDir, 'plans'))
  if (names.length > 10000) fail('RECOVERY_PLAN_LIMIT')
  for (const name of names) {
    if (!/^[A-Za-z0-9-]+\.json$/u.test(name)) continue
    const plan = await json(host.stateDir, `plans/${name}`)
    const { planDigest, ...content } = plan
    if (planDigest === report.planDigest && digest(content) === planDigest && plan.principal === report.principal
      && plan.projectId === report.projectId && plan.workflowId === report.workflowId) return plan
  }
  fail('RECOVERY_PLAN_REQUIRED')
}

function evidence(value, context, startedAfter) {
  const fields = ['schemaVersion', 'recoveryId', 'runId', 'targetId', 'planDigest', 'sourceDigest', 'targetFingerprint',
    'providerDigest', 'executorStopped', 'outcome', 'observedAt', 'artifact']
  if (!plain(value) || Object.keys(value).some(key => !fields.includes(key)) || value.schemaVersion !== 1
    || value.executorStopped !== true || !['not-applied', 'restored'].includes(value.outcome)
    || !Number.isSafeInteger(value.observedAt) || value.observedAt < startedAfter || value.observedAt > Date.now()) fail('RECOVERY_EVIDENCE_INVALID')
  for (const field of ['recoveryId', 'runId', 'targetId', 'planDigest', 'sourceDigest', 'targetFingerprint', 'providerDigest']) {
    if (value[field] !== context[field]) fail('RECOVERY_EVIDENCE_MISMATCH')
  }
  if (value.outcome === 'not-applied' && context.originalTarget.mutationState === 'applied') fail('RECOVERY_RESTORE_REQUIRED')
  const artifact = value.artifact
  if (!plain(artifact) || Object.keys(artifact).some(key => !['path', 'digest', 'bytes'].includes(key))
    || typeof artifact.path !== 'string' || !artifact.path || !SHA.test(artifact.digest ?? '')
    || !Number.isSafeInteger(artifact.bytes) || artifact.bytes < 1 || artifact.bytes > 1024 * 1024) fail('RECOVERY_ARTIFACT_REQUIRED')
  canonical(value)
}

export async function recover(host, { runId, targetId, providerId, requestId, principal }) {
  for (const id of [runId, targetId, providerId, requestId]) if (!ID.test(id ?? '')) fail('INVALID_ID')
  await host.init()
  const provider = host.recoveryProviders?.[providerId]
  if (!provider || typeof provider.fingerprint !== 'function' || typeof provider.reconcile !== 'function'
    || !Array.isArray(provider.effects) || provider.effects.some(effect => !EFFECTS.includes(effect))) fail('RECOVERY_PROVIDER_NOT_REGISTERED')
  await host.permit(principal, 'recover', { runId, targetId, providerId, effects: provider.effects })
  if (!host.allowTargetMutations && provider.effects.some(effect => ['writesTargetData', 'changesMetadata', 'serviceLifecycle', 'destructiveRecovery'].includes(effect))) fail('TARGET_MUTATIONS_DISABLED')
  if (host.active.has(runId)) fail('RECOVERY_EXECUTOR_ACTIVE')
  const release = await mutex(host.stateDir, `${host.stateDir}:${runId}`)
  let pending
  try {
    const report = await json(host.stateDir, `runs/${runId}/result.json`)
    if (report.principal !== principal) fail('NOT_AUTHORIZED')
    const target = report.targets.find(item => item.id === targetId)
    if (!target?.mutationRequested) fail('RECOVERY_TARGET_NOT_FOUND')
    const plan = await originalPlan(host, report)
    const requestKey = digest({ principal, requestId })
    const requestPath = join(host.stateDir, 'recoveries', `${requestKey}.json`)
    const association = { runId, targetId, providerId, principal, requestId }
    const recoveryEngineDigest = hashBytes(await readFile(new URL(import.meta.url)))
    let receipt
    if (await exists(requestPath)) {
      receipt = verify(await json(host.stateDir, `recoveries/${requestKey}.json`))
      if (Object.entries(association).some(([key, value]) => receipt[key] !== value)) fail('RECOVERY_REQUEST_CONFLICT')
    } else {
      receipt = sealed({ schemaVersion: 1, ...association, recoveryEngineDigest, recoveryId: randomUUID(), phase: 'pending', requestedAt: Date.now() })
      await save(requestPath, receipt, true)
    }
    const resourceName = digest(targetId), lockPath = join(host.stateDir, 'locks', resourceName)
    const quarantine = `${lockPath}.recovered-${receipt.recoveryId}`
    const verifyOwner = async relative => {
      const holder = await json(host.stateDir, relative)
      if (holder.runId !== runId || holder.principal !== principal || holder.resourceId !== targetId) fail('RECOVERY_TARGET_LOCK_NOT_OWNED')
    }
    const indexCompleted = async () => {
      const indexDir = join(host.stateDir, 'runs', runId, 'recoveries')
      await mkdir(indexDir, { recursive: true, mode: 0o700 })
      await projectPath(host.stateDir, `runs/${runId}/recoveries`)
      await save(join(indexDir, `${resourceName}.json`), receipt)
      if (await exists(quarantine)) {
        await verifyOwner(`locks/${resourceName}.recovered-${receipt.recoveryId}/owner.json`)
        await rm(quarantine, { recursive: true })
      }
    }
    if (receipt.phase === 'completed') { await indexCompleted(); return receipt }
    if (receipt.phase === 'pending') {
      await verifyOwner(`locks/${resourceName}/owner.json`)
      const providerDigest = await provider.fingerprint()
      if (!SHA.test(providerDigest ?? '')) fail('RECOVERY_PROVIDER_FINGERPRINT_INVALID')
      if (receipt.providerDigest !== undefined && receipt.providerDigest !== providerDigest) fail('RECOVERY_PROVIDER_CHANGED')
      if (receipt.providerDigest === undefined) {
        const { receiptDigest: _old, ...content } = receipt
        receipt = sealed({ ...content, providerDigest }); await save(requestPath, receipt)
      }
      const binding = plan.inputs.steps.filter(step => step.resources?.some(resource => resource.id === targetId))
        .map(step => ({ id: step.id, adapterId: step.adapterId, adapterDigest: step.adapterDigest }))
      const context = { schemaVersion: 1, recoveryId: receipt.recoveryId, runId, targetId, planDigest: report.planDigest,
        sourceDigest: plan.inputs.source.digest, targetFingerprint: digest({ id: targetId, environment: target.environment, binding }),
        providerDigest, originalTarget: structuredClone(target), originalResult: structuredClone(report),
        artifactDir: join(host.stateDir, 'recoveries', 'artifacts', receipt.recoveryId) }
      await mkdir(context.artifactDir, { recursive: true, mode: 0o700 })
      await projectPath(host.stateDir, `recoveries/artifacts/${receipt.recoveryId}`)
      const startedAfter = Date.now(), controller = new AbortController()
      context.signal = controller.signal
      const timeoutMs = provider.timeoutMs ?? 60000
      if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 100 || timeoutMs > 3600000) fail('RECOVERY_TIMEOUT_INVALID')
      context.timeoutMs = timeoutMs; context.deadline = Date.now() + timeoutMs
      let timeout
      const execution = Promise.resolve().then(() => provider.reconcile(Object.freeze(context)))
        .finally(() => { pending = null })
      pending = execution
      const timedOut = new Promise((_, reject) => { timeout = setTimeout(() => { controller.abort(); reject(Object.assign(new Error('RECOVERY_TIMEOUT'), { code: 'RECOVERY_TIMEOUT' })) }, timeoutMs) })
      let value
      try { value = await Promise.race([execution, timedOut]); pending = null } finally { clearTimeout(timeout) }
      evidence(value, context, startedAfter)
      const bytes = await safeRead(context.artifactDir, await projectPath(context.artifactDir, value.artifact.path), 1024 * 1024)
      if (bytes.length !== value.artifact.bytes || hashBytes(bytes) !== value.artifact.digest) fail('RECOVERY_ARTIFACT_MISMATCH')
      if (await provider.fingerprint() !== providerDigest) fail('RECOVERY_PROVIDER_CHANGED')
      if (host.active.has(runId) || digest(await json(host.stateDir, `runs/${runId}/result.json`)) !== digest(report)) fail('RECOVERY_RUN_CHANGED')
      await verifyOwner(`locks/${resourceName}/owner.json`)
      receipt = sealed({ ...association, schemaVersion: 1, recoveryId: receipt.recoveryId, requestedAt: receipt.requestedAt,
        recoveryEngineDigest, phase: 'evidence-confirmed', evidence: value, evidenceDigest: digest(value), preparedAt: Date.now() })
      await save(requestPath, receipt)
    }
    if (receipt.phase !== 'evidence-confirmed') fail('RECOVERY_RECEIPT_INVALID')
    const artifactDir = join(host.stateDir, 'recoveries', 'artifacts', receipt.recoveryId)
    const artifactPath = await projectPath(artifactDir, receipt.evidence.artifact.path)
    if ((await lstat(artifactPath)).nlink !== 1) fail('RECOVERY_ARTIFACT_MISMATCH')
    const proof = await safeRead(artifactDir, artifactPath, 1024 * 1024)
    if (proof.length !== receipt.evidence.artifact.bytes || hashBytes(proof) !== receipt.evidence.artifact.digest) fail('RECOVERY_ARTIFACT_MISMATCH')
    // Prepared proof is durable before ownership is released. A restart finalizes
    // this exact receipt from its private tombstone, never repeats restore.
    if (!await exists(quarantine)) {
      await verifyOwner(`locks/${resourceName}/owner.json`)
      await rename(lockPath, quarantine)
    }
    await verifyOwner(`locks/${resourceName}.recovered-${receipt.recoveryId}/owner.json`)
    receipt = sealed({ ...Object.fromEntries(Object.entries(receipt).filter(([key]) => key !== 'receiptDigest')),
      phase: 'completed', completedAt: Date.now() })
    await save(requestPath, receipt)
    // The target index is an independently sealed receipt; original execution journal is unchanged.
    await indexCompleted()
    return receipt
  } finally {
    if (pending) pending.catch(() => {}).finally(() => release().catch(() => {}))
    else await release()
  }
}

export async function recoveryResult(host, report) {
  let names
  try { names = await readdir(join(host.stateDir, 'runs', report.runId, 'recoveries')) } catch (error) { if (error.code === 'ENOENT') return report; throw error }
  if (names.length > 1024) fail('RECOVERY_RECEIPT_LIMIT')
  const receipts = []
  for (const name of names) {
    if (!/^[a-f0-9]{64}\.json$/u.test(name)) fail('RECOVERY_RECEIPT_INVALID')
    const receipt = verify(await json(host.stateDir, `runs/${report.runId}/recoveries/${name}`))
    if (receipt.runId !== report.runId || receipt.principal !== report.principal || receipt.phase !== 'completed') fail('RECOVERY_RECEIPT_INVALID')
    receipts.push({ recoveryId: receipt.recoveryId, targetId: receipt.targetId, outcome: receipt.evidence.outcome,
      completedAt: receipt.completedAt, receiptDigest: receipt.receiptDigest })
  }
  const targets = report.targets.map(target => receipts.some(receipt => receipt.targetId === target.id)
    ? { ...target, recoveryState: 'completed' } : target)
  const required = targets.filter(target => target.recoveryState === 'required')
  return { ...report, targets, verdict: report.verdict === 'RUNNING' ? 'INDETERMINATE' : report.verdict,
    recoveryState: required.length ? 'required' : 'completed',
    retainedLocks: required.length > 0 && report.retainedLocks === true, recoveries: receipts,
    originalVerdict: report.verdict, observation: !report.finishedAt ? 'reconciled' : report.observation ?? 'recovery-completed' }
}
