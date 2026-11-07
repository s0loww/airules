import { createHash } from 'node:crypto'

const FORBIDDEN_KEYS = new Set(['__proto__', 'prototype', 'constructor'])
const MAX_DEPTH = 64
const MAX_NODES = 100_000
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u
export const EFFECTS = Object.freeze([
  'readsSource', 'connectsTarget', 'startsProcess', 'writesFilesystem',
  'writesTargetData', 'changesMetadata', 'serviceLifecycle', 'externalIO',
  'destructiveRecovery',
])

function fail(path, message) { throw new Error(`${path}: ${message}`) }
function plain(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && [Object.prototype, null].includes(Object.getPrototypeOf(value))
}

/** Canonical JSON only: no coercion, getters, executable values or prototype keys. */
export function canonical(value) {
  const ancestors = new Set()
  let nodes = 0
  function visit(item, depth, path) {
    if (++nodes > MAX_NODES || depth > MAX_DEPTH) fail(path, 'JSON complexity limit exceeded')
    if (item === null || typeof item === 'string' || typeof item === 'boolean') return JSON.stringify(item)
    if (typeof item === 'number') {
      if (!Number.isFinite(item)) fail(path, 'non-finite number')
      return JSON.stringify(item)
    }
    if (typeof item !== 'object') fail(path, 'unsupported JSON value')
    if (ancestors.has(item)) fail(path, 'cyclic JSON')
    if (!Array.isArray(item) && !plain(item)) fail(path, 'non-plain object')
    if (Object.getOwnPropertySymbols(item).length) fail(path, 'symbol properties')
    ancestors.add(item)
    const keys = Object.getOwnPropertyNames(item)
    for (const key of keys) {
      if (Array.isArray(item) && key === 'length') continue
      if (FORBIDDEN_KEYS.has(key)) fail(path, 'forbidden property')
      const descriptor = Object.getOwnPropertyDescriptor(item, key)
      if (!descriptor.enumerable || !Object.hasOwn(descriptor, 'value')) fail(path, 'non-data property')
    }
    let output
    if (Array.isArray(item)) {
      if (keys.length !== item.length + 1) fail(path, 'sparse array or extra properties')
      const elements = []
      for (let i = 0; i < item.length; i++) {
        if (!Object.hasOwn(item, i)) fail(path, 'sparse array')
        elements.push(visit(item[i], depth + 1, `${path}[${i}]`))
      }
      output = `[${elements.join(',')}]`
    } else {
      output = `{${keys.sort().map(key => `${JSON.stringify(key)}:${visit(item[key], depth + 1, `${path}.${key}`)}`).join(',')}}`
    }
    ancestors.delete(item)
    return output
  }
  return visit(value, 0, '$')
}

export function digest(value) { return createHash('sha256').update(canonical(value), 'utf8').digest('hex') }
const clone = value => JSON.parse(canonical(value))

const COMMON = new Set(['$schema', 'title', 'description', 'type', 'enum', 'const', 'anyOf'])
const TYPES = {
  object: ['properties', 'required', 'additionalProperties'],
  array: ['items', 'minItems', 'maxItems', 'uniqueItems'],
  string: ['minLength', 'maxLength'],
  number: ['minimum', 'maximum'],
  integer: ['minimum', 'maximum'],
  boolean: [], null: [],
}

function bound(schema, key, path, { integer = true, minimum = 0 } = {}) {
  if (!Object.hasOwn(schema, key)) return
  const value = schema[key]
  if (typeof value !== 'number' || !Number.isFinite(value) || (integer && !Number.isSafeInteger(value)) || value < minimum) {
    fail(path, `invalid ${key}`)
  }
}

/** This is an explicit JSON Schema subset, not a permissive full-schema validator. */
function checkSchema(schema, path = '$schema', depth = 0) {
  if (depth > MAX_DEPTH) fail(path, 'schema depth limit exceeded')
  if (typeof schema === 'boolean') return
  if (!plain(schema)) fail(path, 'schema must be an object or boolean')
  const type = schema.type
  if (type !== undefined && (typeof type !== 'string' || !Object.hasOwn(TYPES, type))) fail(path, 'unsupported schema type')
  const allowed = new Set([...COMMON, ...(TYPES[type] ?? [])])
  for (const key of Object.keys(schema)) if (!allowed.has(key)) fail(path, `unsupported schema keyword ${key}`)
  for (const key of ['$schema', 'title', 'description']) {
    if (Object.hasOwn(schema, key) && typeof schema[key] !== 'string') fail(path, `invalid ${key}`)
  }
  if (Object.hasOwn(schema, '$schema') && schema.$schema !== 'https://json-schema.org/draft/2020-12/schema') {
    fail(path, 'unsupported schema dialect')
  }
  if (Object.hasOwn(schema, 'enum')) {
    if (!Array.isArray(schema.enum) || !schema.enum.length) fail(path, 'enum must be nonempty')
    if (new Set(schema.enum.map(canonical)).size !== schema.enum.length) fail(path, 'duplicate enum values')
  }
  if (Object.hasOwn(schema, 'anyOf')) {
    if (!Array.isArray(schema.anyOf) || !schema.anyOf.length) fail(path, 'anyOf must be nonempty')
    for (const [i, branch] of schema.anyOf.entries()) checkSchema(branch, `${path}.anyOf[${i}]`, depth + 1)
  }
  if (type === 'object') {
    if (Object.hasOwn(schema, 'properties')) {
      if (!plain(schema.properties)) fail(path, 'properties must be an object')
      for (const [key, child] of Object.entries(schema.properties)) checkSchema(child, `${path}.properties.${key}`, depth + 1)
    }
    if (Object.hasOwn(schema, 'required')) {
      if (!Array.isArray(schema.required) || schema.required.some(key => typeof key !== 'string')
          || new Set(schema.required).size !== schema.required.length) fail(path, 'invalid required')
    }
    if (Object.hasOwn(schema, 'additionalProperties')) checkSchema(schema.additionalProperties, `${path}.additionalProperties`, depth + 1)
  }
  if (type === 'array') {
    if (Object.hasOwn(schema, 'items')) checkSchema(schema.items, `${path}.items`, depth + 1)
    bound(schema, 'minItems', path); bound(schema, 'maxItems', path)
    if ((schema.minItems ?? 0) > (schema.maxItems ?? Infinity)) fail(path, 'inverted item bounds')
    if (Object.hasOwn(schema, 'uniqueItems') && typeof schema.uniqueItems !== 'boolean') fail(path, 'invalid uniqueItems')
  }
  if (type === 'string') {
    bound(schema, 'minLength', path); bound(schema, 'maxLength', path)
    if ((schema.minLength ?? 0) > (schema.maxLength ?? Infinity)) fail(path, 'inverted string bounds')
  }
  if (type === 'number' || type === 'integer') {
    bound(schema, 'minimum', path, { integer: false, minimum: -Infinity })
    bound(schema, 'maximum', path, { integer: false, minimum: -Infinity })
    if ((schema.minimum ?? -Infinity) > (schema.maximum ?? Infinity)) fail(path, 'inverted number bounds')
  }
}

function checkValue(schema, value, path = '$') {
  if (schema === true) return
  if (schema === false) fail(path, 'schema rejects value')
  const encoded = canonical(value)
  if (Object.hasOwn(schema, 'const') && encoded !== canonical(schema.const)) fail(path, 'const mismatch')
  if (schema.enum && !schema.enum.some(item => canonical(item) === encoded)) fail(path, 'enum mismatch')
  if (schema.anyOf) {
    let matches = false
    for (const branch of schema.anyOf) {
      try { checkValue(branch, value, path); matches = true; break } catch { /* branch rejection */ }
    }
    if (!matches) fail(path, 'no anyOf branch matched')
  }
  const type = schema.type
  if (type === undefined) return
  const typeOK = type === 'object' ? plain(value)
    : type === 'array' ? Array.isArray(value)
      : type === 'null' ? value === null
        : type === 'integer' ? Number.isSafeInteger(value)
          : typeof value === type
  if (!typeOK) fail(path, `expected ${type}`)
  if (type === 'object') {
    for (const key of schema.required ?? []) if (!Object.hasOwn(value, key)) fail(path, `missing required ${key}`)
    for (const [key, item] of Object.entries(value)) {
      if (Object.hasOwn(schema.properties ?? {}, key)) checkValue(schema.properties[key], item, `${path}.${key}`)
      else if (schema.additionalProperties === false) fail(path, `unknown property ${key}`)
      else if (typeof schema.additionalProperties === 'object') checkValue(schema.additionalProperties, item, `${path}.${key}`)
    }
  }
  if (type === 'array') {
    if (value.length < (schema.minItems ?? 0) || value.length > (schema.maxItems ?? Infinity)) fail(path, 'array length out of bounds')
    if (schema.uniqueItems && new Set(value.map(canonical)).size !== value.length) fail(path, 'duplicate items')
    if (Object.hasOwn(schema, 'items')) for (const [i, item] of value.entries()) checkValue(schema.items, item, `${path}[${i}]`)
  }
  if (type === 'string') {
    const length = [...value].length
    if (length < (schema.minLength ?? 0) || length > (schema.maxLength ?? Infinity)) fail(path, 'string length out of bounds')
  }
  if (type === 'number' || type === 'integer') {
    if (value < (schema.minimum ?? -Infinity) || value > (schema.maximum ?? Infinity)) fail(path, 'number out of bounds')
  }
}

export function validateSchema(schema, value) {
  canonical(schema); canonical(value)
  checkSchema(schema)
  checkValue(schema, value)
  return value
}

function objectKeys(value, allowed, required, path) {
  if (!plain(value)) fail(path, 'expected object')
  for (const key of Object.keys(value)) if (!allowed.includes(key)) fail(path, `unknown property ${key}`)
  for (const key of required) if (!Object.hasOwn(value, key)) fail(path, `missing required ${key}`)
}
function identifier(value, path) { if (typeof value !== 'string' || !ID.test(value)) fail(path, 'invalid identifier') }
function version(value, path) {
  if (typeof value !== 'string' || !value.length || value.length > 128) fail(path, 'invalid version')
}
function stringList(value, path, ids = false) {
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string' || !item.length)
      || new Set(value).size !== value.length) fail(path, 'expected unique strings')
  if (ids) for (const item of value) identifier(item, path)
}

/** Normalize defaults and sort the DAG; caller input is never mutated. */
export function validateWorkflow(input) {
  const workflow = clone(input)
  objectKeys(workflow, ['schemaVersion', 'id', 'version', 'steps'], ['schemaVersion', 'id', 'version', 'steps'], '$workflow')
  if (workflow.schemaVersion !== 1) fail('$workflow', 'unsupported schemaVersion')
  identifier(workflow.id, '$workflow.id'); version(workflow.version, '$workflow.version')
  if (!Array.isArray(workflow.steps) || !workflow.steps.length || workflow.steps.length > 1024) fail('$workflow.steps', 'expected 1..1024 steps')
  const steps = new Map()
  for (const step of workflow.steps) {
    objectKeys(step, ['id', 'adapter', 'operation', 'dependsOn', 'inputs', 'resources', 'required', 'timeoutMs'], ['id', 'adapter', 'operation'], '$step')
    for (const key of ['id', 'adapter', 'operation']) identifier(step[key], `$step.${key}`)
    if (steps.has(step.id)) fail('$workflow', 'duplicate step id')
    for (const [key, value] of Object.entries({ dependsOn: [], inputs: {}, resources: [], required: true, timeoutMs: 300_000 })) {
      if (!Object.hasOwn(step, key)) step[key] = value
    }
    stringList(step.dependsOn, '$step.dependsOn', true); stringList(step.resources, '$step.resources', true)
    if (!plain(step.inputs)) fail('$step.inputs', 'expected object')
    if (typeof step.required !== 'boolean') fail('$step.required', 'expected boolean')
    if (!Number.isSafeInteger(step.timeoutMs) || step.timeoutMs < 100 || step.timeoutMs > 3_600_000) fail('$step.timeoutMs', 'expected 100..3600000 milliseconds')
    steps.set(step.id, step)
  }
  for (const step of steps.values()) {
    for (const dependency of step.dependsOn) {
      if (!steps.has(dependency)) fail('$workflow', 'missing dependency')
      if (dependency === step.id) fail('$workflow', 'self dependency')
    }
  }
  const ordered = []; const remaining = new Map(steps); const emitted = new Set()
  while (remaining.size) {
    let progress = false
    for (const [id, step] of remaining) {
      if (!step.dependsOn.every(dependency => emitted.has(dependency))) continue
      ordered.push(step); emitted.add(id); remaining.delete(id); progress = true
    }
    if (!progress) fail('$workflow', 'dependency cycle')
  }
  return { ...workflow, steps: ordered }
}

/** Descriptor data is not executable registration or authorization. */
export function validateDescriptor(input) {
  const descriptor = clone(input)
  objectKeys(descriptor, ['protocolVersion', 'id', 'version', 'operations'], ['protocolVersion', 'id', 'version', 'operations'], '$descriptor')
  if (descriptor.protocolVersion !== 1) fail('$descriptor', 'unsupported protocolVersion')
  identifier(descriptor.id, '$descriptor.id'); version(descriptor.version, '$descriptor.version')
  if (!plain(descriptor.operations) || !Object.keys(descriptor.operations).length) fail('$descriptor.operations', 'expected nonempty object')
  for (const [id, operation] of Object.entries(descriptor.operations)) {
    identifier(id, '$operation.id')
    objectKeys(operation, ['inputSchema', 'resultSchema', 'effects', 'validator', 'resourcesRequired'], ['inputSchema', 'resultSchema', 'effects', 'validator'], '$operation')
    checkSchema(operation.inputSchema); checkSchema(operation.resultSchema)
    stringList(operation.effects, '$operation.effects')
    if (operation.effects.some(effect => !EFFECTS.includes(effect))) fail('$operation.effects', 'unsupported effect')
    identifier(operation.validator, '$operation.validator')
    if (Object.hasOwn(operation, 'resourcesRequired') && typeof operation.resourcesRequired !== 'boolean') fail('$operation.resourcesRequired', 'expected boolean')
  }
  return descriptor
}
