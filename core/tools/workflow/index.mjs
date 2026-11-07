import { randomUUID } from 'node:crypto'
import { lstat, mkdir, readFile, realpath, rename, rm, writeFile } from 'node:fs/promises'
import { isAbsolute, join, resolve } from 'node:path'
import { canonical, digest, validateDescriptor, validateSchema, validateWorkflow } from './lib/contracts.mjs'
import { validateEvidence } from './lib/validators.mjs'
import { fail, hashBytes, projectPath, safeRead, snapshot } from './lib/snapshot.mjs'
import { recover, recoveryResult } from './lib/recovery.mjs'

const ID = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/u
const TARGET_EFFECTS = new Set(['writesTargetData', 'changesMetadata', 'serviceLifecycle', 'destructiveRecovery'])
const BUILTIN_VALIDATORS = new Set(['process-exit', 'assertions', 'test-summary'])
const clone = value => JSON.parse(canonical(value))
const checkId = value => { if (typeof value !== 'string' || !ID.test(value)) fail('INVALID_ID'); return value }
const safeReason = value => typeof value === 'string' && /^[A-Z][A-Z0-9_:-]{0,95}$/u.test(value) ? value : 'EVIDENCE_REJECTED'
const mutation = effects => effects.some(effect => TARGET_EFFECTS.has(effect))
const mergeMutation = (prior, current) => prior === 'unknown' || current === 'unknown' ? 'unknown'
  : prior === 'applied' || current === 'applied' ? 'applied' : 'not-applied'
function rejectSecrets(value) {
  if (!value || typeof value !== 'object') return
  for (const [key, entry] of Object.entries(value)) {
    if (/^(?:password|passwd|secret|apiKey|accessToken|refreshToken|authorization|credentialValue)$/iu.test(key)) fail('INLINE_SECRET_FORBIDDEN')
    rejectSecrets(entry)
  }
}

async function executeBounded(adapter, step, context) {
  const controller = new AbortController()
  let timer, grace, rejectStop, timedOut = false
  let settled = false
  const stopped = new Promise((_, reject) => { rejectStop = reject })
  const abort = () => {
    controller.abort()
    if (!grace) grace = setTimeout(() => { if (!settled) rejectStop(Object.assign(new Error('EXECUTOR_STOP_UNCONFIRMED'), { code: 'EXECUTOR_STOP_UNCONFIRMED' })) }, 12000)
  }
  context.signal.addEventListener('abort', abort, { once: true })
  if (context.signal.aborted) abort()
  const execution = Promise.resolve().then(() => {
    if (controller.signal.aborted) fail('CANCELLED_BEFORE_EXECUTION')
    return adapter.execute(step.operation, clone(step.inputs), { ...context, signal: controller.signal })
  }).finally(() => { settled = true })
  timer = setTimeout(() => { timedOut = true; abort() }, step.timeoutMs)
  try {
    const output = await Promise.race([execution, stopped])
    if (output?.data?.terminationConfirmed === false) fail('EXECUTOR_STOP_UNCONFIRMED')
    if (timedOut) fail('STEP_TIMEOUT')
    return output
  }
  finally { clearTimeout(timer); clearTimeout(grace); context.signal.removeEventListener('abort', abort) }
}

async function json(path) {
  if (!(await lstat(path)).isFile() || (await lstat(path)).isSymbolicLink()) fail('UNSAFE_STATE_FILE')
  return JSON.parse((await readFile(path, 'utf8')).replace(/^\uFEFF/u, ''))
}
async function save(path, value, exclusive = false) {
  const text = `${canonical(value)}\n`
  if (exclusive) return writeFile(path, text, { flag: 'wx', mode: 0o600 })
  const temporary = `${path}.${randomUUID()}.tmp`
  await writeFile(temporary, text, { flag: 'wx', mode: 0o600 })
  await rename(temporary, path)
}

/** Trusted host API. Registry and principal must come from the embedding client, not model input. */
export class WorkflowHost {
  constructor({ stateDir, projects = {}, workflows = {}, adapters = {}, authorize, validators = {}, recoveryProviders = {}, allowTargetMutations = false }) {
    if (typeof stateDir !== 'string' || !isAbsolute(stateDir) || typeof authorize !== 'function'
      || typeof allowTargetMutations !== 'boolean') fail('HOST_CONFIGURATION_REQUIRED')
    this.stateDir = resolve(stateDir)
    this.projects = clone(projects)
    this.workflows = clone(workflows)
    this.adapters = adapters
    this.authorize = authorize
    this.validators = validators
    this.recoveryProviders = recoveryProviders
    this.allowTargetMutations = allowTargetMutations
    this.active = new Map()
  }

  async init() {
    await mkdir(this.stateDir, { recursive: true, mode: 0o700 })
    if ((await lstat(this.stateDir)).isSymbolicLink()) fail('UNSAFE_STATE_ROOT')
    this.stateDir = await realpath(this.stateDir)
    for (const name of ['plans', 'runs', 'requests', 'locks', 'recoveries', 'recovery-locks']) {
      const path = join(this.stateDir, name)
      await mkdir(path, { recursive: true, mode: 0o700 })
      if ((await lstat(path)).isSymbolicLink()) fail('UNSAFE_STATE_ROOT')
    }
  }

  async permit(principal, action, details = {}) {
    checkId(principal)
    if (await this.authorize({ principal, action, ...details }) !== true) fail('NOT_AUTHORIZED')
  }

  async inputs(projectId, workflowId) {
    checkId(projectId); checkId(workflowId)
    const project = this.projects[projectId]
    if (!project || !this.workflows[workflowId]) fail('NOT_REGISTERED')
    const root = await realpath(project.root)
    const bindingPath = await projectPath(root, project.bindingPath)
    const bindingBytes = await safeRead(root, bindingPath, 1024 * 1024)
    const binding = JSON.parse(bindingBytes.toString('utf8').replace(/^\uFEFF/u, ''))
    canonical(binding); rejectSecrets(binding)
    if (binding.schemaVersion !== 1 || binding.projectId !== projectId || !binding.providers || typeof binding.providers !== 'object') fail('INVALID_BINDING')
    const workflow = validateWorkflow(this.workflows[workflowId])
    if (workflow.id !== workflowId) fail('WORKFLOW_ID_MISMATCH')
    const source = await snapshot(root, project.sourcePaths ?? [], this.stateDir)
    const config = await snapshot(root, project.configPaths ?? [], this.stateDir)
    const steps = []
    for (const step of workflow.steps) {
      const provider = binding.providers[step.adapter]
      if (!provider || typeof provider.adapterId !== 'string') {
        if (step.required) fail('PROVIDER_NOT_CONFIGURED')
        steps.push({ ...step, configured: false }); continue
      }
      const adapter = this.adapters[provider.adapterId]
      if (!adapter || typeof adapter.execute !== 'function' || typeof adapter.fingerprint !== 'function') fail('ADAPTER_NOT_REGISTERED')
      const descriptor = validateDescriptor(adapter.descriptor)
      if (descriptor.id !== provider.adapterId) fail('ADAPTER_ID_MISMATCH')
      const operation = descriptor.operations[step.operation]
      if (!operation) fail('OPERATION_UNSUPPORTED')
      if (!BUILTIN_VALIDATORS.has(operation.validator) && typeof this.validators[operation.validator] !== 'function') fail('VALIDATOR_NOT_REGISTERED')
      if (mutation(operation.effects) && operation.validator === 'process-exit') fail('MUTATION_REQUIRES_POSTCONDITION')
      const values = binding.inputs?.[step.id] ?? step.inputs
      validateSchema(operation.inputSchema, values)
      const resources = step.resources.map(ref => {
        const resource = project.resources?.[ref]
        if (!resource || !ID.test(resource.id)) fail('RESOURCE_NOT_REGISTERED')
        return { ref, id: resource.id, environment: resource.environment ?? null }
      })
      if ((operation.resourcesRequired || mutation(operation.effects)) && !resources.length) fail('RESOURCE_REQUIRED')
      if (mutation(operation.effects) && resources.some(resource => !['test', 'development', 'production'].includes(resource.environment))) fail('UNKNOWN_ENVIRONMENT')
      const fingerprint = await adapter.fingerprint()
      if (typeof fingerprint !== 'string' || !/^[a-f0-9]{64}$/u.test(fingerprint)) fail('INVALID_ADAPTER_FINGERPRINT')
      steps.push({ ...step, inputs: clone(values), configured: true, adapterId: descriptor.id,
        adapterVersion: descriptor.version, adapterDigest: fingerprint, descriptorDigest: digest(descriptor),
        effects: operation.effects, validator: operation.validator, resources })
    }
    const kernelFiles = ['index.mjs', 'lib/contracts.mjs', 'lib/snapshot.mjs', 'lib/validators.mjs', 'lib/recovery.mjs']
    const kernel = await Promise.all(kernelFiles.map(async path => [path, hashBytes(await readFile(new URL(path, import.meta.url)))]))
    const validatorCode = Object.entries(this.validators).map(([id, implementation]) => [id, implementation.toString()]).sort(([a], [b]) => a.localeCompare(b))
    return { root, engineDigest: digest({ kernel, validatorCode, node: process.versions.node, platform: process.platform }),
      projectDigest: digest(project), bindingDigest: hashBytes(bindingBytes), workflowDigest: digest(workflow), source, config, steps }
  }

  async capabilities({ projectId, workflowId, principal }) {
    await this.permit(principal, 'capabilities', { projectId, workflowId })
    checkId(projectId); checkId(workflowId)
    const project = this.projects[projectId]
    if (!project || !this.workflows[workflowId]) fail('NOT_REGISTERED')
    const root = await realpath(project.root)
    const bytes = await safeRead(root, await projectPath(root, project.bindingPath), 1024 * 1024)
    const binding = JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/u, ''))
    canonical(binding); rejectSecrets(binding)
    if (binding.schemaVersion !== 1 || binding.projectId !== projectId) fail('INVALID_BINDING')
    const workflow = validateWorkflow(this.workflows[workflowId])
    return { schemaVersion: 1, projectId, workflowId, targetMutationsEnabled: this.allowTargetMutations,
      steps: workflow.steps.map(step => {
        const id = binding.providers?.[step.adapter]?.adapterId
        const adapter = id && this.adapters[id]
        let status = id ? 'unavailable' : 'not-configured'
        if (adapter) status = validateDescriptor(adapter.descriptor).operations[step.operation] ? 'configured' : 'unsupported'
        return { id: step.id, required: step.required, providerRef: step.adapter, status, availability: 'not-probed' }
      }) }
  }

  async plan({ projectId, workflowId, principal, ttlMs = 300000 }) {
    await this.init()
    await this.permit(principal, 'plan', { projectId, workflowId })
    if (!Number.isInteger(ttlMs) || ttlMs < 100 || ttlMs > 3600000) fail('INVALID_TTL')
    const inputs = await this.inputs(projectId, workflowId)
    const plan = { schemaVersion: 1, id: randomUUID(), principal, projectId, workflowId,
      createdAt: Date.now(), expiresAt: Date.now() + ttlMs, inputs }
    const sealed = { ...plan, planDigest: digest(plan) }
    await save(join(this.stateDir, 'plans', `${plan.id}.json`), sealed, true)
    // Do not expose trusted raw inputs: they may contain project-specific content.
    return { id: sealed.id, planDigest: sealed.planDigest, projectId, workflowId, expiresAt: sealed.expiresAt,
      source: inputs.source, steps: inputs.steps.map(({ id, operation, configured, effects, resources, required }) =>
        ({ id, operation, configured, effects: effects ?? [], resources: resources ?? [], required })) }
  }

  async loadPlan(planId, principal, planDigest) {
    checkId(planId)
    const plan = await json(join(this.stateDir, 'plans', `${planId}.json`))
    if (plan.principal !== principal) fail('NOT_AUTHORIZED')
    const { planDigest: storedDigest, ...content } = plan
    if (storedDigest !== planDigest || digest(content) !== storedDigest) fail('PLAN_MISMATCH')
    return plan
  }

  async run({ planId, planDigest, principal, requestId }) {
    await this.init(); checkId(requestId)
    await this.permit(principal, 'run', { planId })
    const plan = await this.loadPlan(planId, principal, planDigest)
    const requestKey = digest({ principal, requestId, projectId: plan.projectId })
    const requestPath = join(this.stateDir, 'requests', requestKey)
    try { await mkdir(requestPath, { mode: 0o700 }) }
    catch (error) {
      if (error.code !== 'EEXIST') throw error
      let prior
      try { prior = await json(join(requestPath, 'receipt.json')) } catch { fail('REQUEST_INDETERMINATE') }
      if (prior.planDigest !== planDigest) fail('REQUEST_CONFLICT')
      return this.result({ runId: prior.runId, principal })
    }
    const runId = randomUUID()
    const runDir = join(this.stateDir, 'runs', runId)
    await mkdir(runDir, { mode: 0o700 })
    const report = { schemaVersion: 1, runId, planId, principal, projectId: plan.projectId, workflowId: plan.workflowId,
      planDigest, startedAt: Date.now(), finishedAt: null, verdict: 'RUNNING', mutationState: 'not-applied',
      recoveryState: 'not-required', reason: null, steps: [], targets: [] }
    const reportPath = join(runDir, 'result.json')
    await save(reportPath, report)
    await save(join(requestPath, 'receipt.json'), { runId, planDigest }, true)
    try { await save(join(this.stateDir, 'plans', `${planId}.run.json`), { runId, planDigest }, true) }
    catch (error) {
      if (error.code !== 'EEXIST') throw error
      const accepted = await json(join(this.stateDir, 'plans', `${planId}.run.json`))
      if (accepted.planDigest !== planDigest) fail('PLAN_MISMATCH')
      report.verdict = 'BLOCKED'; report.reason = 'PLAN_ALREADY_ACCEPTED'; report.finishedAt = Date.now()
      await save(reportPath, report)
      await save(join(requestPath, 'receipt.json'), accepted)
      return this.result({ runId: accepted.runId, principal })
    }
    const controller = new AbortController()
    const active = { controller, principal, report, reportPath }
    this.active.set(runId, active)
    const locks = []
    let retainLocks = false
    const verifyLocks = async () => {
      for (const lock of locks) {
        const holder = await json(join(lock, 'owner.json'))
        if (holder.runId !== runId || holder.principal !== principal) fail('LOCK_OWNERSHIP_LOST')
      }
    }
    const updateMutation = () => {
      const states = report.targets.filter(target => target.mutationRequested).map(target => target.mutationState)
      report.mutationState = states.includes('unknown') ? 'unknown' : states.includes('applied')
        ? states.includes('not-applied') ? 'partial' : 'applied' : 'not-applied'
    }
    try {
      if (Date.now() >= plan.expiresAt) fail('PLAN_EXPIRED')
      const effects = [...new Set(plan.inputs.steps.flatMap(step => step.effects ?? []))]
      if (!this.allowTargetMutations && mutation(effects)) fail('TARGET_MUTATIONS_DISABLED')
      await this.permit(principal, 'execute', { projectId: plan.projectId, planDigest, effects,
        resources: plan.inputs.steps.flatMap(step => step.resources ?? []) })
      if (digest(await this.inputs(plan.projectId, plan.workflowId)) !== digest(plan.inputs)) fail('STALE_PLAN')
      const resources = new Map()
      const mutationResources = new Set()
      for (const step of plan.inputs.steps) for (const resource of step.resources ?? []) {
        if (resources.has(resource.id) && resources.get(resource.id).environment !== resource.environment) fail('RESOURCE_IDENTITY_CONFLICT')
        resources.set(resource.id, resource)
        if (mutation(step.effects ?? [])) mutationResources.add(resource.id)
      }
      for (const resource of [...resources.values()].sort((a, b) => a.id.localeCompare(b.id))) {
        const lockDir = join(this.stateDir, 'locks', digest(resource.id))
        try { await mkdir(lockDir, { mode: 0o700 }) } catch (error) { if (error.code === 'EEXIST') fail('RESOURCE_BUSY'); throw error }
        locks.push(lockDir)
        await save(join(lockDir, 'owner.json'), { runId, principal, resourceId: resource.id }, true)
        report.targets.push({ id: resource.id, environment: resource.environment ?? null,
          mutationRequested: mutationResources.has(resource.id), mutationState: 'not-applied', recoveryState: 'not-required', stages: [] })
      }
      // Close the preflight/lock race before invoking any adapter.
      if (digest(await this.inputs(plan.projectId, plan.workflowId)) !== digest(plan.inputs)) fail('STALE_PLAN')
      for (const step of plan.inputs.steps) {
        const row = { id: step.id, required: step.required, status: 'pending', reason: null,
          effects: step.effects ?? [], startedAt: null, finishedAt: null, evidence: null }
        report.steps.push(row)
        const dependencyFailed = step.dependsOn.some(id => report.steps.find(item => item.id === id)?.status !== 'passed')
        if (!step.configured || dependencyFailed || controller.signal.aborted) {
          row.status = controller.signal.aborted ? 'interrupted' : dependencyFailed ? 'blocked' : 'skipped'
          row.reason = controller.signal.aborted ? 'CANCELLED' : dependencyFailed ? 'DEPENDENCY_NOT_PASSED' : 'PROVIDER_NOT_CONFIGURED'
          await save(reportPath, report); continue
        }
        if (report.steps.some(item => item !== row && (item.status === 'indeterminate' || item.status === 'interrupted'
          || item.required && item.status !== 'passed' || item.status === 'failed' && mutation(item.effects)))) {
          row.status = 'blocked'; row.reason = 'REQUIRED_GATE_FAILED'; await save(reportPath, report); continue
        }
        if (digest(await this.inputs(plan.projectId, plan.workflowId)) !== digest(plan.inputs)) fail('STALE_PLAN')
        await verifyLocks()
        const adapter = this.adapters[step.adapterId]
        const operation = adapter.descriptor.operations[step.operation]
        row.status = 'running'; row.startedAt = Date.now()
        await save(reportPath, report)
        const artifactDir = join(runDir, step.id)
        await mkdir(artifactDir, { mode: 0o700 })
        let output
        const priorMutations = new Map()
        try {
          if (controller.signal.aborted) fail('CANCELLED_BEFORE_EXECUTION')
          if (mutation(step.effects)) for (const resource of step.resources) {
            const target = report.targets.find(item => item.id === resource.id)
            priorMutations.set(resource.id, target.mutationState)
            target.stages.push({ stepId: step.id, mutationState: 'unknown' })
            target.mutationState = 'unknown'; target.recoveryState = 'required'
          }
          updateMutation(); await save(reportPath, report)
          if (controller.signal.aborted) {
            for (const [id, previous] of priorMutations) {
              const target = report.targets.find(item => item.id === id)
              target.mutationState = previous; target.stages.at(-1).mutationState = 'not-applied'
            }
            fail('CANCELLED_BEFORE_EXECUTION')
          }
          output = await executeBounded(adapter, step, { cwd: plan.inputs.root, signal: controller.signal,
            runId, stepId: step.id, artifactDir, timeoutMs: step.timeoutMs, sourceDigest: plan.inputs.source.digest })
          if (mutation(step.effects)) {
            for (const resource of step.resources) {
              const target = report.targets.find(item => item.id === resource.id)
              const state = ['not-applied', 'applied'].includes(output?.mutationState) ? output.mutationState : 'unknown'
              target.stages.at(-1).mutationState = state
              target.mutationState = mergeMutation(priorMutations.get(resource.id), state)
            }
          }
          validateSchema(operation.resultSchema, output?.data)
          const validator = this.validators[step.validator] ?? ((data, context) => validateEvidence(step.validator, data, context))
          const evidence = await validator(output.data, { runId, sourceDigest: plan.inputs.source.digest })
          if (!['passed', 'failed', 'indeterminate'].includes(evidence?.status)) fail('INVALID_VALIDATOR_RESULT')
          row.status = evidence.status; row.reason = evidence.status === 'passed' ? null : safeReason(evidence.reason)
          row.evidence = { validator: step.validator, adapterId: step.adapterId, adapterDigest: step.adapterDigest,
            sourceDigest: plan.inputs.source.digest, validated: true }
          if (output.data?.terminationConfirmed === false) { row.status = 'indeterminate'; row.reason = 'EXECUTOR_STOP_UNCONFIRMED'; retainLocks = true }
          if (digest(await this.inputs(plan.projectId, plan.workflowId)) !== digest(plan.inputs)) {
            row.status = 'indeterminate'; row.reason = 'INPUT_CHANGED_DURING_EXECUTION'; row.evidence.validated = false
          }
          await verifyLocks()
          if (mutation(step.effects) && step.resources.some(resource => report.targets.find(target => target.id === resource.id).mutationState === 'unknown')) {
            row.status = 'indeterminate'; row.reason = 'MUTATION_STATE_UNCONFIRMED'; retainLocks = true
          }
          if (controller.signal.aborted) { row.status = 'interrupted'; row.reason = 'CANCELLED' }
        } catch (error) {
          row.status = controller.signal.aborted ? 'interrupted' : error.code === 'STEP_TIMEOUT' && !mutation(step.effects) ? 'failed' : 'indeterminate'
          row.reason = controller.signal.aborted ? 'CANCELLED' : error.code === 'STEP_TIMEOUT' ? 'STEP_TIMEOUT' : 'EXECUTION_OR_EVIDENCE_INVALID'
          if (error.code !== 'CANCELLED_BEFORE_EXECUTION' && mutation(step.effects)) for (const resource of step.resources) {
            const target = report.targets.find(item => item.id === resource.id)
            target.mutationState = 'unknown'; target.recoveryState = 'required'
            if (target.stages.at(-1)?.stepId === step.id) target.stages.at(-1).mutationState = 'unknown'
          }
          if (error.code === 'EXECUTOR_STOP_UNCONFIRMED') retainLocks = true
        }
        if (mutation(step.effects) && (row.status === 'interrupted' || row.status === 'indeterminate')) retainLocks = true
        row.finishedAt = Date.now(); updateMutation()
        await save(reportPath, report)
      }
      const required = report.steps.filter(step => step.required)
      report.verdict = controller.signal.aborted ? 'INTERRUPTED'
        : report.mutationState === 'unknown' || report.steps.some(step => step.status === 'indeterminate') ? 'INDETERMINATE'
        : report.steps.some(step => step.status === 'failed' && (step.required || mutation(step.effects))) ? 'FAIL'
        : required.length && required.every(step => step.status === 'passed') ? 'PASS' : 'BLOCKED'
    } catch (error) {
      report.verdict = report.mutationState === 'unknown' ? 'INDETERMINATE' : 'BLOCKED'
      report.reason = safeReason(error.code ?? error.message)
    } finally {
      updateMutation()
      if (report.mutationState === 'unknown') retainLocks = true
      for (const target of report.targets) target.recoveryState = target.mutationState !== 'not-applied' && report.verdict !== 'PASS' ? 'required' : 'not-required'
      report.recoveryState = report.targets.some(target => target.recoveryState === 'required') ? 'required' : 'not-required'
      if (report.recoveryState === 'required') retainLocks = true
      report.finishedAt = Date.now()
      report.retainedLocks = retainLocks
      if (!retainLocks) for (const lock of locks.reverse()) {
        try {
          const holder = await json(join(lock, 'owner.json'))
          if (holder.runId !== runId || holder.principal !== principal) fail('LOCK_OWNERSHIP_LOST')
          await rm(lock, { recursive: true })
        } catch {
          report.verdict = 'INDETERMINATE'; report.reason = 'LOCK_CLEANUP_NOT_CONFIRMED'; report.retainedLocks = true
        }
      }
      await save(reportPath, report)
      this.active.delete(runId)
    }
    return clone(report)
  }

  async result({ runId, principal }) {
    checkId(runId); await this.permit(principal, 'result', { runId })
    const report = await json(join(this.stateDir, 'runs', runId, 'result.json'))
    if (report.principal !== principal) fail('NOT_AUTHORIZED')
    const recovered = await recoveryResult(this, report)
    if (recovered === report && !report.finishedAt && !this.active.has(runId)) return { ...report, observation: 'owner-not-attached', reason: 'OWNER_LIVENESS_NOT_VERIFIED' }
    return recovered
  }

  async recover(args) { return recover(this, args) }

  async cancel({ runId, principal }) {
    checkId(runId); await this.permit(principal, 'cancel', { runId })
    const active = this.active.get(runId)
    if (!active || active.principal !== principal) fail('RUN_NOT_OWNED_OR_NOT_ACTIVE')
    active.controller.abort()
    return { runId, cancellationRequested: true }
  }
}
