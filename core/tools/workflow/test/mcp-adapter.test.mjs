import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { createMcpAdapter } from '../lib/mcp-adapter.mjs'

const inputSchema = { type: 'object', required: ['text'], additionalProperties: false, properties: { text: { type: 'string' } } }
const resultSchema = { type: 'object', required: ['complete', 'assertions'], additionalProperties: false, properties: {
  complete: { type: 'boolean' }, assertions: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['id', 'passed'], properties: { id: { type: 'string' }, passed: { type: 'boolean' } } } },
} }
const mapped = () => ({ data: { complete: true, assertions: [{ id: 'syntax', passed: true }] }, mutationState: 'not-applied' })
const context = signal => ({ runId: 'run-1', stepId: 'step-1', sourceDigest: 'a'.repeat(64), signal })
const registration = (overrides = {}) => ({ id: 'syntax-adapter', connectionRef: 'direct-syntax', connectionRevision: 'config-v1',
  operations: { check: { tool: 'validate', inputSchema, resultSchema, effects: ['readsSource'], validator: 'assertions', mapResult: mapped } },
  call: async () => ({ privateRaw: 'never returned' }), ...overrides })

test('direct providers and facade use the same adapter without discovery or implicit routing', async () => {
  const calls = []
  const caller = async value => { calls.push(value); return { transportSpecific: true } }
  for (const connectionRef of ['direct-syntax', 'project-qa', 'my-facade']) {
    const adapter = createMcpAdapter(registration({ connectionRef, call: caller }))
    const result = await adapter.execute('check', { text: 'value' }, context())
    assert.deepEqual(result, mapped())
    assert.equal(calls.at(-1).connectionRef, connectionRef)
    assert.equal(calls.at(-1).tool, 'validate')
    assert.deepEqual(calls.at(-1).arguments, { text: 'value' })
    assert.deepEqual(calls.at(-1).context, { runId: 'run-1', stepId: 'step-1', sourceDigest: 'a'.repeat(64) })
    assert.doesNotMatch(JSON.stringify(adapter.descriptor), /direct-syntax|project-qa|my-facade|privateRaw|mapResult|connectionRevision/u)
  }
  assert.equal(calls.length, 3)
})

test('fingerprinting calls no native tools or mapping code and binds revision, tools, caller and trusted files', async () => {
  let invoked = 0
  const root = await mkdtemp(join(tmpdir(), 'workflow-mcp-'))
  try {
    const path = join(root, 'mapper-version.txt')
    await writeFile(path, 'v1')
    const config = registration({ fingerprintPaths: [path], call: async () => { invoked++; return {} } })
    config.operations.check.mapResult = () => { invoked++; return mapped() }
    config.operations.check.mapInputs = value => { invoked++; return value }
    const a = createMcpAdapter(config)
    const first = await a.fingerprint()
    assert.match(first, /^[a-f0-9]{64}$/u)
    assert.equal(await a.fingerprint(), first)
    assert.equal(invoked, 0)
    assert.notEqual(await createMcpAdapter({ ...config, connectionRevision: 'config-v2' }).fingerprint(), first)
    assert.notEqual(await createMcpAdapter({ ...config, connectionRef: 'another-provider' }).fingerprint(), first)
    assert.notEqual(await createMcpAdapter({ ...config, call: async () => null }).fingerprint(), first)
    const changedTool = registration({ ...config, operations: { check: { ...config.operations.check, tool: 'other-tool' } } })
    assert.notEqual(await createMcpAdapter(changedTool).fingerprint(), first)
    const changedMapper = registration({ ...config, operations: { check: { ...config.operations.check, mapResult: () => ({ data: {}, mutationState: 'unknown' }) } } })
    assert.notEqual(await createMcpAdapter(changedMapper).fingerprint(), first)
    await writeFile(path, 'v2')
    assert.notEqual(await a.fingerprint(), first)
    assert.equal(invoked, 0)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('registration rejects missing contracts, arbitrary fields and missing nonsecret revisions', () => {
  for (const mutate of [
    value => { value.connectionRevision = '' }, value => { value.connectionRef = 'https://unregistered' },
    value => { delete value.operations.check.mapResult }, value => { value.operations.check.mapInputs = 'code' },
    value => { value.operations.check.shell = 'cmd' }, value => { value.operations.check.effects = ['safe'] },
    value => { value.fingerprintPaths = ['relative-script.js'] },
  ]) {
    const value = registration(); mutate(value)
    assert.throws(() => createMcpAdapter(value), error => error.code === 'MCP_CONFIGURATION_INVALID' && !error.cause)
  }
})

test('typed input and explicit mapping are checked, caller results are normalized rather than exposed', async () => {
  let calls = 0
  const value = registration({ call: async () => { calls++; return { password: 'do-not-expose', answer: 12 } } }) // airules:allow creds-password — synthetic redaction fixture
  value.operations.check.mapInputs = inputs => ({ code: inputs.text })
  value.operations.check.mapResult = (raw, ctx) => ({ data: { complete: true, assertions: [{ id: ctx.stepId, passed: raw.answer === 12 }] }, mutationState: 'not-applied' })
  const adapter = createMcpAdapter(value)
  assert.deepEqual(await adapter.execute('check', { text: 'sample' }, context()), { data: { complete: true, assertions: [{ id: 'step-1', passed: true }] }, mutationState: 'not-applied' })
  await assert.rejects(adapter.execute('check', { text: 12 }, context()), error => error.code === 'MCP_CALL_FAILED')
  await assert.rejects(adapter.execute('unregistered', { text: 'sample' }, context()), error => error.code === 'MCP_CALL_FAILED')
  assert.equal(calls, 1)
})

test('invalid mappers and native errors emit only safe failure codes', async () => {
  const rawSecret = 'secret-test-value' // airules:allow creds-token — synthetic redaction fixture
  for (const mutate of [
    value => { value.call = async () => { throw new Error(rawSecret) } },
    value => { value.call = async () => ({ isError: true, content: [{ type: 'text', text: rawSecret }] }) },
    value => { value.operations.check.mapInputs = () => { throw new Error(rawSecret) } },
    value => { value.operations.check.mapInputs = () => ['not-object'] },
    value => { value.operations.check.mapResult = () => { throw new Error(rawSecret) } },
    value => { value.operations.check.mapResult = () => ({ data: { password: rawSecret }, mutationState: 'not-applied' }) }, // airules:allow creds-password — synthetic redaction fixture
    value => { value.operations.check.mapResult = () => ({ ...mapped(), raw: rawSecret }) },
    value => { value.operations.check.mapResult = () => ({ data: mapped().data }) },
  ]) {
    const value = registration(); mutate(value)
    await assert.rejects(createMcpAdapter(value).execute('check', { text: 'sample' }, context()), error => {
      assert.equal(error.code, 'MCP_CALL_FAILED'); assert.equal(error.message, 'MCP_CALL_FAILED')
      assert.equal(error.cause, undefined); assert.doesNotMatch(JSON.stringify(error), /secret-test-value/u)
      return true
    })
  }
})

test('pre-abort never calls native tool; post-call and post-mapping abort never return evidence', async () => {
  let calls = 0; let mappedCount = 0
  const before = new AbortController(); before.abort()
  const first = createMcpAdapter(registration({ call: async () => { calls++; return {} } }))
  await assert.rejects(first.execute('check', { text: 'sample' }, context(before.signal)), /MCP_CALL_FAILED/u)
  assert.equal(calls, 0)
  const during = new AbortController()
  const value = registration({ call: async () => { calls++; during.abort(); return {} } })
  value.operations.check.mapResult = () => { mappedCount++; return mapped() }
  await assert.rejects(createMcpAdapter(value).execute('check', { text: 'sample' }, context(during.signal)), /MCP_CALL_FAILED/u)
  assert.equal(mappedCount, 0)
  const after = new AbortController()
  const value2 = registration()
  value2.operations.check.mapResult = () => { after.abort(); return mapped() }
  await assert.rejects(createMcpAdapter(value2).execute('check', { text: 'sample' }, context(after.signal)), /MCP_CALL_FAILED/u)
})
