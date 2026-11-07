import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, readFile, rm, symlink } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createReportProcessAdapter } from '../lib/report-process.mjs'
import { validateEvidence } from '../lib/validators.mjs'

const resultSchema = {
  type: 'object', additionalProperties: false,
  required: ['runId', 'sourceDigest', 'complete', 'tests', 'failures', 'errors', 'skipped'],
  properties: {
    runId: { type: 'string' }, sourceDigest: { type: 'string' }, complete: { type: 'boolean' },
    tests: { type: 'integer', minimum: 0 }, failures: { type: 'integer', minimum: 0 },
    errors: { type: 'integer', minimum: 0 }, skipped: { type: 'integer', minimum: 0 },
  },
}
const script = `
import {writeFileSync,linkSync,symlinkSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
const [dir,runId,sourceDigest,mode,name]=process.argv.slice(2);
const data={runId,sourceDigest,complete:true,tests:2,failures:0,errors:0,skipped:0};
if(mode==='hardlink'){const path=join(process.cwd(),'outside.json');writeFileSync(path,JSON.stringify(data));linkSync(path,join(dir,name));process.exit(0)}
if(mode==='symlink'){const path=join(process.cwd(),'outside-dir');mkdirSync(path);symlinkSync(path,join(dir,name),process.platform==='win32'?'junction':'dir');process.exit(0)}
if(mode==='missing')process.exit(0);
if(mode==='stale-run')data.runId='previous-run';
if(mode==='stale-source')data.sourceDigest='previous-source';
if(mode==='zero')data.tests=0;
if(mode==='fail')data.failures=1;
if(mode==='wrong-type')data.tests='2';
const content=mode==='malformed'?'private-token-in-invalid-json':mode==='oversize'?'x'.repeat(1048577):mode==='utf8'?Buffer.from([0xc0,0xaf]):JSON.stringify(data);
writeFileSync(join(dir,name),content);
if(mode==='nonzero')process.exit(7);
`

async function fixture(t, config = {}) {
  const cwd = await mkdtemp(join(tmpdir(), 'workflow-report-'))
  t.after(() => rm(cwd, { recursive: true, force: true }))
  const runner = join(cwd, 'runner.mjs'), artifactDir = join(cwd, 'artifacts')
  await mkdir(artifactDir)
  await writeFile(runner, script)
  const reportPath = config.reportPath ?? 'summary.json'
  const adapter = createReportProcessAdapter({ id: 'report-fixture', fingerprintPaths: [runner], operations: { test: {
    command: process.execPath,
    args: (inputs, context) => [runner, context.artifactDir, context.runId, context.sourceDigest, inputs.mode ?? 'success', reportPath],
    inputSchema: { type: 'object', additionalProperties: false, properties: { mode: { type: 'string' } } },
    resultSchema, reportPath, validator: 'test-summary', effects: ['startsProcess', 'writesFilesystem'], ...config,
  } } })
  return { adapter, runner, context: { cwd, artifactDir, runId: 'this-run', sourceDigest: 'this-source', stepId: 'test', timeoutMs: 3000 } }
}

test('report process returns schema-validated fresh structured evidence and preserves mutation state', async t => {
  const { adapter, context } = await fixture(t)
  const result = await adapter.execute('test', {}, context)
  assert.equal(result.data.tests, 2)
  assert.equal(result.data.runId, context.runId)
  assert.equal(validateEvidence('test-summary', result.data, context).status, 'passed')
  assert.equal(adapter.descriptor.operations.test.validator, 'test-summary')
  assert.deepEqual(adapter.descriptor.operations.test.resultSchema, resultSchema)
  assert.doesNotMatch(JSON.stringify(result), /command|stdout|argv/)
  assert.ok(['not-applied', 'unknown'].includes(result.mutationState))
  assert.notEqual(result.mutationState, 'applied')
})

test('report fingerprint changes with runner and public report contract', async t => {
  const { adapter, runner } = await fixture(t)
  const before = await adapter.fingerprint()
  assert.match(before, /^[a-f0-9]{64}$/u)
  assert.equal(await adapter.fingerprint(), before)
  await writeFile(runner, `${script}\n// changed runner`)
  assert.notEqual(await adapter.fingerprint(), before)
})

test('zero tests and assertion failures are retained for the validator, never invented as PASS', async t => {
  for (const mode of ['zero', 'fail']) {
    const { adapter, context } = await fixture(t)
    const result = await adapter.execute('test', { mode }, context)
    assert.equal(validateEvidence('test-summary', result.data, context).status, 'failed')
  }
})

test('missing, malformed, invalid UTF-8, oversize and wrong-schema reports are rejected safely', async t => {
  for (const mode of ['missing', 'malformed', 'utf8', 'oversize', 'wrong-type']) {
    const { adapter, context } = await fixture(t)
    await assert.rejects(adapter.execute('test', { mode }, context), error => {
      assert.match(error.message, /^PROCESS_REPORT_[A-Z_]+$/u)
      assert.doesNotMatch(error.message, /private-token|artifacts|summary|1048577/)
      return true
    })
  }
})

test('report provenance must match both current run and source', async t => {
  for (const mode of ['stale-run', 'stale-source']) {
    const { adapter, context } = await fixture(t)
    await assert.rejects(adapter.execute('test', { mode }, context), /PROCESS_REPORT_PROVENANCE_MISMATCH/u)
  }
  const { adapter, context } = await fixture(t)
  await assert.rejects(adapter.execute('test', {}, { ...context, sourceDigest: undefined }), /PROCESS_REPORT_PROVENANCE_REQUIRED/u)
})

test('preexisting report is rejected before runner execution and not overwritten', async t => {
  const { adapter, context } = await fixture(t)
  const path = join(context.artifactDir, 'summary.json')
  await writeFile(path, 'retained-old-report')
  await assert.rejects(adapter.execute('test', {}, context), /PROCESS_REPORT_PREEXISTING/u)
  assert.equal(await readFile(path, 'utf8'), 'retained-old-report')
})

test('successful-looking report cannot override a failed runner process', async t => {
  const { adapter, context } = await fixture(t)
  await assert.rejects(adapter.execute('test', { mode: 'nonzero' }, context), /PROCESS_REPORT_EXECUTION_FAILED/u)
})

test('reports created as symlinks or hardlinks are rejected after the runner exits', async t => {
  for (const mode of ['symlink', 'hardlink']) {
    const { adapter, context } = await fixture(t)
    await assert.rejects(adapter.execute('test', { mode }, context), /PROCESS_REPORT_FILE_INVALID/u)
  }
})

test('report paths reject absolute, traversal, drive-relative and alternate stream syntax', () => {
  for (const reportPath of ['../summary.json', 'folder/../summary.json', '/tmp/report', 'C:\\report.json', 'C:report.json', 'summary.json:stream', 'folder//summary.json']) {
    assert.throws(() => createReportProcessAdapter({ id: 'invalid', operations: { test: { reportPath } } }), /PROCESS_REPORT_PATH_INVALID/u)
  }
})

test('provenance fields must be required by the declared report schema', async t => {
  await assert.rejects(fixture(t, { resultSchema: { type: 'object', properties: {} } }), /PROCESS_REPORT_PROVENANCE_SCHEMA_REQUIRED/u)
})

test('symlinked report parent cannot redirect output outside the artifact directory', async t => {
  const { adapter, context } = await fixture(t, { reportPath: 'linked/summary.json' })
  const outside = join(context.cwd, 'outside')
  await mkdir(outside)
  await symlink(outside, join(context.artifactDir, 'linked'), process.platform === 'win32' ? 'junction' : 'dir')
  await assert.rejects(adapter.execute('test', {}, context), /PROCESS_REPORT_PATH_INVALID/u)
  await assert.rejects(readFile(join(outside, 'summary.json')), { code: 'ENOENT' })
})

test('symlinked artifact root is rejected', async t => {
  const { adapter, context } = await fixture(t)
  const alias = join(context.cwd, 'artifact-alias')
  await symlink(context.artifactDir, alias, process.platform === 'win32' ? 'junction' : 'dir')
  await assert.rejects(adapter.execute('test', {}, { ...context, artifactDir: alias }), /PROCESS_REPORT_ARTIFACT_DIRECTORY_INVALID/u)
})
