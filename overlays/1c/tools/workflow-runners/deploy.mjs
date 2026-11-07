import { lstat, realpath } from 'node:fs/promises'
import { dirname, isAbsolute, resolve } from 'node:path'
import { digest } from '../../../../core/tools/workflow/lib/contracts.mjs'
import { projectPath, safeRead, hashBytes, within } from '../../../../core/tools/workflow/lib/snapshot.mjs'
import { inspectRunnerBinding } from './index.mjs'
import { isIP } from 'node:net'

const fail = code => { throw Object.assign(new Error(code), { code }) }
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const SHA = /^[a-f0-9]{64}$/u
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/u
const text = value => typeof value === 'string' && value.trim() !== '' && !/[\x00-\x1f]/u.test(value)
function relativePath(value) {
  if (!text(value) || isAbsolute(value) || /^[A-Za-z]:/u.test(value)
    || value.split(/[\\/]/u).some(part => !part || part === '.' || part === '..')) fail('DEPLOY_PROJECT_PATH_REQUIRED')
  return value.replaceAll('\\', '/')
}

/** Normalize direct cluster metadata without DNS, credentials or a network call. */
export function normalizeDeployServerTarget(server, ref) {
  if (!text(server) || !text(ref) || server.length > 300 || ref.length > 200
    || /[\\/;"'\x00-\x1f]/u.test(ref)) fail('DEPLOY_SERVER_TARGET_INVALID')
  const endpoint = server.trim().toLowerCase()
  let host, port = '1541'
  if (endpoint.startsWith('[')) {
    const matched = endpoint.match(/^\[([^\]]+)\](?::(\d{1,5}))?$/u)
    if (!matched || isIP(matched[1]) !== 6) fail('DEPLOY_SERVER_TARGET_INVALID')
    const address = new URL(`http://[${matched[1]}]/`).hostname.slice(1, -1)
    const [left, right] = address.split('::').map(part => part ? part.split(':') : [])
    const groups = right === undefined ? left : [...left, ...Array(8 - left.length - right.length).fill('0'), ...right]
    host = `[${groups.map(group => group.padStart(4, '0')).join(':')}]`
    port = matched[2] ?? port
  } else {
    const matched = endpoint.match(/^([a-z0-9_][a-z0-9_.-]*)(?::(\d{1,5}))?$/u)
    if (!matched) fail('DEPLOY_SERVER_TARGET_INVALID')
    host = matched[1].replace(/\.$/u, '')
    if (!host || host.split('.').some(label => !label || label.startsWith('-') || label.endsWith('-'))) fail('DEPLOY_SERVER_TARGET_INVALID')
    port = matched[2] ?? port
  }
  const number = Number(port)
  if (!Number.isInteger(number) || number < 1 || number > 65535) fail('DEPLOY_SERVER_TARGET_INVALID')
  const normalizedRef = ref.trim().normalize('NFC').toLowerCase()
  if (!normalizedRef) fail('DEPLOY_SERVER_TARGET_INVALID')
  return { server: `${host}:${number}`, ref: normalizedRef }
}

/** Private in-memory deploy context. It never opens an env file or a database. */
export async function inspectDeployBinding({ root, binding }) {
  const info = await inspectRunnerBinding({ root, binding })
  if (binding.kind !== 'agent-1c' || !info.operations['deploy-apply']?.supported) fail('DEPLOY_PROTOCOL_REQUIRED')
  // agent-1c resolves source and target relative to the profile's parent.
  // Until nested-profile bindings have a separate root contract, require root profile.
  if (binding.profilePath !== 'agent-1c.json') fail('DEPLOY_ROOT_PROFILE_REQUIRED')
  const actualRoot = await realpath(root)
  const bytes = await safeRead(actualRoot, await projectPath(actualRoot, binding.profilePath), 512 * 1024)
  if (hashBytes(bytes) !== info.profile.digest) fail('DEPLOY_PROFILE_CHANGED')
  let profile
  try { profile = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes).replace(/^\uFEFF/u, '')) }
  catch { fail('PROFILE_JSON_INVALID') }
  const target = profile.testTarget
  if (!['file', 'server'].includes(target.kind)) fail('DEPLOY_TARGET_KIND_REQUIRED')
  if (!['test', 'development'].includes(target.environment)) fail('DEPLOY_TARGET_ENVIRONMENT_FORBIDDEN')
  let targetPath = null, serverTarget = null
  if (target.kind === 'server') {
    const runnerBytes = await safeRead(actualRoot, await projectPath(actualRoot, binding.runnerPath), 2 * 1024 * 1024)
    const header = new TextDecoder('utf-8', { fatal: true }).decode(runnerBytes).slice(0, 8192).split(/\bfunction\s/iu)[0]
    if (!['Kind', 'Server', 'Ref'].every(suffix => new RegExp(`\\[string\\]\\s*\\$WorkflowTarget${suffix}\\b`, 'iu').test(header))) fail('DEPLOY_SERVER_PROTOCOL_REQUIRED')
    serverTarget = normalizeDeployServerTarget(target.server, target.ref)
    if (profile.platform?.engine === 'ibcmd') fail('DEPLOY_SERVER_ENGINE_UNSUPPORTED')
  } else {
    if (!text(target.path)) fail('DEPLOY_DIRECT_TARGET_PATH_REQUIRED')
    targetPath = resolve(actualRoot, target.path)
    // A junction/alias must not obtain a second lock identity for the same base.
    // Missing bases are supported by checking their nearest existing ancestor.
    let ancestor = targetPath
    for (;;) {
      try {
        if ((await lstat(ancestor)).isSymbolicLink()) fail('DEPLOY_TARGET_ALIAS_FORBIDDEN')
        const actual = await realpath(ancestor)
        const normalize = value => process.platform === 'win32' ? value.toLowerCase() : value
        if (normalize(actual) !== normalize(ancestor)) fail('DEPLOY_TARGET_ALIAS_FORBIDDEN')
        break
      } catch (error) {
        if (error.code !== 'ENOENT') throw error
        const next = dirname(ancestor)
        if (next === ancestor) fail('DEPLOY_TARGET_PATH_INVALID')
        ancestor = next
      }
    }
  }
  // The target identity must not alias a mutable project input or its report directory.
  const sourcePath = relativePath(profile.sourceDir), resultPath = relativePath(profile.resultDir)
  if (sourcePath === resultPath || sourcePath.startsWith(`${resultPath}/`) || resultPath.startsWith(`${sourcePath}/`)) fail('DEPLOY_SOURCE_RESULT_OVERLAP')
  const source = await projectPath(actualRoot, sourcePath)
  if (!(await lstat(source)).isDirectory()) fail('DEPLOY_SOURCE_DIRECTORY_REQUIRED')
  if (targetPath && (within(targetPath, source) || within(source, targetPath) || within(targetPath, resolve(actualRoot, resultPath)) || within(resolve(actualRoot, resultPath), targetPath))) fail('DEPLOY_TARGET_PATH_OVERLAP')
  // There is no platform process probe in offline inspection. The runner checks
  // the actually selected platform directory against this exact build before mutation.
  const identity = targetPath && (process.platform === 'win32' ? targetPath.toLowerCase() : targetPath)
  const targetDigest = digest(serverTarget ? { kind: 'server', ...serverTarget } : { kind: 'file', path: identity })
  return { projectId: profile.projectId, sourcePath, resultPath, profileDigest: info.profile.digest,
    exactBuild: binding.exactBuild, targetPath, targetDigest,
    ...(serverTarget ? { targetServer: serverTarget.server, targetRef: serverTarget.ref } : {}),
    target: { id: `onec-${targetDigest}`, kind: target.kind, environment: target.environment },
    closureDigest: info.closureDigest, fingerprint: digest({ profileDigest: info.profile.digest,
      sourcePath, resultPath, exactBuild: binding.exactBuild, targetDigest, environment: target.environment }) }
}

/** Validate a bound runner report; never return arbitrary runner messages or artifacts. */
export function validateDeployReport(report, expected) {
  if (!plain(expected) || !UUID.test(expected.runId ?? '') || !ID.test(expected.stepId ?? '')
    || ['sourceDigest', 'targetDigest', 'profileDigest'].some(key => !SHA.test(expected[key] ?? ''))
    || !text(expected.projectId) || !Number.isFinite(expected.startedAfter) || !Number.isFinite(expected.finishedBefore)
    || expected.startedAfter > expected.finishedBefore) fail('DEPLOY_REPORT_CONTEXT_INVALID')
  const preview = expected.operation === 'deploy-preview'
  if (expected.operation !== undefined && !['deploy-apply', 'deploy-preview'].includes(expected.operation)) fail('DEPLOY_REPORT_CONTEXT_INVALID')
  if (!plain(report) || report.schemaVersion !== 1 || report.projectId !== expected.projectId
    || report.command !== 'deploy' || report.apply !== !preview || !Number.isSafeInteger(report.exitCode)
    || !plain(report.workflow) || report.workflow.schemaVersion !== 1) fail('DEPLOY_REPORT_INVALID')
  for (const key of ['runId', 'stepId', 'sourceDigest', 'targetDigest', 'profileDigest']) {
    if (report.workflow[key] !== expected[key]) fail('DEPLOY_REPORT_IDENTITY_MISMATCH')
  }
  const start = typeof report.startedAtUtc === 'string' ? Date.parse(report.startedAtUtc) : NaN
  const finish = typeof report.finishedAtUtc === 'string' ? Date.parse(report.finishedAtUtc) : NaN
  if (!Number.isFinite(start) || !Number.isFinite(finish) || start < expected.startedAfter || finish < start
    || finish > expected.finishedBefore) fail('DEPLOY_REPORT_STALE')
  const mutationState = report.workflow.mutationState
  if (!['not-applied', 'unknown', 'applied'].includes(mutationState)) fail('DEPLOY_REPORT_MUTATION_INVALID')
  if (!Array.isArray(report.steps) || report.steps.length === 0 || report.steps.length > 4096
    || report.steps.some(step => !plain(step) || !text(step.name) || !text(step.status))) fail('DEPLOY_REPORT_STEPS_INVALID')
  const terminal = report.steps.filter(step => step.name === 'deploy.apply')
  if (mutationState === 'not-applied' && report.steps.some(step => /^deploy\.apply(?:\.|$)/u.test(step.name) && step.status === 'ok')) fail('DEPLOY_REPORT_MUTATION_CONTRADICTION')
  const successful = report.exitCode === 0 && mutationState === (preview ? 'not-applied' : 'applied') && terminal.length === 1 && terminal[0].status === (preview ? 'dry-run' : 'ok')
    && !report.steps.some(step => ['error', 'failed', ...(preview ? [] : ['dry-run'])].includes(step.status))
  return { complete: true, mutationState, assertions: [
    { id: 'deploy-report-bound', passed: true },
    { id: 'deploy-process-exit', passed: report.exitCode === 0 },
    { id: preview ? 'deploy-preview' : 'deploy-applied', passed: successful },
  ] }
}
