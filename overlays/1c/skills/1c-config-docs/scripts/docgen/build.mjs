#!/usr/bin/env node
// DOCX builder: one content JSON -> <base>_<suffix>.docx per configured language.
//   node docgen/build.mjs --config <cfg.json> <content.json> [...] [--out <dir>] [--report <file>]
//   node docgen/build.mjs --config <cfg.json> --all [--out <dir>]   (every <contentDir>/*.json except "_"-prefixed)
// A content file path that does not exist relative to the cwd is also looked up in <contentDir>.
// Output dir per file: --out > content "outDir" (relative to the content file) > content "set" > first set.
// Exit codes: 0 = all built, 1 = validation failures, 2 = execution/usage/config error.
// Report: --report <file>; else <out>/last-build.json when --out is given (a scratch build never
// overwrites the shared report); else <reportDir>/last-build.json.
import fs from 'node:fs';
import path from 'node:path';
import { loadConfig, parseArgs, runMain, UsageError } from '../lib/config.mjs';
import { loadDocgen } from './lib/load-docgen.mjs';

const { createDocgen, writeReport, printEntry } = await loadDocgen('build');

const USAGE = 'usage: node docgen/build.mjs --config <cfg.json> <content.json> [...] [--out <dir>] [--report <file>]\n       node docgen/build.mjs --config <cfg.json> --all [--out <dir>]';

async function main() {
  const startedAt = new Date().toISOString();
  const args = parseArgs(process.argv.slice(2), { config: 'string', all: 'bool', out: 'string', report: 'string' });
  if (args.help) { console.log(USAGE); return 0; }
  const cfg = loadConfig(args.config);
  const dg = createDocgen(cfg);
  const reportFile = args.report ? path.resolve(args.report)
    : args.out ? path.join(path.resolve(args.out), 'last-build.json')
      : path.join(cfg.reportDir, 'last-build.json');

  const files = [];
  for (const f of args._) {
    if (fs.existsSync(f)) files.push(path.resolve(f));
    else if (fs.existsSync(path.join(cfg.contentDir, f))) files.push(path.join(cfg.contentDir, f));
    else throw new UsageError(`content file not found: ${f} (also looked in ${cfg.contentDir})`);
  }
  if (args.all) {
    if (!fs.existsSync(cfg.contentDir)) throw new UsageError(`contentDir not found: ${cfg.contentDir}`);
    files.push(...fs.readdirSync(cfg.contentDir)
      .filter((f) => f.endsWith('.json') && !f.startsWith('_'))
      .sort().map((f) => path.join(cfg.contentDir, f)));
  }
  if (!files.length) {
    if (args.all) { console.log(`no content files in ${cfg.contentDir} ("_"-prefixed files are skipped by --all)`); return 0; }
    throw new UsageError(`no content files given\n${USAGE}`);
  }

  const entries = [];
  for (const f of files) {
    let e;
    try { e = await dg.buildFile(f, { out: args.out }); } catch (err) {
      e = { content: path.resolve(f), status: 'error', error: err && err.stack ? err.stack.split('\n').slice(0, 3).join(' | ') : String(err), errors: [], warnings: [], outputs: [] };
    }
    entries.push(e);
    printEntry(e);
  }
  const exitCode = entries.some((e) => e.status === 'error') ? 2 : entries.some((e) => e.status === 'invalid') ? 1 : 0;
  const report = { tool: 'build.mjs', config: cfg.file, languages: cfg.langs, startedAt, finishedAt: new Date().toISOString(), argv: process.argv.slice(2), exitCode, files: entries };
  try { writeReport(reportFile, report); } catch (e) { console.error(`cannot write report ${reportFile}: ${e.message}`); return 2; }
  console.log(`exit ${exitCode}: ${entries.filter((e) => e.status === 'ok').length} ok, ${entries.filter((e) => e.status === 'invalid').length} invalid, ${entries.filter((e) => e.status === 'error').length} error · report ${reportFile}`);
  return exitCode;
}

runMain('build', main);
