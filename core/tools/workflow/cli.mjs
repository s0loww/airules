#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { lstat, readFile } from 'node:fs/promises'
import { isAbsolute, resolve } from 'node:path'
import { userInfo } from 'node:os'
import { pathToFileURL } from 'node:url'
import { WorkflowHost } from './index.mjs'
import { canonical, validateWorkflow } from './lib/contracts.mjs'
import { createLocalProcessAdapter } from './lib/local-process.mjs'

const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u
const fail = code => { throw Object.assign(new Error(code), { code }) }
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const text = value => typeof value === 'string' && value.length > 0 && !value.includes('\0')
function keys(value, allowed, required = []) {
  if (!plain(value) || Object.keys(value).some(key => !allowed.includes(key))
    || required.some(key => !Object.hasOwn(value, key))) fail('INVALID_REGISTRY')
}
function strings(value, allowEmpty = false) {
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string' || item.includes('\0') || (!allowEmpty && !item.length))) fail('INVALID_REGISTRY')
}
function absolute(value) { if (!text(value) || !isAbsolute(value)) fail('INVALID_REGISTRY_PATH') }
function identifier(value) { if (typeof value !== 'string' || !ID.test(value)) fail('INVALID_REGISTRY_ID') }

function argumentsFor(argv) {
  const result = {}; const commands = new Set(['capabilities', 'plan', 'run', 'result'])
  const flags = new Set(['registry', 'project', 'workflow', 'plan', 'digest', 'request', 'run'])
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (commands.has(arg) && !result.command) { result.command = arg; continue }
    if (arg === '--execute') {
      if (result.execute) fail('INVALID_ARGUMENTS')
      result.execute = true; continue
    }
    if (!arg.startsWith('--') || !flags.has(arg.slice(2))) fail('INVALID_ARGUMENTS')
    const key = arg.slice(2)
    if (Object.hasOwn(result, key) || !text(argv[i + 1]) || argv[i + 1].startsWith('--')) fail('INVALID_ARGUMENTS')
    result[key] = argv[++i]
  }
  if (!result.command || !result.registry || !isAbsolute(result.registry)) fail('ABSOLUTE_REGISTRY_REQUIRED')
  const commandFields = {
    capabilities: ['project', 'workflow'], plan: ['project', 'workflow'], run: ['plan', 'digest', 'request'], result: ['run'],
  }
  const required = commandFields[result.command]
  if (required.some(key => !result[key])) fail('INVALID_ARGUMENTS')
  const allowed = new Set(['command', 'registry', ...required, ...(result.command === 'run' ? ['execute'] : [])])
  if (Object.keys(result).some(key => !allowed.has(key))) fail('INVALID_ARGUMENTS')
  if (result.command === 'run' && !result.execute) fail('EXECUTE_FLAG_REQUIRED')
  return result
}

async function registryFrom(path) {
  const info = await lstat(path)
  if (!info.isFile() || info.isSymbolicLink() || info.size > 4 * 1024 * 1024) fail('INVALID_REGISTRY_FILE')
  const data = JSON.parse((await readFile(path, 'utf8')).replace(/^\uFEFF/u, ''))
  canonical(data) // Reject unsafe keys and values before interpreting trusted machine configuration.
  keys(data, ['schemaVersion', 'stateDir', 'projects', 'workflows', 'localAdapters'],
    ['schemaVersion', 'stateDir', 'projects', 'workflows', 'localAdapters'])
  if (data.schemaVersion !== 1 || !plain(data.projects) || !plain(data.workflows) || !plain(data.localAdapters)) fail('INVALID_REGISTRY')
  absolute(data.stateDir)
  for (const [id, project] of Object.entries(data.projects)) {
    identifier(id)
    keys(project, ['root', 'bindingPath', 'sourcePaths', 'configPaths', 'resources'], ['root', 'bindingPath'])
    absolute(project.root)
    if (!text(project.bindingPath) || isAbsolute(project.bindingPath)) fail('INVALID_REGISTRY_PATH')
    for (const field of ['sourcePaths', 'configPaths']) {
      if (project[field] !== undefined) {
        strings(project[field])
        if (project[field].some(isAbsolute)) fail('INVALID_REGISTRY_PATH')
      }
    }
    if (project.resources !== undefined) {
      if (!plain(project.resources)) fail('INVALID_REGISTRY')
      for (const [ref, resource] of Object.entries(project.resources)) {
        identifier(ref); keys(resource, ['id', 'environment'], ['id']); identifier(resource.id)
        if (resource.environment !== undefined && !['test', 'development', 'production'].includes(resource.environment)) fail('INVALID_REGISTRY')
      }
    }
  }
  for (const [id, workflow] of Object.entries(data.workflows)) {
    identifier(id); validateWorkflow(workflow)
    if (workflow.id !== id) fail('WORKFLOW_ID_MISMATCH')
  }
  const adapters = Object.create(null)
  for (const [id, config] of Object.entries(data.localAdapters)) {
    identifier(id); keys(config, ['version', 'operations'], ['operations'])
    if (!plain(config.operations)) fail('INVALID_REGISTRY')
    if (config.version !== undefined && !text(config.version)) fail('INVALID_REGISTRY')
    const operations = Object.create(null)
    for (const [operationId, operation] of Object.entries(config.operations)) {
      identifier(operationId)
      keys(operation, ['command', 'args', 'inputSchema', 'resultSchema', 'effects', 'validator', 'fingerprintPaths', 'resourcesRequired'],
        ['command', 'args', 'inputSchema', 'effects', 'validator'])
      absolute(operation.command); strings(operation.args, true)
      if (operation.args.length > 1024 || operation.args.some(value => value.length > 65536)) fail('INVALID_REGISTRY')
      if (operation.fingerprintPaths !== undefined) {
        strings(operation.fingerprintPaths); operation.fingerprintPaths.forEach(absolute)
      }
      const fixedArgs = [...operation.args]
      operations[operationId] = { ...operation,
        // This file seals closure-captured constant arguments as well as descriptors.
        fingerprintPaths: [...new Set([path, ...(operation.fingerprintPaths ?? [])])],
        args: () => [...fixedArgs],
      }
    }
    adapters[id] = createLocalProcessAdapter({ id, ...(config.version === undefined ? {} : { version: config.version }), operations })
  }
  return { ...data, adapters }
}

/** Explicit operator CLI. It never searches a project for code or machine configuration. */
export async function main(argv = process.argv.slice(2)) {
  try {
    const args = argumentsFor(argv)
    const registry = await registryFrom(resolve(args.registry))
    const identity = userInfo()
    const principal = `local-${createHash('sha256').update(`${identity.username}\0${identity.uid}`).digest('hex').slice(0, 40)}`
    const host = new WorkflowHost({ stateDir: registry.stateDir, projects: registry.projects,
      workflows: registry.workflows, adapters: registry.adapters, allowTargetMutations: false,
      authorize: ({ principal: caller, action }) => caller === principal
        && (['capabilities', 'plan', 'result'].includes(action) || (args.execute === true && ['run', 'execute'].includes(action))),
    })
    let result
    if (args.command === 'capabilities') result = await host.capabilities({ projectId: args.project, workflowId: args.workflow, principal })
    else if (args.command === 'plan') result = await host.plan({ projectId: args.project, workflowId: args.workflow, principal })
    else if (args.command === 'run') result = await host.run({ planId: args.plan, planDigest: args.digest, requestId: args.request, principal })
    else result = await host.result({ runId: args.run, principal })
    return { exitCode: args.command === 'run' && result.verdict !== 'PASS' ? 1 : 0, output: { ok: true, result } }
  } catch (error) {
    const candidate = error?.code ?? error?.message
    const code = typeof candidate === 'string' && /^[A-Z][A-Z0-9_:-]{0,95}$/u.test(candidate) ? candidate : 'WORKFLOW_ERROR'
    return { exitCode: 1, output: { ok: false, error: code } }
  }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const { exitCode, output } = await main()
  process.stdout.write(`${JSON.stringify(output)}\n`)
  process.exitCode = exitCode
}
