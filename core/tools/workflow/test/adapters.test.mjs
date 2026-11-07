import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { setTimeout as delay } from 'node:timers/promises'
import { createLocalProcessAdapter, PROCESS_RESULT_SCHEMA } from '../lib/local-process.mjs'
import { validateEvidence } from '../lib/validators.mjs'

const emptySchema = { type: 'object', properties: {}, additionalProperties: false }
function adapter(script, extras = {}) {
  return createLocalProcessAdapter({ id: 'local-fixture', operations: { inspect: {
    command: process.execPath, args: () => ['-e', script], inputSchema: emptySchema,
    resultSchema: PROCESS_RESULT_SCHEMA, effects: ['startsProcess'], validator: 'process-exit', ...extras,
  } } })
}
async function fixture(t) {
  const cwd = await mkdtemp(join(tmpdir(), 'workflow-adapter-'))
  t.after(() => rm(cwd, { recursive: true, force: true }))
  return { cwd, runId: 'run-fixture', stepId: 'inspect', timeoutMs: 3000 }
}

test('process execution returns only metadata and does not expose argv or secret output', async t => {
  const context = await fixture(t)
  const secret = 'fixture-output-must-not-be-recorded' // airules:allow creds-token — synthetic redaction fixture
  const local = adapter(`process.stdout.write(${JSON.stringify(secret)}); process.stderr.write('private-error')`)
  const result = await local.execute('inspect', {}, context)
  assert.equal(result.data.exitCode, 0)
  assert.equal(result.data.stdoutBytes, Buffer.byteLength(secret))
  assert.equal(result.data.stderrBytes, Buffer.byteLength('private-error'))
  assert.equal(result.data.terminationConfirmed, true)
  assert.equal(result.mutationState, 'not-applied')
  assert.doesNotMatch(JSON.stringify(result), /fixture-output-must-not-be-recorded|private-error|process\.stdout/)
  assert.doesNotMatch(JSON.stringify(local.descriptor), /command|args|node\.exe/)
  assert.equal(validateEvidence('process-exit', result.data).status, 'passed')
})

test('fixed executable receives literal arguments without a shell', async t => {
  const context = await fixture(t)
  const path = join(context.cwd, 'literal.json')
  const scriptPath = join(context.cwd, 'literal.mjs')
  await writeFile(scriptPath, "import {writeFileSync} from 'node:fs';writeFileSync(process.argv[2],JSON.stringify(process.argv.slice(3)))")
  const values = ['Unicode_кот', '$(not-a-command)', 'a; b && c', 'quote"and space']
  const local = adapter('', { args: () => [scriptPath, path, ...values] })
  const result = await local.execute('inspect', {}, context)
  assert.equal(result.data.exitCode, 0)
  assert.deepEqual(JSON.parse(await readFile(path, 'utf8')), values)
})

test('adapter fingerprint changes with registered runner content without exposing it', async t => {
  const context = await fixture(t)
  const runner = join(context.cwd, 'runner.mjs')
  await writeFile(runner, 'process.exit(0)')
  const local = adapter('', { args: () => [runner], fingerprintPaths: [runner] })
  const before = await local.fingerprint()
  assert.match(before, /^[a-f0-9]{64}$/)
  assert.equal(await local.fingerprint(), before)
  await writeFile(runner, 'process.exit(1)')
  assert.notEqual(await local.fingerprint(), before)
})

test('undeclared arguments, operations and unbounded timeouts are rejected before launch', async t => {
  const context = await fixture(t)
  let invoked = false
  const local = adapter('', { args: () => { invoked = true; return ['-e', ''] } })
  await assert.rejects(local.execute('missing', {}, context), /not registered/)
  await assert.rejects(local.execute('inspect', { command: 'arbitrary' }, context))
  await assert.rejects(local.execute('inspect', {}, { ...context, timeoutMs: 0 }), /bounded/)
  await assert.rejects(local.execute('inspect', {}, { ...context, signal: { aborted: false } }), /AbortSignal/)
  assert.equal(invoked, false)
  await assert.rejects(adapter('', { args: () => ['nul\0byte'] }).execute('inspect', {}, context), /null bytes/)
  assert.throws(() => adapter('', { command: 'relative-executable' }), /fixed executable/)
  assert.throws(() => adapter('', { effects: ['undocumentedEffect'] }), /unsupported effect/)
})

test('nonzero exit cannot be accepted as a passing process check', async t => {
  const result = await adapter('process.exit(7)').execute('inspect', {}, await fixture(t))
  assert.equal(result.data.exitCode, 7)
  assert.equal(validateEvidence('process-exit', result.data).status, 'failed')
})

test('timeout terminates the owned long-running process and reports failure', async t => {
  const context = await fixture(t)
  const result = await adapter('setInterval(()=>{},1000)').execute('inspect', {}, { ...context, timeoutMs: 150 })
  assert.equal(result.data.timedOut, true)
  assert.equal(result.data.terminationConfirmed, true)
  assert.equal(validateEvidence('process-exit', result.data).status, 'failed')
})

test('pre-aborted execution does not invoke the argument builder or start a process', async t => {
  const context = await fixture(t)
  const controller = new AbortController()
  controller.abort()
  let invoked = false
  const result = await adapter('', { args: () => { invoked = true; return [] } }).execute('inspect', {}, { ...context, signal: controller.signal })
  assert.equal(invoked, false)
  assert.equal(result.data.aborted, true)
  assert.equal(result.data.terminationConfirmed, true)
  assert.equal(result.mutationState, 'not-applied')
})

test('active cancellation awaits owned process completion and retains mutation uncertainty', async t => {
  const context = await fixture(t)
  const controller = new AbortController()
  const active = adapter('setInterval(()=>{},1000)', { effects: ['startsProcess', 'changesMetadata'] })
  const timer = setTimeout(() => controller.abort(), 200)
  t.after(() => clearTimeout(timer))
  const result = await active.execute('inspect', {}, { ...context, signal: controller.signal })
  assert.equal(result.data.aborted, true)
  assert.equal(result.data.terminationConfirmed, true)
  assert.equal(result.mutationState, 'unknown')
})

test('cancellation terminates a child created by the owned runner', async t => {
  const context = await fixture(t)
  const pidFile = join(context.cwd, 'owned-child.pid')
  const runner = join(context.cwd, 'tree.cjs')
  await writeFile(runner, "const {spawn}=require('node:child_process');const {writeFileSync}=require('node:fs');const c=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:'inherit',windowsHide:true});writeFileSync(process.argv[2],String(c.pid));setInterval(()=>{},1000)")
  const controller = new AbortController()
  const active = adapter('', { args: () => [runner, pidFile] }).execute('inspect', {}, { ...context, signal: controller.signal })
  let childPid
  for (let i = 0; i < 60; i++) {
    try { childPid = Number(await readFile(pidFile, 'utf8')); if (Number.isSafeInteger(childPid) && childPid > 0) break } catch {}
    await delay(25)
  }
  controller.abort()
  const result = await active
  assert.ok(Number.isSafeInteger(childPid) && childPid > 0, 'fixture child must have started')
  assert.equal(result.data.terminationConfirmed, true)
  let exists = true
  for (let i = 0; i < 40 && exists; i++) {
    try { process.kill(childPid, 0); await delay(25) } catch (error) { if (error.code === 'ESRCH') exists = false; else throw error }
  }
  assert.equal(exists, false, 'owned descendant must no longer be running')
})

test('zero exit is not proof of completed mutation', async t => {
  const result = await adapter('', { effects: ['writesTargetData'] }).execute('inspect', {}, await fixture(t))
  assert.equal(result.data.exitCode, 0)
  assert.equal(result.mutationState, 'unknown')
})

test('excessive child output is counted and stopped without retaining output', async t => {
  const result = await adapter("setInterval(()=>process.stdout.write('x'.repeat(65536)),0)").execute('inspect', {}, await fixture(t))
  assert.equal(result.data.outputLimitExceeded, true)
  assert.equal(result.data.terminationConfirmed, true)
  assert.ok(result.data.stdoutBytes > 1024 * 1024)
  assert.ok(JSON.stringify(result).length < 1000)
})

test('assertion evidence requires complete nonempty unique assertions and all required IDs', () => {
  assert.equal(validateEvidence('assertions', { complete: true, assertions: [] }).status, 'failed')
  assert.equal(validateEvidence('assertions', { complete: false, assertions: [{ id: 'one', passed: true }] }).status, 'indeterminate')
  assert.equal(validateEvidence('assertions', { complete: true, assertions: [{ id: 'one', passed: true }, { id: 'one', passed: true }] }).status, 'indeterminate')
  assert.equal(validateEvidence('assertions', { complete: true, assertions: [{ id: 'one', passed: 'true' }] }).status, 'indeterminate')
  const report = { complete: true, assertions: [{ id: 'one', passed: true }] }
  assert.equal(validateEvidence('assertions', report, { expectedAssertions: ['one', 'two'] }).status, 'failed')
  assert.equal(validateEvidence('assertions', report, { expectedAssertions: ['one'] }).status, 'passed')
  assert.equal(validateEvidence('assertions', { complete: true, assertions: [{ id: 'one', passed: false }] }).status, 'failed')
})

test('test summary rejects empty, stale, malformed, incomplete and all-skipped reports', () => {
  const context = { runId: 'current-run', sourceDigest: 'current-source' }
  const data = { tests: 2, failures: 0, errors: 0, skipped: 0, complete: true, ...context }
  assert.equal(validateEvidence('test-summary', data, context).status, 'passed')
  assert.equal(validateEvidence('test-summary', data).status, 'indeterminate')
  assert.equal(validateEvidence('test-summary', { ...data, runId: 'old' }, context).status, 'indeterminate')
  assert.equal(validateEvidence('test-summary', { ...data, complete: false }, context).status, 'indeterminate')
  assert.equal(validateEvidence('test-summary', { ...data, tests: 0 }, context).status, 'failed')
  assert.equal(validateEvidence('test-summary', { ...data, skipped: 2 }, context).status, 'failed')
  assert.equal(validateEvidence('test-summary', { ...data, failures: -1 }, context).status, 'indeterminate')
  assert.equal(validateEvidence('test-summary', { ...data, failures: 3 }, context).status, 'indeterminate')
  assert.equal(validateEvidence('test-summary', { ...data, errors: 1 }, context).status, 'failed')
  assert.equal(validateEvidence('unknown', data, context).status, 'indeterminate')
  assert.equal(validateEvidence('process-exit', { exitCode: 0, timedOut: 'false' }).status, 'indeterminate')
})
