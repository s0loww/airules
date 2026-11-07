import { spawn, execFile } from 'node:child_process'
import { isAbsolute, join } from 'node:path'
import { realpath, stat, readFile } from 'node:fs/promises'
import { createReadStream } from 'node:fs'
import { createHash } from 'node:crypto'
import { validateSchema, validateDescriptor, digest } from './contracts.mjs'

const OUTPUT_LIMIT = 1024 * 1024
const STOP_DEADLINE = 10000
const MAX_TIMEOUT = 3600000
const MUTATING = new Set(['writesFilesystem', 'writesTargetData', 'changesMetadata', 'serviceLifecycle', 'externalIO', 'destructiveRecovery'])

export const PROCESS_RESULT_SCHEMA = Object.freeze({
  type: 'object', additionalProperties: false,
  required: ['exitCode', 'signal', 'timedOut', 'aborted', 'outputLimitExceeded', 'stdoutBytes', 'stderrBytes', 'startError', 'terminationConfirmed'],
  properties: {
    exitCode: { anyOf: [{ type: 'integer' }, { type: 'null' }] },
    signal: { anyOf: [{ type: 'string' }, { type: 'null' }] },
    timedOut: { type: 'boolean' }, aborted: { type: 'boolean' },
    outputLimitExceeded: { type: 'boolean' }, terminationConfirmed: { type: 'boolean' },
    stdoutBytes: { type: 'integer', minimum: 0 }, stderrBytes: { type: 'integer', minimum: 0 },
    startError: { anyOf: [{ type: 'string' }, { type: 'null' }] },
  },
})

function abortResult() {
  return { data: { exitCode: null, signal: null, timedOut: false, aborted: true,
    outputLimitExceeded: false, stdoutBytes: 0, stderrBytes: 0,
    startError: null, terminationConfirmed: true }, mutationState: 'not-applied' }
}

/** Trusted host configuration only: command/argument builders never come from a workflow. */
export function createLocalProcessAdapter({ id, version = '1.0.0', operations }) {
  if (typeof id !== 'string' || !id || typeof version !== 'string' || !version ||
      !operations || typeof operations !== 'object' || Array.isArray(operations)) throw new Error('Invalid process adapter registration')
  const registered = new Map()
  const described = Object.create(null)
  for (const [name, config] of Object.entries(operations)) {
    if (!name || !config || typeof config.command !== 'string' || !isAbsolute(config.command) ||
        config.command.includes('\0') || typeof config.args !== 'function' ||
        !config.inputSchema || !Array.isArray(config.effects) || typeof config.validator !== 'string') {
      throw new Error('Process operation must have a fixed executable and declared contracts')
    }
    const inputSchema = structuredClone(config.inputSchema)
    const resultSchema = structuredClone(config.resultSchema ?? PROCESS_RESULT_SCHEMA)
    const effects = [...config.effects]
    const fingerprintPaths = [...(config.fingerprintPaths ?? [])]
    if (fingerprintPaths.some(path => typeof path !== 'string' || !isAbsolute(path))) throw new Error('Fingerprint files must be absolute paths')
    registered.set(name, { command: config.command, args: config.args, inputSchema, resultSchema, effects, fingerprintPaths })
    described[name] = { inputSchema: structuredClone(inputSchema), resultSchema: structuredClone(resultSchema),
      effects: [...effects], validator: config.validator,
      ...(config.resourcesRequired === undefined ? {} : { resourcesRequired: config.resourcesRequired }) }
  }
  if (!registered.size) throw new Error('Process adapter has no operations')
  const descriptor = validateDescriptor({ protocolVersion: 1, id, version, operations: described })
  return {
    descriptor: freeze(descriptor),
    async fingerprint() {
      const moduleHash = createHash('sha256').update(await readFile(new URL(import.meta.url))).digest('hex')
      const files = new Map()
      for (const config of registered.values()) {
        for (const path of [config.command, ...config.fingerprintPaths]) {
          if (!files.has(path)) files.set(path, await fingerprintFile(path))
        }
      }
      return digest({ id, version, moduleHash, descriptor: described, files: [...files.entries()].sort(([a], [b]) => a.localeCompare(b)),
        builders: [...registered.entries()].map(([name, config]) => [name, config.args.toString()]) })
    },
    async execute(operation, inputs, context = {}) {
      const config = registered.get(operation)
      if (!config) throw new Error('Process operation is not registered')
      validateSchema(config.inputSchema, inputs)
      if (context.signal !== undefined && context.signal !== null && !(context.signal instanceof AbortSignal)) {
        throw new Error('Process cancellation requires an AbortSignal')
      }
      if (!Number.isInteger(context.timeoutMs) || context.timeoutMs < 100 || context.timeoutMs > MAX_TIMEOUT) {
        throw new Error('A bounded process timeout is required')
      }
      if (typeof context.cwd !== 'string' || !isAbsolute(context.cwd) || !(await stat(context.cwd)).isDirectory()) {
        throw new Error('Process working directory must be an existing absolute directory')
      }
      if (context.signal?.aborted) return abortResult()
      const command = await realpath(config.command)
      if (!(await stat(command)).isFile()) throw new Error('Registered executable is not a file')
      // Node cannot start batch files without a command interpreter. Do not silently add one.
      if (process.platform === 'win32' && /\.(?:cmd|bat)$/iu.test(command)) throw new Error('Batch executables require an explicit trusted interpreter adapter')
      const args = config.args(structuredClone(inputs), context)
      if (!Array.isArray(args) || args.some(value => typeof value !== 'string' || value.includes('\0'))) {
        throw new Error('Process arguments must be an array of strings without null bytes')
      }
      if (context.signal?.aborted) return abortResult()
      return runProcess(command, args, context, config.effects)
    },
  }
}

function freeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze)
    Object.freeze(value)
  }
  return value
}

function runProcess(command, args, context, effects) {
  return new Promise(resolve => {
    let child
    let spawned = false
    let settled = false
    let stopping = false
    let closed = false
    let treeKillPending = false
    let treeKillConfirmed = true
    let timer
    let stopTimer
    const data = { exitCode: null, signal: null, timedOut: false, aborted: false,
      outputLimitExceeded: false, stdoutBytes: 0, stderrBytes: 0,
      startError: null, terminationConfirmed: false }
    const mutating = effects.some(effect => MUTATING.has(effect))
    const finish = confirmed => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      clearTimeout(stopTimer)
      context.signal?.removeEventListener('abort', onAbort)
      data.terminationConfirmed = confirmed
      if (!confirmed) {
        // Leave the state indeterminate; never imply that a timeout means the job stopped.
        child?.stdout?.destroy()
        child?.stderr?.destroy()
        child?.unref()
      }
      resolve({ data, mutationState: spawned && mutating ? 'unknown' : 'not-applied' })
    }
    const stop = () => {
      if (stopping || settled) return
      stopping = true
      clearTimeout(stopTimer)
      stopTimer = setTimeout(() => finish(false), STOP_DEADLINE)
      if (!child?.pid || child.exitCode !== null || child.signalCode !== null) return
      if (process.platform === 'win32') {
        const systemRoot = process.env.SystemRoot
        if (!systemRoot || !isAbsolute(systemRoot)) return
        // The PID is exclusively the child just spawned by this adapter, never caller input.
        treeKillPending = true
        execFile(join(systemRoot, 'System32', 'taskkill.exe'), ['/PID', String(child.pid), '/T', '/F'],
          { windowsHide: true, timeout: STOP_DEADLINE - 1000, maxBuffer: 65536 }, error => {
            treeKillPending = false
            treeKillConfirmed = !error
            if (closed) finish(treeKillConfirmed)
          })
      } else {
        try { process.kill(-child.pid, 'SIGKILL') } catch (error) {
          if (error.code !== 'ESRCH') return
        }
      }
    }
    const onAbort = () => { data.aborted = true; stop() }
    try {
      child = spawn(command, args, { cwd: context.cwd, shell: false, windowsHide: true,
        detached: process.platform !== 'win32', stdio: ['ignore', 'pipe', 'pipe'] })
    } catch (error) {
      data.startError = safeErrorCode(error)
      finish(true)
      return
    }
    child.once('spawn', () => { spawned = true; if (stopping) { stopping = false; stop() } })
    child.once('error', error => { data.startError = safeErrorCode(error) })
    child.once('close', (code, signal) => {
      data.exitCode = code
      data.signal = signal
      closed = true
      if (!treeKillPending) finish(treeKillConfirmed)
    })
    for (const [stream, counter] of [[child.stdout, 'stdoutBytes'], [child.stderr, 'stderrBytes']]) {
      stream.on('data', chunk => {
        data[counter] = Math.min(Number.MAX_SAFE_INTEGER, data[counter] + chunk.length)
        if (data[counter] > OUTPUT_LIMIT) { data.outputLimitExceeded = true; stop() }
      })
    }
    context.signal?.addEventListener('abort', onAbort, { once: true })
    timer = setTimeout(() => { data.timedOut = true; stop() }, context.timeoutMs)
    if (context.signal?.aborted) onAbort()
  })
}

function safeErrorCode(error) {
  return typeof error?.code === 'string' && /^[A-Z0-9_]{1,32}$/u.test(error.code) ? error.code : 'START_FAILED'
}

async function fingerprintFile(path) {
  const resolved = await realpath(path)
  const before = await stat(resolved)
  if (!before.isFile() || before.size > 1024 * 1024 * 1024) throw new Error('Fingerprint input is not a bounded regular file')
  const hash = createHash('sha256')
  for await (const chunk of createReadStream(resolved)) hash.update(chunk)
  const after = await stat(resolved)
  if (before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ino !== after.ino) {
    throw new Error('Fingerprint input changed while being read')
  }
  return { identity: resolved, sha256: hash.digest('hex') }
}
