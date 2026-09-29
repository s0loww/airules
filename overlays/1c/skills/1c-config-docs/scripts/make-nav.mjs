#!/usr/bin/env node
// make-nav.mjs — navigation page (index.html) and README.md registry for every
// documentation set of the config (mono- or bilingual).
//
//   node make-nav.mjs --config <cfg.json> [--dry-run] [--date YYYY-MM-DD] [--report <file>]
//
//   --dry-run   build and validate everything in memory, write nothing
//   --force     overwrite an index.html / README.md that make-nav did not write (refused otherwise, exit 2)
//   --date      generation date printed in the footers (default: today, local time)
//
// Writes, per set: <set.dir>/index.html (self-contained; primary language leading,
// secondary as the small line) and <set.dir>/README.md (in nav.readmeLanguage:
// documents, diagrams, checksums, rebuild). Output is deterministic except the date.
//
// Inputs:
//   documents   content JSON files (<contentDir>/*.json and generated/) whose output dir is
//               the set dir (content "set" / "outDir" / first set); docx <base>_<suffix>.docx
//   diagrams    <set.dir>/<prefix>*.json + .html; expected list = <set.dir>/_REGISTRY.md when
//               present, else every <prefix>*.json; *.visual-check.* and _-prefixed files ignored
//
// Exit codes: 0 = complete and valid · 1 = something expected is missing or a
// validation check failed · 2 = execution/config error.
// Report: <reportDir>/make-nav-report.json (or --report).
//
// Rendering and validators live in lib/nav.mjs (shared with make-clear.mjs).
//
// Node >= 18, no dependencies.

import fs from 'node:fs';
import path from 'node:path';
import { loadConfig, parseArgs, runMain, UsageError, ConfigError, writeJsonReport } from './lib/config.mjs';
import { buildNav } from './lib/nav.mjs';

function main() {
  const args = parseArgs(process.argv.slice(2), { config: 'string', dryRun: 'bool', force: 'bool', date: 'string', report: 'string' });
  if (args.help) { console.log('usage: node make-nav.mjs --config <cfg.json> [--dry-run] [--force] [--date YYYY-MM-DD] [--report <file>]'); return 0; }
  if (args._.length) throw new UsageError(`unexpected argument ${args._[0]}`);
  if (args.date && !/^\d{4}-\d{2}-\d{2}$/.test(args.date)) throw new UsageError('--date expects YYYY-MM-DD');
  const cfg = loadConfig(args.config);
  const reportFile = args.report ? path.resolve(args.report) : path.join(cfg.reportDir, 'make-nav-report.json');
  const { LANGS, SOURCE, genDate, outputs, pending, checkHtml, checkTargets, mdHrefs } = buildNav(cfg, { genDate: args.date });

  // Ownership: a set directory may be a project root (dir "."). An index.html / README.md that
  // make-nav did not write (no "make-nav" in it) is someone else's — never overwritten silently.
  const foreign = [];
  for (const { g } of outputs) {
    for (const name of ['index.html', 'README.md']) {
      const f = path.join(g.set.dir, name);
      if (fs.existsSync(f) && !fs.readFileSync(f, 'utf8').includes('make-nav')) foreign.push(f);
    }
  }
  if (foreign.length && !args.force) {
    const msg = `not written by make-nav, would be overwritten: ${foreign.join(', ')} — move them, point sets[].dir elsewhere, or pass --force`;
    if (!args.dryRun) throw new ConfigError(msg);
    console.log(`warning: ${msg}`);
  }

  let failed = false;
  const report = { tool: 'make-nav.mjs', config: cfg.file, dryRun: !!args.dryRun, generated: genDate, source: SOURCE, languages: LANGS, sets: [] };
  console.log(`make-nav ${args.dryRun ? '(dry run) ' : ''}· source ${SOURCE.ref ? `${SOURCE.ref}@` : ''}${SOURCE.commit} · generated ${genDate}`);
  for (const { g, html, md } of outputs) {
    const { set, docs, diagrams, issues, warnings, links } = g;
    console.log('');
    console.log(`[${set.id}] ${set.dir}`);
    const docFiles = docs.flatMap((d) => LANGS.map((l) => d.langs[l]));
    const docPresent = docFiles.filter((f) => f.info).length;
    console.log(`  documents : ${docs.length} content files, ${docPresent}/${docFiles.length} docx present`);
    for (const d of docs) {
      const st = (f) => (f.info ? 'ok     ' : 'MISSING');
      console.log(`    ${LANGS.map((l) => `${st(d.langs[l])} ${d.langs[l].name.padEnd(48)}`).join(' ').trimEnd()}`);
    }
    const diagOk = diagrams.filter((d) => d.json && d.html).length;
    const regNote = fs.existsSync(path.join(set.dir, '_REGISTRY.md')) ? '_REGISTRY.md' : `all ${set.diagramPrefix}*.json`;
    console.log(`  diagrams  : ${diagrams.length} expected (${regNote}), ${diagOk} complete (json+html); links between diagrams ${links.total}, broken ${links.broken.length}`);
    for (const d of diagrams) if (!d.json || !d.html) console.log(`    MISSING ${!d.json ? d.jsonName : ''} ${!d.html ? d.htmlName : ''}`.trimEnd());
    for (const w of warnings) console.log(`  warning   : ${w}`);
    for (const i of issues) if (!/^MISSING/.test(i)) console.log(`  issue     : ${i}`);

    const hc = checkHtml(html);
    const brokenHtml = checkTargets(set.dir, hc.hrefs, pending);
    const brokenMd = checkTargets(set.dir, mdHrefs(md), pending);
    console.log(`  index.html: ${hc.errors.length ? 'MALFORMED' : 'well-formed'}, ${hc.hrefs.length} hrefs, ${brokenHtml.length} broken`);
    for (const e of hc.errors) console.log(`    html error: ${e}`);
    for (const b of brokenHtml) console.log(`    broken href: ${b}`);
    console.log(`  README.md : ${mdHrefs(md).length} links, ${brokenMd.length} broken`);
    for (const b of brokenMd) console.log(`    broken link: ${b}`);
    if (hc.errors.length || brokenHtml.length || brokenMd.length || issues.length) failed = true;

    if (!args.dryRun) {
      fs.writeFileSync(path.join(set.dir, 'index.html'), html, 'utf8');
      fs.writeFileSync(path.join(set.dir, 'README.md'), md, 'utf8');
      console.log(`  wrote     : index.html (${Buffer.byteLength(html)} B), README.md (${Buffer.byteLength(md)} B)`);
    }
    console.log(`  status    : ${issues.length ? `INCOMPLETE — ${issues.length} issue(s)` : 'complete'}`);
    report.sets.push({
      id: set.id, dir: set.dir, documents: docs.map((d) => ({ base: d.base, files: LANGS.map((l) => ({ name: d.langs[l].name, ...(d.langs[l].info || { missing: true }) })) })),
      diagrams: diagrams.map((d) => ({ stem: d.stem, json: !!d.json, html: !!d.html })), links, issues, warnings,
      html: { errors: hc.errors, broken: brokenHtml }, readme: { broken: brokenMd },
    });
  }

  // Independent re-read of what was written.
  if (!args.dryRun) {
    for (const { g, html, md } of outputs) {
      const h = fs.readFileSync(path.join(g.set.dir, 'index.html'), 'utf8');
      const r = fs.readFileSync(path.join(g.set.dir, 'README.md'), 'utf8');
      if (h !== html || r !== md) { console.log(`re-read mismatch in ${g.set.id}`); failed = true; }
      const hc = checkHtml(h);
      const broken = checkTargets(g.set.dir, hc.hrefs, new Set());
      if (hc.errors.length || broken.length) { console.log(`re-read check failed in ${g.set.id}: ${[...hc.errors, ...broken].join('; ')}`); failed = true; }
    }
  }

  report.exitCode = failed ? 1 : 0;
  writeJsonReport(reportFile, report);
  console.log('');
  console.log(failed ? `RESULT: incomplete (exit 1) · report ${reportFile}` : `RESULT: complete (exit 0) · report ${reportFile}`);
  return failed ? 1 : 0;
}

runMain('make-nav', main);