import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, writeFile, rm, symlink } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { inspectRunnerBinding, inspectDeployBinding, compileRunnerCommand, validateDeployReport, normalizeDeployServerTarget } from '../index.mjs'

const sha = 'a'.repeat(64), runId = '11111111-2222-3333-4444-555555555555'
const fields = ['RunId', 'StepId', 'SourceDigest', 'TargetDigest', 'ProfileDigest', 'ExactBuild', 'TargetPath', 'TargetKind', 'TargetServer', 'TargetRef']
const header = `param([ValidateSet('doctor','analyze','deploy')] [string]$Command='doctor', [string]$Profile, [switch]$Apply, ${fields.map(field => `[string]$Workflow${field}`).join(', ')})\nfunction FixtureOnly {}`
const runner = 'tools/agent-1c/agent-1c.ps1'
const binding = { schemaVersion: 1, kind: 'agent-1c', runnerPath: runner, profilePath: 'agent-1c.json', sourceKind: 'extension', extensionName: 'Fixture', exactBuild: '8.3.27.1989' }
async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'workflow-deploy-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  await mkdir(join(root, 'tools/agent-1c/lib'), { recursive: true }); await mkdir(join(root, 'src'))
  await writeFile(join(root, runner), header)
  await writeFile(join(root, 'tools/agent-1c/lib/1c-guard.ps1'), '# fixture only')
  await writeFile(join(root, 'tools/agent-1c/toolchain.lock.json'), '{}')
  const profile = { schemaVersion: 1, projectId: 'fixture', sourceDir: 'src', resultDir: 'reports',
    platform: { versionPrefix: '8.3.27' }, extension: { name: 'Fixture' },
    testTarget: { kind: 'file', environment: 'test', path: 'test-base', envFile: '../NEVER_READ.env', envSection: 'TEST' } }
  await writeFile(join(root, 'agent-1c.json'), JSON.stringify(profile))
  return { root, profile, save: () => writeFile(join(root, 'agent-1c.json'), JSON.stringify(profile)) }
}

test('deploy compiler uses explicit Apply and fully bound fixed protocol arguments only', async t => {
  const f = await fixture(t)
  const context = { runId, stepId: 'apply', sourceDigest: sha, targetDigest: sha, profileDigest: sha, exactBuild: binding.exactBuild, targetPath: join(f.root, 'test-base') }
  const options = { root: f.root, runnerKind: 'agent-1c', operation: 'deploy-apply', runnerPath: runner, profilePath: binding.profilePath, pwshPath: join(f.root, 'pwsh.exe'), deployContext: context }
  const result = compileRunnerCommand(options)
  assert.ok(result.args.includes('-Apply'))
  assert.deepEqual(result.args.slice(-14), Object.entries(context).flatMap(([key, value]) => [`-Workflow${key[0].toUpperCase()}${key.slice(1)}`, value]))
  assert.equal(result.enabled, false)
  assert.throws(() => compileRunnerCommand({ ...options, deployContext: undefined }))
  for (const patch of [{ runId: '../escape' }, { stepId: '..' }, { sourceDigest: 'bad' }, { targetPath: 'relative' }, { arbitrary: '-Command' }]) {
    assert.throws(() => compileRunnerCommand({ ...options, deployContext: { ...context, ...patch } }))
  }
  assert.throws(() => compileRunnerCommand({ ...options, operation: 'doctor' }), /DEPLOY_CONTEXT_UNEXPECTED/u)
})

test('old runner with Apply but no binding protocol is not deploy capable', async t => {
  const f = await fixture(t)
  assert.equal((await inspectRunnerBinding({ root: f.root, binding })).operations['deploy-apply'].supported, true)
  await writeFile(join(f.root, runner), "param([ValidateSet('doctor','deploy')] [string]$Command, [string]$Profile, [switch]$Apply)\n")
  assert.equal((await inspectRunnerBinding({ root: f.root, binding })).operations['deploy-apply'].supported, false)
  await assert.rejects(inspectDeployBinding({ root: f.root, binding }), /DEPLOY_PROTOCOL_REQUIRED/u)
})

test('deploy inspection binds the concrete test base without opening credentials or database', async t => {
  const f = await fixture(t), info = await inspectDeployBinding({ root: f.root, binding })
  assert.equal(info.targetPath, resolve(f.root, 'test-base'))
  assert.equal(info.sourcePath, 'src'); assert.equal(info.resultPath, 'reports')
  assert.equal(info.target.environment, 'test'); assert.equal(info.target.kind, 'file')
  assert.equal(info.target.id, `onec-${info.targetDigest}`)
  assert.match(info.profileDigest, /^[a-f0-9]{64}$/u)
  assert.doesNotMatch(JSON.stringify(info), /NEVER_READ|envSection/u)
  f.profile.testTarget.environment = 'development'; await f.save()
  const second = await inspectDeployBinding({ root: f.root, binding })
  assert.equal(second.target.id, info.target.id)
  assert.notEqual(second.fingerprint, info.fingerprint)
})

test('deploy target metadata rejects production, unknown path and source/report overlap', async t => {
  const f = await fixture(t)
  for (const patch of [{ environment: 'production' }, { path: null }, { path: 'src' }, { path: 'reports' }]) {
    f.profile.testTarget = { kind: 'file', environment: 'test', path: 'test-base', ...patch }; await f.save()
    await assert.rejects(inspectDeployBinding({ root: f.root, binding }))
  }
  f.profile.testTarget = { kind: 'file', environment: 'test', path: 'test-base' }
  f.profile.resultDir = 'src/reports'; await f.save()
  await assert.rejects(inspectDeployBinding({ root: f.root, binding }), /DEPLOY_SOURCE_RESULT_OVERLAP/u)
})

test('server identity is normalized without DNS or credential resolution and shares a stable resource', async t => {
  const f = await fixture(t)
  f.profile.testTarget = { kind: 'server', environment: 'test', server: 'CLUSTER.Example.', ref: ' Демо ' }
  await f.save()
  const info = await inspectDeployBinding({ root: f.root, binding })
  assert.equal(info.target.kind, 'server'); assert.equal(info.targetPath, null)
  assert.equal(info.targetServer, 'cluster.example:1541'); assert.equal(info.targetRef, 'демо')
  f.profile.testTarget.server = 'cluster.example:01541'; f.profile.testTarget.ref = 'демо'
  await f.save()
  assert.equal((await inspectDeployBinding({ root: f.root, binding })).target.id, info.target.id)
  f.profile.testTarget.ref = 'other'; await f.save()
  assert.notEqual((await inspectDeployBinding({ root: f.root, binding })).target.id, info.target.id)
  f.profile.platform.engine = 'ibcmd'; await f.save()
  await assert.rejects(inspectDeployBinding({ root: f.root, binding }))
})

test('server metadata rejects ambiguous, injected and incomplete endpoints and old file-only protocol', async t => {
  for (const [server, ref] of [['user@host', 'base'], ['host:0', 'base'], ['host:65536', 'base'], ['host/path', 'base'],
    ['https://host', 'base'], ['host', 'base;Pwd=secret'], ['host', 'base/path'], ['host', ''], ['host..example', 'base']]) {
    assert.throws(() => normalizeDeployServerTarget(server, ref), /DEPLOY_SERVER_TARGET_INVALID/u)
  }
  assert.deepEqual(normalizeDeployServerTarget('[::1]', 'BASE'), { server: '[0000:0000:0000:0000:0000:0000:0000:0001]:1541', ref: 'base' })
  assert.deepEqual(normalizeDeployServerTarget('[0:0:0:0:0:0:0:1]:1541', 'base'), normalizeDeployServerTarget('[::1]', 'BASE'))
  const f = await fixture(t)
  f.profile.testTarget = { kind: 'server', environment: 'test', server: 'host', ref: 'base' }; await f.save()
  await writeFile(join(f.root, runner), header.replace(', [string]$WorkflowTargetKind, [string]$WorkflowTargetServer, [string]$WorkflowTargetRef', ''))
  await assert.rejects(inspectDeployBinding({ root: f.root, binding }), /DEPLOY_SERVER_PROTOCOL_REQUIRED/u)
})

test('bound server compiler has no file path or shell string and bound preview never applies', async t => {
  const f = await fixture(t)
  const context = { runId, stepId: 'apply', sourceDigest: sha, targetDigest: sha, profileDigest: sha, exactBuild: binding.exactBuild,
    targetKind: 'server', targetServer: 'host:1541', targetRef: 'base' }
  const options = { root: f.root, runnerKind: 'agent-1c', operation: 'deploy-apply', runnerPath: runner, profilePath: binding.profilePath,
    pwshPath: join(f.root, 'pwsh.exe'), deployContext: context }
  const apply = compileRunnerCommand(options)
  assert.ok(apply.args.includes('-Apply')); assert.ok(apply.args.includes('-WorkflowTargetServer'))
  assert.equal(apply.args.includes('-WorkflowTargetPath'), false)
  const preview = compileRunnerCommand({ ...options, operation: 'deploy-preview' })
  assert.equal(preview.args.includes('-Apply'), false)
  assert.ok(preview.args.includes('-WorkflowRunId'))
  assert.throws(() => compileRunnerCommand({ ...options, deployContext: { ...context, targetPath: join(f.root, 'ambiguous') } }))
  assert.throws(() => compileRunnerCommand({ ...options, deployContext: { ...context, targetServer: 'host' } }))
})

test('deploy rejects target aliases instead of creating a second target lock identity', async t => {
  const f = await fixture(t)
  await mkdir(join(f.root, 'base-real'))
  try { await symlink(join(f.root, 'base-real'), join(f.root, 'base-link'), 'junction') }
  catch (error) { if (['EPERM', 'EACCES'].includes(error.code)) { t.skip('Host does not permit symlinks'); return } throw error }
  f.profile.testTarget.path = 'base-link'; await f.save()
  await assert.rejects(inspectDeployBinding({ root: f.root, binding }), /DEPLOY_TARGET_ALIAS_FORBIDDEN/u)
})

const expected = () => ({ runId, stepId: 'apply', sourceDigest: sha, targetDigest: sha, profileDigest: sha, projectId: 'fixture', startedAfter: 1000, finishedBefore: 5000 })
const report = () => ({ schemaVersion: 1, projectId: 'fixture', command: 'deploy', apply: true, startedAtUtc: new Date(2000).toISOString(), finishedAtUtc: new Date(3000).toISOString(), exitCode: 0,
  workflow: { schemaVersion: 1, runId, stepId: 'apply', sourceDigest: sha, targetDigest: sha, profileDigest: sha, mutationState: 'applied' },
  steps: [{ name: 'deploy.apply', status: 'ok', message: 'PRIVATE_REPORT_TEXT' }] })
test('deploy evidence requires actual apply postcondition; process exit zero alone never passes', () => {
  const result = validateDeployReport(report(), expected())
  assert.equal(result.complete, true); assert.equal(result.mutationState, 'applied')
  assert.ok(result.assertions.every(row => row.passed))
  assert.doesNotMatch(JSON.stringify(result), /PRIVATE_REPORT_TEXT/u)
  for (const patch of [value => { value.exitCode = 1 }, value => { value.steps[0].status = 'dry-run' },
    value => { value.steps.push({ name: 'deploy.probe', status: 'error' }) }, value => { value.steps.push({ ...value.steps[0] }) }]) {
    const value = report(); patch(value)
    assert.equal(validateDeployReport(value, expected()).assertions.every(row => row.passed), false)
  }
})
test('deploy report identities, freshness and shape cannot be substituted', () => {
  for (const patch of [value => { value.workflow.runId = 'other' }, value => { value.workflow.stepId = 'other' }, value => { value.workflow.targetDigest = 'b'.repeat(64) },
    value => { value.workflow.profileDigest = 'b'.repeat(64) }, value => { value.workflow.sourceDigest = 'b'.repeat(64) }, value => { value.projectId = 'other' },
    value => { value.startedAtUtc = new Date(0).toISOString() }, value => { value.finishedAtUtc = new Date(6000).toISOString() }, value => { value.apply = false },
    value => { delete value.workflow }, value => { value.workflow.mutationState = 'partial' }, value => { value.steps = [] }]) {
    const value = report(); patch(value)
    assert.throws(() => validateDeployReport(value, expected()))
  }
})
test('applied failure remains applied; partial/unknown report never becomes PASS', () => {
  const value = report(); value.exitCode = 5; value.steps.push({ name: 'deploy.probe', status: 'error' })
  assert.equal(validateDeployReport(value, expected()).mutationState, 'applied')
  value.workflow.mutationState = 'unknown'
  const result = validateDeployReport(value, expected())
  assert.equal(result.mutationState, 'unknown'); assert.equal(result.assertions.every(row => row.passed), false)
  value.workflow.mutationState = 'not-applied'
  assert.throws(() => validateDeployReport(value, expected()), /DEPLOY_REPORT_MUTATION_CONTRADICTION/u)
})

test('preview evidence is independently bound and cannot masquerade as applied deployment', () => {
  const value = report(); value.apply = false; value.workflow.mutationState = 'not-applied'; value.steps[0].status = 'dry-run'
  assert.ok(validateDeployReport(value, { ...expected(), operation: 'deploy-preview' }).assertions.every(row => row.passed))
  assert.throws(() => validateDeployReport(value, expected()))
  const applied = report()
  assert.throws(() => validateDeployReport(applied, { ...expected(), operation: 'deploy-preview' }))
})
test('canonical PowerShell runner binds workflow report and gates before target mutation without executing PowerShell', async () => {
  const script = await readFile(new URL('../../agent-1c/agent-1c.ps1', import.meta.url), 'utf8')
  assert.ok(script.indexOf('WORKFLOW_PROFILE_CHANGED') < script.indexOf("$script:WorkflowMutationState = 'unknown'"))
  assert.ok(script.indexOf('WORKFLOW_PLATFORM_BUILD_MISMATCH') < script.indexOf("$script:WorkflowMutationState = 'unknown'"))
  assert.ok(script.indexOf('WORKFLOW_TARGET_PATH_MISMATCH') < script.indexOf("$script:WorkflowMutationState = 'unknown'"))
  assert.match(script, /New-Item -ItemType Directory -Path \$freshRunDir -ErrorAction Stop/u)
  assert.match(script, /\$report\.workflow = \[ordered\]@/u)
})

test('PowerShell parser and isolated metadata guards agree with JS; no runner or platform is invoked', { skip: process.platform !== 'win32' }, () => {
  const path = fileURLToPath(new URL('../../agent-1c/agent-1c.ps1', import.meta.url)).replaceAll("'", "''")
  const command = `$tokens=$null; $errors=$null; $ast=[System.Management.Automation.Language.Parser]::ParseFile('${path}',[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'AST_PARSE_FAILED'}
foreach($functionName in @('Get-WorkflowServerIdentity','Assert-WorkflowPlatformTool')){
  $fn=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $functionName},$true)
  . ([scriptblock]::Create($fn.Extent.Text))
}
$a=Get-WorkflowServerIdentity 'CLUSTER.Example.' ' BASE '
$b=Get-WorkflowServerIdentity '[::1]' 'BASE'
if($a.server -cne 'cluster.example:1541' -or $a.ref -cne 'base' -or $b.server -cne '[0000:0000:0000:0000:0000:0000:0000:0001]:1541'){throw 'NORMALIZER_PARITY_FAILED'}
function Test-Path {return $true}
function Assert-WorkflowPathNoReparse {}
$script:WorkflowProtocol=$true; $WorkflowExactBuild='8.3.27.1989'; $script:FakeBuild=1989
function Get-Item {return @{Directory=@{Parent=@{Name='8.3.27.1989'}}; VersionInfo=@{FileMajorPart=8;FileMinorPart=3;FileBuildPart=27;FilePrivatePart=$script:FakeBuild}}}
Assert-WorkflowPlatformTool 'fixture-ibcmd.exe'
$script:FakeBuild=1990; $rejected=$false
try{Assert-WorkflowPlatformTool 'fixture-ibcmd.exe'}catch{if($_.Exception.Message -eq 'WORKFLOW_PLATFORM_BUILD_MISMATCH'){$rejected=$true}}
if(-not $rejected){throw 'MIXED_BINARY_NOT_REJECTED'}
Write-Output 'ISOLATED_METADATA_GUARDS_PASS'`
  const processResult = spawnSync('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(command, 'utf16le').toString('base64')], { encoding: 'utf8', windowsHide: true, timeout: 15000 })
  assert.equal(processResult.status, 0, 'isolated PowerShell metadata guards failed')
  assert.match(processResult.stdout, /ISOLATED_METADATA_GUARDS_PASS/u)
})
