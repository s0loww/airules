import { createHash } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { realpath, stat } from 'node:fs/promises'
import { isAbsolute } from 'node:path'
import { fileURLToPath } from 'node:url'
import { canonical, digest, validateDescriptor, validateSchema } from './contracts.mjs'

const MODULE_PATH = fileURLToPath(import.meta.url)
const REF = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u
const MUTATION_STATES = new Set(['not-applied', 'applied', 'unknown'])
const OPERATION_KEYS = new Set(['tool', 'inputSchema', 'resultSchema', 'effects', 'validator', 'resourcesRequired', 'mapInputs', 'mapResult'])
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value)
  && [Object.prototype, null].includes(Object.getPrototypeOf(value))
const clone = value => JSON.parse(canonical(value))
const error = code => Object.assign(new Error(code), { code })
const safeString = value => typeof value === 'string' && value.trim().length > 0 && value.length <= 256 && !/[\u0000-\u001f\u007f]/u.test(value)
const sourceOf = value => Function.prototype.toString.call(value)

function freeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze)
    Object.freeze(value)
  }
  return value
}

async function fingerprintFile(path) {
  const resolved = await realpath(path)
  const before = await stat(resolved)
  if (!before.isFile() || before.size > 1024 * 1024 * 1024) throw error('MCP_FINGERPRINT_FAILED')
  const hash = createHash('sha256')
  let bytes = 0
  for await (const chunk of createReadStream(resolved)) {
    bytes += chunk.length
    if (bytes > 1024 * 1024 * 1024) throw error('MCP_FINGERPRINT_FAILED')
    hash.update(chunk)
  }
  const after = await stat(resolved)
  if (before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ino !== after.ino || bytes !== after.size) {
    throw error('MCP_FINGERPRINT_FAILED')
  }
  return { path: resolved, bytes, sha256: hash.digest('hex') }
}

/**
 * Trusted host registration only. No network, discovery, credential access or
 * connection creation: the embedding client supplies its existing native caller.
 * Revision is a nonsecret host configuration/credential-record version, never a key.
 */
export function createMcpAdapter({ id, version = '0.1.0', connectionRef, connectionRevision, operations, call, fingerprintPaths = [] }) {
  let descriptor
  const registered = new Map()
  let paths
  try {
    if (!REF.test(connectionRef) || typeof connectionRef !== 'string' || !safeString(connectionRevision)
        || typeof call !== 'function' || !plain(operations) || !Array.isArray(fingerprintPaths)) throw error('MCP_CONFIGURATION_INVALID')
    paths = [...fingerprintPaths]
    if (paths.some(path => typeof path !== 'string' || !isAbsolute(path) || path.includes('\0'))) throw error('MCP_CONFIGURATION_INVALID')
    const described = Object.create(null)
    for (const [operation, config] of Object.entries(operations)) {
      if (!plain(config) || Object.keys(config).some(key => !OPERATION_KEYS.has(key))
          || !safeString(config.tool) || typeof config.mapResult !== 'function'
          || (config.mapInputs !== undefined && typeof config.mapInputs !== 'function')) throw error('MCP_CONFIGURATION_INVALID')
      const inputSchema = clone(config.inputSchema)
      const resultSchema = clone(config.resultSchema)
      const effects = clone(config.effects)
      described[operation] = { inputSchema, resultSchema, effects, validator: config.validator,
        ...(config.resourcesRequired === undefined ? {} : { resourcesRequired: config.resourcesRequired }) }
      registered.set(operation, { tool: config.tool, inputSchema: clone(inputSchema), resultSchema: clone(resultSchema),
        mapInputs: config.mapInputs, mapResult: config.mapResult })
    }
    descriptor = freeze(validateDescriptor({ protocolVersion: 1, id, version, operations: described }))
  } catch { throw error('MCP_CONFIGURATION_INVALID') }

  return {
    descriptor,
    async fingerprint() {
      try {
        const files = []
        for (const path of [...new Set([MODULE_PATH, ...paths])].sort()) files.push(await fingerprintFile(path))
        return digest({ descriptor, connectionRef, connectionRevision, files, caller: sourceOf(call),
          mappings: [...registered.entries()].map(([operation, config]) => ({ operation, tool: config.tool,
            inputMapper: config.mapInputs ? sourceOf(config.mapInputs) : 'canonical-json-identity-v1',
            resultMapper: sourceOf(config.mapResult) })) })
      } catch { throw error('MCP_FINGERPRINT_FAILED') }
    },
    async execute(operation, inputs, context = {}) {
      try {
        const config = registered.get(operation)
        if (!config) throw error('MCP_CALL_FAILED')
        if (context.signal !== undefined && context.signal !== null && !(context.signal instanceof AbortSignal)) throw error('MCP_CALL_FAILED')
        if (context.signal?.aborted) throw error('MCP_CALL_FAILED')
        validateSchema(config.inputSchema, inputs)
        const nativeContext = freeze(clone({ runId: context.runId, stepId: context.stepId, sourceDigest: context.sourceDigest }))
        if (![nativeContext.runId, nativeContext.stepId, nativeContext.sourceDigest].every(safeString)) throw error('MCP_CALL_FAILED')
        const argumentsValue = config.mapInputs
          ? await config.mapInputs(clone(inputs), nativeContext) : clone(inputs)
        const argumentsClone = clone(argumentsValue)
        if (!plain(argumentsClone) || context.signal?.aborted) throw error('MCP_CALL_FAILED')
        const raw = await call({ connectionRef, tool: config.tool, arguments: argumentsClone,
          signal: context.signal, context: nativeContext })
        // MCP application errors must not be mapped into successful evidence.
        if (context.signal?.aborted || raw?.isError === true) throw error('MCP_CALL_FAILED')
        const normalized = clone(await config.mapResult(raw, nativeContext))
        if (context.signal?.aborted || !plain(normalized)
            || Object.keys(normalized).some(key => !['data', 'mutationState'].includes(key))
            || !Object.hasOwn(normalized, 'data') || !MUTATION_STATES.has(normalized.mutationState)) throw error('MCP_CALL_FAILED')
        validateSchema(config.resultSchema, normalized.data)
        return normalized
      } catch { throw error('MCP_CALL_FAILED') }
    },
  }
}
