import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { canonical } from '../../../../core/tools/workflow/lib/contracts.mjs'

// Offline metadata gate. No runner, database, environment or XML is opened here.
const EXACT_BUILD = /^\d+\.\d+\.\d+\.\d+$/u
const ENVIRONMENTS = new Set(['test', 'development', 'production'])
const CHECK_CONTEXTS = new Set([
  'ThinClient', 'WebClient', 'Server', 'ExternalConnection',
  'ThickClientOrdinaryApplication', 'MobileAppClient', 'MobileAppServer',
])
const SECRET_KEYS = new Set(['password', 'token', 'apikey', 'accesstoken', 'refreshtoken', 'clientsecret'])

function fail(code) { throw Object.assign(new Error(code), { code }) }
function plain(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && [Object.prototype, null].includes(Object.getPrototypeOf(value))
}
function text(value) { return typeof value === 'string' && value.trim().length > 0 && !value.includes('\0') }
function assert(condition, code) { if (!condition) fail(code) }
function rejectInlineCredentials(value, seen = new Set(), depth = 0) {
  assert(depth <= 30, 'PROFILE_DEPTH_EXCEEDED')
  if (value === null || typeof value !== 'object') return
  assert(!seen.has(value), 'PROFILE_CYCLE')
  seen.add(value)
  assert(Array.isArray(value) || plain(value), 'PROFILE_OBJECT_REQUIRED')
  for (const key of Object.keys(value)) {
    assert(!['__proto__', 'constructor', 'prototype'].includes(key), 'PROFILE_UNSAFE_KEY')
    assert(!SECRET_KEYS.has(key.toLowerCase()), 'INLINE_CREDENTIALS_NOT_SUPPORTED')
    rejectInlineCredentials(value[key], seen, depth + 1)
  }
  seen.delete(value)
}

/**
 * Validate the deployment-relevant subset of an existing agent-1c profile.
 * sourceKind/name/build are caller-provided verified facts, not discoveries.
 * This does not replace validation against the complete profile.schema.json.
 * No input field values are included in errors or returned evidence.
 */
export function validateOnecProfile(profile, facts = {}) {
  assert(plain(profile) && plain(facts), 'PROFILE_OBJECT_REQUIRED')
  rejectInlineCredentials(profile)
  assert(profile.schemaVersion === 1, 'PROFILE_VERSION_UNSUPPORTED')
  for (const field of ['projectId', 'sourceDir', 'resultDir']) {
    assert(text(profile[field]), 'PROFILE_REQUIRED_METADATA_MISSING')
  }
  const { sourceKind, extensionName, exactBuild } = facts
  assert(['configuration', 'extension'].includes(sourceKind), 'SOURCE_KIND_REQUIRED')
  assert(typeof exactBuild === 'string' && EXACT_BUILD.test(exactBuild), 'EXACT_BUILD_REQUIRED')
  assert(plain(profile.testTarget), 'TARGET_REQUIRED')
  const target = profile.testTarget
  assert(['file', 'server'].includes(target.kind), 'TARGET_KIND_UNSUPPORTED')
  assert(ENVIRONMENTS.has(target.environment), 'TARGET_ENVIRONMENT_REQUIRED')
  for (const field of ['path', 'server', 'ref', 'userEnv', 'passwordEnv', 'envFile', 'envSection', 'dataDir', 'ibsrvDataDir']) {
    assert(target[field] === undefined || target[field] === null || text(target[field]), 'TARGET_REFERENCE_INVALID')
  }
  assert(profile.platform === undefined || plain(profile.platform), 'PLATFORM_METADATA_INVALID')
  const platform = profile.platform ?? {}
  assert(platform.executable === undefined || platform.executable === null || text(platform.executable), 'PLATFORM_EXECUTABLE_INVALID')
  assert(platform.engine === undefined || ['auto', 'designer', 'ibcmd'].includes(platform.engine), 'DEPLOY_ENGINE_UNSUPPORTED')
  const engine = platform.engine ?? 'auto'
  assert(!(target.kind === 'server' && engine === 'ibcmd'), 'CLUSTER_IBCMD_FORBIDDEN')
  const prefix = platform.versionPrefix
  assert(prefix === undefined || prefix === null || (text(prefix) && /^\d+(?:\.\d+){0,3}$/u.test(prefix)), 'PLATFORM_PREFIX_INVALID')
  if (prefix != null) {
    assert(exactBuild === prefix || exactBuild.startsWith(`${prefix}.`), 'PLATFORM_BUILD_MISMATCH')
  }
  assert(profile.extension === undefined || plain(profile.extension), 'EXTENSION_METADATA_INVALID')
  const extension = profile.extension ?? {}
  assert(extension.name === undefined || extension.name === null || text(extension.name), 'EXTENSION_NAME_INVALID')
  assert(extensionName === undefined || text(extensionName), 'EXTENSION_NAME_INVALID')
  if (sourceKind === 'extension') {
    assert(text(extensionName) && text(extension.name), 'EXTENSION_NAME_REQUIRED')
    assert(extension.name === extensionName, 'EXTENSION_NAME_MISMATCH')
  } else {
    assert(!text(extension.name) && !text(extensionName), 'CONFIGURATION_EXTENSION_CONFLICT')
  }
  assert(extension.scope === undefined || ['infobase', 'data-separation'].includes(extension.scope), 'EXTENSION_SCOPE_INVALID')
  assert(extension.safeMode === undefined || typeof extension.safeMode === 'boolean', 'EXTENSION_SAFE_MODE_INVALID')
  assert(profile.unit === undefined || plain(profile.unit), 'UNIT_METADATA_INVALID')
  if (profile.unit?.launchParameter !== undefined) assert(text(profile.unit.launchParameter), 'UNIT_METADATA_INVALID')
  assert(profile.probe === undefined || plain(profile.probe), 'PROBE_METADATA_INVALID')
  const contexts = profile.probe?.checkModules
  assert(contexts === undefined || (Array.isArray(contexts) && contexts.every(x => CHECK_CONTEXTS.has(x))
    && new Set(contexts).size === contexts.length), 'PROBE_CONTEXTS_INVALID')
  assert(profile.probe?.baseline === undefined || text(profile.probe.baseline), 'PROBE_BASELINE_INVALID')
  assert(profile.suspendServices === undefined || (Array.isArray(profile.suspendServices)
    && profile.suspendServices.every(text)), 'SERVICE_METADATA_INVALID')
  assert(profile.vanessa === undefined || plain(profile.vanessa), 'VANESSA_METADATA_INVALID')
  const connection = profile.vanessa?.connection
  assert(connection === undefined || ['file', 'ibsrv'].includes(connection), 'VANESSA_CONNECTION_UNSUPPORTED')
  const unitConfigured = text(profile.unit?.launchParameter)
  const probeConfigured = Array.isArray(contexts) && contexts.length > 0
  const vanessaDeclared = profile.vanessa !== undefined
  const production = target.environment === 'production'
  return {
    complete: true,
    assertions: [
      { id: 'profile-version', passed: true },
      { id: 'target-environment', passed: true },
      { id: 'source-kind-and-extension', passed: true },
      { id: 'exact-build-binding', passed: true },
      { id: 'engine-topology', passed: true },
    ],
    productionAuthorizationRequired: production,
    capabilities: {
      unit: { status: unitConfigured ? 'declared' : 'not-configured' },
      postdeployProbe: { status: probeConfigured ? 'declared' : 'not-configured' },
      vanessa: { status: target.kind === 'server' ? 'unsupported' : vanessaDeclared ? 'declared' : 'not-configured' },
      execution: { status: 'not-configured' },
    },
  }
}

const capabilitySchema = {
  type: 'object', required: ['status'], additionalProperties: false,
  properties: { status: { enum: ['declared', 'not-configured', 'unsupported'] } },
}
export function createOnecProfileAdapter() {
  const adapter = {
    descriptor: {
      protocolVersion: 1, id: 'onec.profile', version: '0.1.0',
      operations: {
        'validate-profile': {
          inputSchema: {
            type: 'object', required: ['profile', 'sourceKind', 'exactBuild'], additionalProperties: false,
            properties: {
              profile: { type: 'object' },
              sourceKind: { enum: ['configuration', 'extension'] },
              extensionName: { type: 'string', minLength: 1 },
              exactBuild: { type: 'string', minLength: 7, maxLength: 64 },
            },
          },
          resultSchema: {
            type: 'object', required: ['complete', 'assertions', 'productionAuthorizationRequired', 'capabilities'], additionalProperties: false,
            properties: {
              complete: { const: true },
              productionAuthorizationRequired: { type: 'boolean' },
              assertions: {
                type: 'array', minItems: 1,
                items: { type: 'object', required: ['id', 'passed'], additionalProperties: false,
                  properties: { id: { type: 'string', minLength: 1 }, passed: { type: 'boolean' } } },
              },
              capabilities: {
                type: 'object', required: ['unit', 'postdeployProbe', 'vanessa', 'execution'], additionalProperties: false,
                properties: { unit: capabilitySchema, postdeployProbe: capabilitySchema, vanessa: capabilitySchema, execution: capabilitySchema },
              },
            },
          },
          effects: ['readsSource'], validator: 'assertions',
        },
      },
    },
    execute(operation, inputs) {
      assert(operation === 'validate-profile', 'OPERATION_UNSUPPORTED')
      const { profile, ...facts } = inputs ?? {}
      return { data: validateOnecProfile(profile, facts), mutationState: 'not-applied' }
    },
    async fingerprint() {
      return createHash('sha256').update(await readFile(new URL(import.meta.url)))
        .update(canonical(adapter.descriptor)).digest('hex')
    },
  }
  return adapter
}
