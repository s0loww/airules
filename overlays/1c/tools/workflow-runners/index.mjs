import { lstat, readdir, realpath } from 'node:fs/promises'
import { basename, isAbsolute, resolve } from 'node:path'
import { canonical, digest } from '../../../../core/tools/workflow/lib/contracts.mjs'
import { projectPath, safeRead, hashBytes, within } from '../../../../core/tools/workflow/lib/snapshot.mjs'
import { validateOnecProfile } from '../workflow-onec/index.mjs'

const RUNNERS = Object.freeze({
  'agent-1c': 'tools/agent-1c/agent-1c.ps1',
  'test-env': 'scripts/RunUnitTests.ps1',
})
const BINDING_KEYS = new Set(['schemaVersion', 'kind', 'runnerPath', 'profilePath', 'sourceKind', 'extensionName', 'exactBuild'])
const COMMAND_KEYS = new Set(['runnerKind', 'operation', 'root', 'runnerPath', 'profilePath', 'pwshPath', 'deployContext'])
const READ_EFFECTS = ['readsSource', 'startsProcess', 'writesFilesystem']
const MUTATING_EFFECTS = [...READ_EFFECTS, 'connectsTarget', 'writesTargetData', 'changesMetadata', 'serviceLifecycle']
function fail(code) { throw Object.assign(new Error(code), { code }) }
const text = value => typeof value === 'string' && value.length > 0 && !value.includes('\0')
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value)
function fields(value, allowed) {
  if (!plain(value) || Object.keys(value).some(key => !allowed.has(key))) fail('RUNNER_BINDING_INVALID')
  canonical(value)
}
function relativePath(path) {
  if (!text(path) || isAbsolute(path) || /^[A-Za-z]:/u.test(path)
    || path.split(/[\\/]/u).some(part => part === '..' || part === '.' || part === '')) fail('RUNNER_PATH_INVALID')
  return path.replaceAll('\\', '/')
}
function runnerPath(kind, path) {
  if (!Object.hasOwn(RUNNERS, kind) || relativePath(path) !== RUNNERS[kind]) fail('RUNNER_NOT_ALLOWLISTED')
  return RUNNERS[kind]
}
function profilePath(path) {
  const normalized = relativePath(path)
  if (!/\.json$/iu.test(normalized)) fail('PROFILE_JSON_REQUIRED')
  return normalized
}
async function readMetadata(root, rel, maxBytes) {
  const path = await projectPath(root, rel)
  const bytes = await safeRead(root, path, maxBytes)
  let content
  try { content = new TextDecoder('utf-8', { fatal: true }).decode(bytes) } catch { fail('RUNNER_UTF8_REQUIRED') }
  if (content.includes('\0')) fail('RUNNER_TEXT_REQUIRED')
  return { path: rel, digest: hashBytes(bytes), bytes: bytes.length, content }
}
function publicFile({ path, digest, bytes }) { return { path, digest, bytes } }

async function agentCodeClosure(root, runner, dependencies) {
  const files = new Map([[runner.path, publicFile(runner)]])
  for (const file of dependencies) files.set(file.path, file)
  let visited = 0; let totalBytes = 0
  async function visit(rel, depth = 0) {
    if (++visited > 4096 || depth > 16) fail('RUNNER_CLOSURE_LIMIT')
    const path = await projectPath(root, rel)
    const stat = await lstat(path)
    if (stat.isSymbolicLink()) fail('SYMLINK_INPUT')
    if (stat.isDirectory()) {
      for (const child of (await readdir(path)).sort()) await visit(`${rel}/${child}`, depth + 1)
    } else if (stat.isFile() && /\.(?:ps1|psm1)$/iu.test(rel)) {
      if (files.size >= 256) fail('RUNNER_CLOSURE_LIMIT')
      const file = publicFile(await readMetadata(root, rel, 2 * 1024 * 1024))
      totalBytes += file.bytes
      if (totalBytes > 8 * 1024 * 1024) fail('RUNNER_CLOSURE_LIMIT')
      files.set(rel, file)
    } else if (!stat.isFile()) fail('RUNNER_CLOSURE_FILE_REQUIRED')
  }
  await visit('tools/agent-1c')
  return [...files.values()].sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0)
}

function declaredAgentCommands(content) {
  // Only literal declarations in the parameter header are recognized; no PowerShell is evaluated.
  const header = content.slice(0, 8192).split(/\bfunction\s/iu)[0]
  const match = header.match(/\[ValidateSet\(([^)]{1,1024})\)\]\s*\[string\]\s*\$Command\b/iu)
  if (!match || !/^\s*'[A-Za-z-]+'(?:\s*,\s*'[A-Za-z-]+')*\s*$/u.test(match[1])) fail('RUNNER_COMMAND_DECLARATION_UNSUPPORTED')
  return { commands: new Set([...match[1].matchAll(/'([^']+)'/gu)].map(match => match[1])),
    hidden: /\[switch\]\s*\$Hidden\b/iu.test(header),
    apply: /\[switch\]\s*\$Apply\b/iu.test(header),
    profile: /\[string\]\s*\$Profile\b/iu.test(header),
    workflow: ['RunId', 'StepId', 'SourceDigest', 'TargetDigest', 'ProfileDigest', 'ExactBuild', 'TargetPath']
      .every(suffix => new RegExp(`\\[string\\]\\s*\\$Workflow${suffix}\\b`, 'iu').test(header)) }
}

function operation(supported, effects, { configured = supported, reason = null, needsIsolation = false,
  readsCredentialReferences = false } = {}) {
  return { supported, configured, enabled: false, effects, needsIsolation,
    readsCredentialReferences, reason: reason ?? (supported ? 'EXECUTION_NOT_ENABLED' : 'RUNNER_OPERATION_UNSUPPORTED') }
}

/** Offline inspection only. It never resolves credential references or executes a runner. */
export async function inspectRunnerBinding({ root, binding }) {
  fields(binding, BINDING_KEYS)
  if (binding.schemaVersion !== 1 || !text(root) || !isAbsolute(root)) fail('RUNNER_BINDING_INVALID')
  const requestedRoot = resolve(root)
  if ((await lstat(requestedRoot)).isSymbolicLink()) fail('SYMLINK_INPUT')
  const actualRoot = await realpath(requestedRoot)
  if (!(await lstat(actualRoot)).isDirectory()) fail('PROJECT_ROOT_REQUIRED')
  const rel = runnerPath(binding.kind, binding.runnerPath)
  const runner = await readMetadata(actualRoot, rel, 2 * 1024 * 1024)
  const dependencies = []
  let profile = null; let profileEvidence = null; let operations
  if (binding.kind === 'agent-1c') {
    const commands = declaredAgentCommands(runner.content)
    if (!commands.profile) fail('RUNNER_PROFILE_PARAMETER_REQUIRED')
    const profileFile = await readMetadata(actualRoot, profilePath(binding.profilePath), 512 * 1024)
    let parsed
    try { parsed = JSON.parse(profileFile.content) } catch { fail('PROFILE_JSON_INVALID') }
    profileEvidence = validateOnecProfile(parsed, { sourceKind: binding.sourceKind,
      ...(binding.extensionName === undefined ? {} : { extensionName: binding.extensionName }), exactBuild: binding.exactBuild })
    profile = publicFile(profileFile)
    // Hash fixed known dependencies, but never traverse profile.envFile or read an env file.
    for (const dependency of ['tools/agent-1c/lib/1c-guard.ps1', 'tools/agent-1c/toolchain.lock.json']) {
      dependencies.push(publicFile(await readMetadata(actualRoot, dependency, 512 * 1024)))
    }
    if (commands.hidden) dependencies.push(publicFile(await readMetadata(actualRoot, 'tools/agent-1c/lib/hidden-desktop.ps1', 512 * 1024)))
    const fileTarget = parsed.testTarget.kind === 'file'
    const unitDeclared = profileEvidence.capabilities.unit.status === 'declared'
    const uiDeclared = profileEvidence.capabilities.vanessa.status === 'declared'
    operations = {
      doctor: operation(commands.commands.has('doctor'), [...READ_EFFECTS]),
      analyze: operation(commands.commands.has('analyze'), [...READ_EFFECTS]),
      'deploy-preview': operation(commands.commands.has('deploy') && commands.apply, [...READ_EFFECTS, 'externalIO'],
        { readsCredentialReferences: true, reason: 'PREVIEW_READS_CREDENTIAL_REFERENCES_AND_WRITES_REPORTS' }),
      unit: operation(commands.commands.has('unit'), [...MUTATING_EFFECTS],
        { configured: commands.commands.has('unit') && unitDeclared, needsIsolation: true }),
      test: operation(commands.commands.has('test') && fileTarget, [...MUTATING_EFFECTS],
        { configured: commands.commands.has('test') && fileTarget && uiDeclared, needsIsolation: true }),
      'test-hidden': operation(commands.commands.has('test') && commands.hidden && fileTarget, [...MUTATING_EFFECTS],
        { configured: commands.commands.has('test') && commands.hidden && fileTarget && uiDeclared, needsIsolation: true }),
      serve: operation(commands.commands.has('serve') && fileTarget, [...READ_EFFECTS, 'connectsTarget', 'serviceLifecycle'], { needsIsolation: true }),
      stop: operation(commands.commands.has('stop') && fileTarget, [...READ_EFFECTS, 'connectsTarget', 'serviceLifecycle'], { needsIsolation: true }),
      'deploy-apply': operation(commands.commands.has('deploy') && commands.apply && commands.workflow, [...MUTATING_EFFECTS],
        { needsIsolation: true, readsCredentialReferences: true, reason: commands.workflow ? 'DEPLOY_TARGET_AUTHORIZATION_REQUIRED' : 'DEPLOY_PROTOCOL_REQUIRED' }),
    }
  } else {
    if (binding.profilePath !== undefined || binding.extensionName !== undefined) fail('TEST_ENV_PROFILE_UNSUPPORTED')
    if (binding.sourceKind !== undefined && binding.sourceKind !== 'configuration') fail('SOURCE_KIND_UNSUPPORTED')
    if (binding.exactBuild !== undefined && !/^\d+\.\d+\.\d+\.\d+$/u.test(binding.exactBuild)) fail('EXACT_BUILD_REQUIRED')
    dependencies.push(publicFile(await readMetadata(actualRoot, 'scripts/TestEnv.ps1', 2 * 1024 * 1024)))
    operations = {
      unit: operation(true, [...MUTATING_EFFECTS], { needsIsolation: true,
        reason: 'TEST_ENV_IMPORTS_CONFIG_AND_UPDATES_DATABASE' }),
      test: operation(false, [...MUTATING_EFFECTS], { reason: 'MANUAL_UI_RUNNER_NOT_AUTOMATED_GATE' }),
      'deploy-apply': operation(false, [...MUTATING_EFFECTS], { reason: 'DEPLOY_APPLY_NOT_AVAILABLE' }),
    }
  }
  const closureFiles = binding.kind === 'agent-1c' ? await agentCodeClosure(actualRoot, runner, dependencies)
    : [publicFile(runner), ...dependencies].sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0)
  const closureDigest = digest({ kind: binding.kind, files: closureFiles })
  const fingerprintPaths = [...new Set([...closureFiles.map(file => file.path), ...(profile ? [profile.path] : [])])].sort()
  const result = { schemaVersion: 1, kind: binding.kind, runner: publicFile(runner), profile, dependencies,
    closureDigest, codeClosure: { digest: closureDigest, files: closureFiles, reviewRequired: true }, fingerprintPaths,
    profileEvidence, operations, executionEnabled: false, deployEnabled: false,
    credentialsResolved: false, sourceFactsVerified: false, pinnedBuildVerified: false,
    limitations: binding.kind === 'test-env'
      ? ['METADATA_ONLY', 'EXACT_BUILD_NOT_ENFORCED_BY_RUNNER', 'UNIT_RUNNER_NEEDS_TIMEOUT_AND_NONZERO_TEST_GATE', 'REVIEW_TESTENV_PROCESS_OWNERSHIP', 'NO_AUTOMATIC_UI_OR_RUNALLTESTS']
      : ['METADATA_ONLY', 'SOURCE_XML_FACTS_SUPPLIED', 'PLATFORM_BUILD_SUPPLIED_NOT_PROBED', 'RUNNER_HASH_IS_NOT_CODE_REVIEW', 'NO_CREDENTIAL_RESOLUTION'] }
  return { ...result, fingerprint: digest({ binding, closureDigest, runner: result.runner, profile, dependencies, operations }) }
}

/** Compile a trusted fixed invocation. This function never starts a process. */
export function compileRunnerCommand(options) {
  fields(options, COMMAND_KEYS)
  const { runnerKind, operation: requestedOperation, root, pwshPath } = options
  if (!['deploy-apply', 'deploy-preview'].includes(requestedOperation) && options.deployContext !== undefined) fail('DEPLOY_CONTEXT_UNEXPECTED')
  if (!text(root) || !isAbsolute(root) || !text(pwshPath) || !isAbsolute(pwshPath)
    || !/^(?:pwsh|powershell)(?:\.exe)?$/iu.test(basename(pwshPath))) fail('TRUSTED_POWERSHELL_REQUIRED')
  const rel = runnerPath(runnerKind, options.runnerPath)
  const cwd = resolve(root); const script = resolve(cwd, rel)
  if (!within(cwd, script)) fail('PATH_ESCAPE')
  const args = ['-NoLogo', '-NoProfile', '-NonInteractive', '-File', script]
  let effects
  if (runnerKind === 'agent-1c') {
    const operations = { doctor: ['doctor'], analyze: ['analyze'], 'deploy-preview': ['deploy'], 'deploy-apply': ['deploy', '-Apply'],
      unit: ['unit'], test: ['test'], 'test-hidden': ['test', '-Hidden'], serve: ['serve'], stop: ['stop'] }
    if (!Object.hasOwn(operations, requestedOperation)) fail('RUNNER_OPERATION_UNSUPPORTED')
    const profile = resolve(cwd, profilePath(options.profilePath))
    if (!within(cwd, profile)) fail('PATH_ESCAPE')
    const [command, ...flags] = operations[requestedOperation]
    args.push(command, '-Profile', profile, ...flags)
    if (requestedOperation === 'deploy-apply' || requestedOperation === 'deploy-preview' && options.deployContext !== undefined) {
      const context = options.deployContext
      fields(context, new Set(['runId', 'stepId', 'sourceDigest', 'targetDigest', 'profileDigest', 'exactBuild', 'targetPath', 'targetKind', 'targetServer', 'targetRef']))
      if (typeof context.runId !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/u.test(context.runId)
        || typeof context.stepId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u.test(context.stepId)
        || ['sourceDigest', 'targetDigest', 'profileDigest'].some(key => typeof context[key] !== 'string' || !/^[a-f0-9]{64}$/u.test(context[key]))
        || typeof context.exactBuild !== 'string' || !/^\d+\.\d+\.\d+\.\d+$/u.test(context.exactBuild)) fail('DEPLOY_CONTEXT_INVALID')
      const server = context.targetKind === 'server'
      if (server) {
        if (context.targetPath !== undefined && context.targetPath !== null || !text(context.targetServer) || !text(context.targetRef)) fail('DEPLOY_CONTEXT_INVALID')
        const normalized = normalizeServerContext(context.targetServer, context.targetRef)
        if (normalized.server !== context.targetServer || normalized.ref !== context.targetRef) fail('DEPLOY_CONTEXT_INVALID')
      } else if (context.targetKind !== undefined && context.targetKind !== 'file' || context.targetServer !== undefined || context.targetRef !== undefined
        || !text(context.targetPath) || !isAbsolute(context.targetPath)) fail('DEPLOY_CONTEXT_INVALID')
      for (const key of ['runId', 'stepId', 'sourceDigest', 'targetDigest', 'profileDigest', 'exactBuild', ...(server ? ['targetKind', 'targetServer', 'targetRef'] : ['targetPath'])]) {
        args.push(`-Workflow${key[0].toUpperCase()}${key.slice(1)}`, context[key])
      }
    }
    effects = ['doctor', 'analyze'].includes(requestedOperation) ? [...READ_EFFECTS]
      : requestedOperation === 'deploy-preview' ? [...READ_EFFECTS, 'externalIO'] : [...MUTATING_EFFECTS]
  } else {
    if (options.profilePath !== undefined || requestedOperation !== 'unit') fail('RUNNER_OPERATION_UNSUPPORTED')
    effects = [...MUTATING_EFFECTS]
  }
  // -Apply belongs only to the explicit deploy-apply operation. No arbitrary parameters or shell string.
  return { command: pwshPath, args, cwd, effects, enabled: false, requiresInspection: true }
}

import { normalizeDeployServerTarget as normalizeServerContext } from './deploy.mjs'
export { inspectDeployBinding, validateDeployReport, normalizeDeployServerTarget } from './deploy.mjs'
