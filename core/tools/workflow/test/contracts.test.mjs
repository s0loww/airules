import test from 'node:test'
import assert from 'node:assert/strict'
import { canonical, digest, validateSchema, validateWorkflow, validateDescriptor } from '../lib/contracts.mjs'

test('canonical hashes data deterministically, never JSON-coerces executable values', () => {
  assert.equal(canonical({ z: [2, { b: true, a: null }], a: 'я' }), '{"a":"я","z":[2,{"a":null,"b":true}]}')
  assert.equal(digest({ a: 1, b: 2 }), digest({ b: 2, a: 1 }))
  assert.notEqual(digest({ a: 1 }), digest({ a: 2 }))
  const cyclic = {}; cyclic.a = cyclic
  let getterCalled = false
  const getter = Object.defineProperty({}, 'x', { enumerable: true, get() { getterCalled = true; return 1 } })
  for (const value of [undefined, NaN, Infinity, () => 1, Symbol('x'), 2n, new Date(), cyclic, getter, [undefined], new Array(1), JSON.parse('{"__proto__":{}}'), { constructor: 'x' }]) {
    assert.throws(() => canonical(value))
  }
  assert.equal(getterCalled, false)
  const shared = { a: 1 }
  assert.equal(canonical([shared, shared]), '[{"a":1},{"a":1}]')
})

test('schema subset validates nested typed input, object policy and unicode bounds', () => {
  const schema = { type: 'object', required: ['name', 'items'], additionalProperties: false, properties: {
    name: { type: 'string', minLength: 1, maxLength: 2 },
    items: { type: 'array', minItems: 1, maxItems: 2, uniqueItems: true, items: { type: 'integer', minimum: 0, maximum: 3 } },
  } }
  assert.doesNotThrow(() => validateSchema(schema, { name: '😀', items: [1, 2] }))
  for (const input of [{ name: 'a' }, { name: 'abc', items: [1] }, { name: 'a', items: [1, 1] }, { name: 'a', items: [1.5] }, { name: 'a', items: [4] }, { name: 'a', items: [1], command: 'x' }]) {
    assert.throws(() => validateSchema(schema, input))
  }
  assert.doesNotThrow(() => validateSchema({ type: 'object', additionalProperties: { type: 'boolean' } }, { enabled: true }))
  assert.throws(() => validateSchema({ type: 'object', additionalProperties: { type: 'boolean' } }, { enabled: 'yes' }))
})

test('schema supports explicit unions, const/enum and rejects unknown schema semantics in every branch', () => {
  assert.doesNotThrow(() => validateSchema({ anyOf: [{ type: 'null' }, { type: 'number', minimum: -2 }] }, null))
  assert.throws(() => validateSchema({ anyOf: [{ type: 'null' }, { type: 'number', minimum: -2 }] }, -3))
  assert.doesNotThrow(() => validateSchema({ enum: [1, { a: 2 }] }, { a: 2 }))
  assert.throws(() => validateSchema({ const: { a: 1 } }, { a: 2 }))
  for (const schema of [
    { type: 'string', pattern: '(a+)+$' }, { type: 'array', contains: { type: 'string' } },
    { $ref: '#/x' }, { type: ['string', 'null'] }, { type: ['object'] }, { minimum: 1 }, { enum: [] },
    { type: 'array', minItems: 3, maxItems: 2 }, { type: 'number', minimum: '1' },
    { anyOf: [true, { type: 'string', format: 'uri' }] },
  ]) assert.throws(() => validateSchema(schema, null))
  assert.throws(() => validateSchema(false, {}))
  assert.doesNotThrow(() => validateSchema(true, {}))
})

const workflow = () => ({ schemaVersion: 1, id: 'sample', version: '1.0.0', steps: [
  { id: 'second', adapter: 'runner', operation: 'verify', dependsOn: ['first'] },
  { id: 'first', adapter: 'reader', operation: 'inspect' },
] })

test('workflow normalizes defaults, orders dependencies and does not mutate caller data', () => {
  const source = workflow(); const before = canonical(source)
  const result = validateWorkflow(source)
  assert.equal(canonical(source), before)
  assert.deepEqual(result.steps.map(step => step.id), ['first', 'second'])
  assert.deepEqual(result.steps[0], { id: 'first', adapter: 'reader', operation: 'inspect', dependsOn: [], inputs: {}, resources: [], required: true, timeoutMs: 300_000 })
})

test('workflow rejects ambiguous graphs, command injection fields and invalid limits', () => {
  const mutations = [
    value => { value.steps[1].id = 'second' },
    value => { value.steps[1].dependsOn = ['second'] },
    value => { value.steps[1].dependsOn = ['absent'] },
    value => { value.steps[1].dependsOn = ['first'] },
    value => { value.steps[0].argv = ['x'] },
    value => { value.steps[0].timeoutMs = 0 },
    value => { value.steps[0].required = 'false' },
    value => { value.steps[0].required = null },
    value => { value.steps[0].inputs = null },
    value => { value.steps[0].resources = ['base', 'base'] },
    value => { value.schemaVersion = 2 },
    value => { value.steps = [] },
  ]
  for (const mutate of mutations) { const source = workflow(); mutate(source); assert.throws(() => validateWorkflow(source)) }
})

const descriptor = () => ({ protocolVersion: 1, id: 'runner', version: '1.0.0', operations: {
  verify: { inputSchema: { type: 'object', additionalProperties: false }, resultSchema: { type: 'object' }, effects: ['readsSource'], validator: 'structured', resourcesRequired: false },
} })

test('descriptor requires reviewed operation contracts, rejects hidden semantics and unknown protocols', () => {
  const source = descriptor()
  assert.deepEqual(validateDescriptor(source), source)
  for (const mutate of [
    value => { value.protocolVersion = 2 }, value => { value.operations.verify.shell = true },
    value => { value.operations.verify.effects = ['safe'] },
    value => { value.operations.verify.inputSchema = { type: 'string', pattern: '.*' } },
    value => { delete value.operations.verify.validator },
    value => { value.operations = {} },
    value => { value.operations.verify.effects = ['readsSource', 'readsSource'] },
  ]) { const value = descriptor(); mutate(value); assert.throws(() => validateDescriptor(value)) }
})
