import { constants } from 'node:fs'
import { lstat, realpath, mkdir, open, readFile } from 'node:fs/promises'
import { isAbsolute, win32, resolve, join } from 'node:path'
import { createHash } from 'node:crypto'
import { createLocalProcessAdapter, PROCESS_RESULT_SCHEMA } from './local-process.mjs'
import { validateDescriptor, validateSchema, digest } from './contracts.mjs'

const LIMIT = 1024 * 1024
const safeFailure = code => new Error(code)
const samePath = (a, b) => process.platform === 'win32' ? a.toLowerCase() === b.toLowerCase() : a === b
const sameFile = (a, b) => a.dev === b.dev && a.ino === b.ino && a.size === b.size && a.mtimeMs === b.mtimeMs

/** A trusted executable writes one JSON report into the unique run artifact directory. */
export function createReportProcessAdapter({ id, version = '1.0.0', operations, fingerprintPaths = [] }) {
  const registered = new Map(), baseOperations = Object.create(null), publicOperations = Object.create(null)
  if (!operations || typeof operations !== 'object' || Array.isArray(operations)) throw safeFailure('PROCESS_REPORT_REGISTRATION_INVALID')
  for (const [name, config] of Object.entries(operations)) {
    const parts = reportParts(config?.reportPath)
    if (config?.resultSchema?.type !== 'object' ||
        !['runId', 'sourceDigest'].every(key => config.resultSchema.required?.includes(key) && config.resultSchema.properties?.[key]?.type === 'string')) {
      throw safeFailure('PROCESS_REPORT_PROVENANCE_SCHEMA_REQUIRED')
    }
    const resultSchema = structuredClone(config.resultSchema)
    registered.set(name, { parts, resultSchema, inputSchema: structuredClone(config.inputSchema) })
    baseOperations[name] = { ...config, resultSchema: PROCESS_RESULT_SCHEMA, validator: 'process-exit',
      fingerprintPaths: [...fingerprintPaths, ...(config.fingerprintPaths ?? [])] }
    publicOperations[name] = { inputSchema: structuredClone(config.inputSchema), resultSchema,
      effects: [...config.effects], validator: config.validator,
      ...(config.resourcesRequired === undefined ? {} : { resourcesRequired: config.resourcesRequired }) }
  }
  const descriptor = validateDescriptor({ protocolVersion: 1, id, version, operations: publicOperations })
  const base = createLocalProcessAdapter({ id, version, operations: baseOperations })
  return {
    descriptor: freeze(descriptor),
    async fingerprint() {
      const moduleHash = createHash('sha256').update(await readFile(new URL(import.meta.url))).digest('hex')
      return digest({ base: await base.fingerprint(), descriptor, moduleHash,
        reports: [...registered].map(([name, config]) => [name, config.parts.join('/')]) })
    },
    async execute(operation, inputs, context = {}) {
      const config = registered.get(operation)
      if (!config) throw safeFailure('PROCESS_REPORT_OPERATION_UNKNOWN')
      if (typeof context.runId !== 'string' || !context.runId || typeof context.sourceDigest !== 'string' || !context.sourceDigest) {
        throw safeFailure('PROCESS_REPORT_PROVENANCE_REQUIRED')
      }
      try {
        validateSchema(config.inputSchema, inputs)
        const root = await artifactRoot(context.artifactDir)
        const report = await safeReportPath(root, config.parts, true)
        try { await lstat(report); throw safeFailure('PROCESS_REPORT_PREEXISTING') }
        catch (error) { if (error.code !== 'ENOENT') throw error }
        const processResult = await base.execute(operation, inputs, context)
        const process = processResult.data
        if (process.exitCode !== 0 || process.signal !== null || process.startError !== null ||
            process.timedOut || process.aborted || process.outputLimitExceeded || process.terminationConfirmed !== true) {
          throw safeFailure('PROCESS_REPORT_EXECUTION_FAILED')
        }
        const data = await readFreshReport(root, config.parts)
        validateSchema(config.resultSchema, data)
        if (data.runId !== context.runId || data.sourceDigest !== context.sourceDigest) throw safeFailure('PROCESS_REPORT_PROVENANCE_MISMATCH')
        return { data, mutationState: processResult.mutationState }
      } catch (error) {
        if (typeof error?.message === 'string' && /^PROCESS_REPORT_[A-Z_]+$/u.test(error.message)) throw error
        // File contents, arguments and operating-system diagnostics may contain credentials.
        throw safeFailure('PROCESS_REPORT_INVALID')
      }
    },
  }
}

function reportParts(value) {
  if (typeof value !== 'string' || !value || value.length > 1024 || value.includes('\0') || isAbsolute(value) || win32.isAbsolute(value)) {
    throw safeFailure('PROCESS_REPORT_PATH_INVALID')
  }
  const parts = value.split(/[\\/]/u)
  if (parts.some(part => !part || part === '.' || part === '..' || /[:<>"|?*]/u.test(part) || /[. ]$/u.test(part))) {
    throw safeFailure('PROCESS_REPORT_PATH_INVALID')
  }
  return parts
}

async function artifactRoot(path) {
  if (typeof path !== 'string' || !isAbsolute(path)) throw safeFailure('PROCESS_REPORT_ARTIFACT_DIRECTORY_INVALID')
  const info = await lstat(path)
  if (!info.isDirectory() || info.isSymbolicLink()) throw safeFailure('PROCESS_REPORT_ARTIFACT_DIRECTORY_INVALID')
  const actual = await realpath(path)
  if (!samePath(actual, resolve(path))) throw safeFailure('PROCESS_REPORT_ARTIFACT_DIRECTORY_INVALID')
  return actual
}

async function safeReportPath(root, parts, createParents) {
  await artifactRoot(root)
  let current = root
  for (const part of parts.slice(0, -1)) {
    current = join(current, part)
    let info
    try { info = await lstat(current) }
    catch (error) {
      if (error.code !== 'ENOENT' || !createParents) throw error
      await mkdir(current)
      info = await lstat(current)
    }
    if (!info.isDirectory() || info.isSymbolicLink() || !samePath(await realpath(current), current)) throw safeFailure('PROCESS_REPORT_PATH_INVALID')
  }
  return join(current, parts.at(-1))
}

async function readFreshReport(root, parts) {
  const path = await safeReportPath(root, parts, false)
  const before = await lstat(path)
  if (!before.isFile() || before.isSymbolicLink() || before.nlink !== 1 || before.size > LIMIT || !samePath(await realpath(path), path)) {
    throw safeFailure('PROCESS_REPORT_FILE_INVALID')
  }
  const handle = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0))
  try {
    const initial = await handle.stat()
    if (!sameFile(before, initial)) throw safeFailure('PROCESS_REPORT_FILE_CHANGED')
    const bytes = Buffer.alloc(initial.size + 1)
    let used = 0
    while (used < bytes.length) {
      const { bytesRead } = await handle.read(bytes, used, bytes.length - used, used)
      if (!bytesRead) break
      used += bytesRead
    }
    const after = await handle.stat()
    const currentPath = await safeReportPath(root, parts, false)
    const current = await lstat(currentPath)
    if (used !== initial.size || after.nlink !== 1 || current.nlink !== 1 || !sameFile(initial, after) || !sameFile(after, current) || current.isSymbolicLink() || !samePath(await realpath(currentPath), path)) {
      throw safeFailure('PROCESS_REPORT_FILE_CHANGED')
    }
    // TextDecoder fatal avoids silently turning invalid UTF-8 into different source text.
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, used))
    return JSON.parse(text)
  } finally { await handle.close() }
}

function freeze(value) {
  if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value) }
  return value
}
