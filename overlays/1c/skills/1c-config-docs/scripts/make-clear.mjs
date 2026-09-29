#!/usr/bin/env node
// make-clear.mjs — the export copy of the documentation ("clear copy"): only what a reader
// opens without the repository, with every link checked inside the copy.
//
//   node make-clear.mjs --config <cfg.json> [--dest <dir>] [--include-internal]
//                       [--allow-excluded-links] [--apply] [--date YYYY-MM-DD] [--report <file>]
//
// Without --apply nothing is written: the plan, the stale files and the link check are
// reported (--dry-run is accepted as the explicit spelling of that default). --apply writes.
// Ownership: the copy's manifest <dest>.make-clear-manifest.json (next to the copy, not in it)
// lists what this tool wrote last time. Only files from that manifest are ever removed; any
// other file in the destination is left in place and reported. A non-empty destination
// without a manifest is refused (exit 2) — it is not ours to clean.
//
// Copy: <outputRoot>/<clearCopy> (or --dest). Per set, at the same path relative to outputRoot:
//   index.html                the set page; copied byte for byte, or — when documents are left out —
//                             re-rendered by the make-nav renderer without them (lib/nav.mjs)
//   <diagramPrefix>*.html     diagrams (not *.visual-check.*, not "_"-prefixed)
//   <base>_<suffix>.docx      documents of the set (content files whose output dir is the set dir)
// Documents listed in sets[].internalDocs are left out unless --include-internal.
// Nothing else is copied (no JSON, README, PNG, _facts, _build, visual-check).
//
// Checks: every link of the copy resolves to a file of the copy — index.html hrefs, links
// baked into the diagram HTML (data-*-link / href / src), external relationship targets of
// every docx (docx -> docx, docx -> html); every copied file is byte-compared with its source
// after the copy (the re-rendered index with its rendered text). Files this tool wrote before
// that are no longer produced are removed (listed in the report). A link to a document that was left out
// (internalDocs) is reported separately: a finding (exit 1) unless --allow-excluded-links.
//
// Exit codes: 0 = copy complete, all links resolve, bytes equal · 1 = findings (missing source
// file, broken link, link to a left-out document, byte mismatch, malformed index) · 2 = usage,
// config or execution error (also: --dest would contain or equal a source directory, or is a
// non-empty directory without a make-clear manifest).
// Report: --report, else <reportDir>/make-clear-report.json (with --dest: <dest>.make-clear-report.json).
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { loadConfig, parseArgs, runMain, UsageError, ConfigError, samePath, writeJsonReport } from './lib/config.mjs';
import { buildNav, safeDecode } from './lib/nav.mjs';
import { docxExternalTargets } from './lib/zip.mjs';

const USAGE = 'usage: node make-clear.mjs --config <cfg.json> [--dest <dir>] [--include-internal] [--allow-excluded-links] [--apply] [--date YYYY-MM-DD] [--report <file>]';
const MANIFEST_TOOL = 'make-clear.mjs';
const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const isFile = (f) => fs.existsSync(f) && fs.statSync(f).isFile();
const norm = (p) => (process.platform === 'win32' ? path.resolve(p).toLowerCase() : path.resolve(p));
const inside = (child, parent) => { const r = path.relative(parent, child); return r === '' || (!r.startsWith('..') && !path.isAbsolute(r)); };
const decodeHtml = (s) => s.replace(/&(lt|gt|amp|quot|apos|#\d+|#x[0-9a-fA-F]+);/g, (m, e) => {
  if (e[0] === '#') return String.fromCodePoint(e[1] === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
  return { lt: '<', gt: '>', amp: '&', quot: '"', apos: "'" }[e];
});
const isExternal = (h) => /^[a-z][a-z0-9+.-]*:/i.test(h) || h.startsWith('//');

/** Relative link targets baked into an archify diagram: data-*-link, href, src attributes. */
function diagramLinks(html) {
  const out = [];
  for (const m of html.matchAll(/\s((?:data-[a-z0-9-]*-link)|href|src|xlink:href)\s*=\s*"([^"]*)"/gi)) out.push({ attr: m[1], href: decodeHtml(m[2]) });
  return out;
}

function walk(dir) {
  if (!fs.existsSync(dir)) return [];
  const out = [];
  for (const d of fs.readdirSync(dir, { withFileTypes: true })) {
    const f = path.join(dir, d.name);
    if (d.isDirectory()) out.push(...walk(f)); else out.push(f);
  }
  return out;
}

/** After removing `file`, drop its parent directories that became empty, up to (not including) `stop`. */
function removeEmptyParents(file, stop) {
  const removed = [];
  let dir = path.dirname(file);
  while (inside(dir, stop) && !samePath(dir, stop) && fs.existsSync(dir) && !fs.readdirSync(dir).length) {
    fs.rmdirSync(dir); removed.push(dir);
    dir = path.dirname(dir);
  }
  return removed;
}

/** The previous copy's manifest: relative paths this tool wrote. null when there is none. */
function readManifest(file) {
  if (!isFile(file)) return null;
  let m;
  try { m = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { throw new ConfigError(`manifest ${file} is not valid JSON (${e.message}) — fix or remove it by hand`); }
  if (m?.tool !== MANIFEST_TOOL || !Array.isArray(m.files)) throw new ConfigError(`manifest ${file} is not a make-clear manifest — fix or remove it by hand`);
  return m.files;
}

function main() {
  const startedAt = new Date().toISOString();
  const args = parseArgs(process.argv.slice(2), {
    config: 'string', dest: 'string', includeInternal: 'bool', allowExcludedLinks: 'bool', apply: 'bool', dryRun: 'bool', date: 'string', report: 'string',
  });
  if (args.help) { console.log(USAGE); return 0; }
  if (args._.length) throw new UsageError(`unexpected argument ${args._[0]}`);
  if (args.apply && args.dryRun) throw new UsageError('--apply and --dry-run together: pick one');
  args.dryRun = !args.apply; // DryRun is the default; only --apply writes
  if (args.date && !/^\d{4}-\d{2}-\d{2}$/.test(args.date)) throw new UsageError('--date expects YYYY-MM-DD');
  const cfg = loadConfig(args.config);
  if (!args.dest && !cfg.clearCopy) throw new UsageError('no destination: set "clearCopy" in the config or pass --dest <dir>');
  const dest = path.resolve(args.dest ? args.dest : path.resolve(cfg.outputRoot, cfg.clearCopy));
  const reportFile = args.report ? path.resolve(args.report)
    : args.dest ? `${dest}.make-clear-report.json` : path.join(cfg.reportDir, 'make-clear-report.json');

  // safety: stale-file removal walks the whole copy, so no source may live inside it
  if (samePath(dest, cfg.outputRoot) || inside(cfg.outputRoot, dest)) throw new ConfigError(`destination ${dest} equals or contains outputRoot ${cfg.outputRoot}`);
  for (const s of cfg.sets) {
    if (inside(s.dir, dest)) throw new ConfigError(`destination ${dest} equals or contains the directory of set "${s.id}" (${s.dir})`);
    const rel = path.relative(cfg.outputRoot, s.dir);
    if (rel.startsWith('..') || path.isAbsolute(rel)) throw new ConfigError(`set "${s.id}": dir ${s.dir} is outside outputRoot — the copy keeps paths relative to outputRoot`);
  }
  if (inside(cfg.reportDir, dest) && !args.report) throw new ConfigError(`reportDir ${cfg.reportDir} is inside the destination; pass --report`);

  // ownership: only what our manifest lists may ever be removed
  const manifestFile = `${dest}.make-clear-manifest.json`;
  const owned = readManifest(manifestFile);
  const existing = walk(dest);
  const ownedSet = new Set((owned || []).map((r) => norm(path.join(dest, r))));

  const nav = buildNav(cfg, { genDate: args.date, excludeInternal: !args.includeInternal });
  const LANGS = nav.LANGS;
  const findings = [];
  const warnings = [];
  const plan = new Map(); // norm(target) -> { target, source?, text?, kind, set }
  const excludedTargets = new Map(); // norm(target) -> "<set>:<name>"
  const add = (e) => plan.set(norm(e.target), e);
  const report = {
    tool: 'make-clear.mjs', config: cfg.file, dest, dryRun: !!args.dryRun, includeInternal: !!args.includeInternal,
    allowExcludedLinks: !!args.allowExcludedLinks, startedAt, sets: [],
  };

  for (const { g, html } of nav.outputs) {
    const set = g.set;
    const rel = path.relative(cfg.outputRoot, set.dir);
    const tdir = path.join(dest, rel);
    const sr = { id: set.id, source: set.dir, target: tdir, documents: [], excluded: [], diagrams: [], index: null };
    for (const i of g.issues) if (/^MISSING docx|^set directory not found/.test(i)) findings.push(`[${set.id}] ${i}`);
    for (const w of g.warnings) warnings.push(`[${set.id}] ${w}`);
    // documents
    for (const d of g.docs) {
      for (const l of LANGS) {
        const name = d.langs[l].name;
        if (!d.langs[l].info) continue; // reported above as MISSING docx
        add({ target: path.join(tdir, name), source: path.join(set.dir, name), kind: 'docx', set: set.id });
        sr.documents.push(name);
      }
    }
    for (const x of g.excluded) {
      for (const l of LANGS) {
        const name = `${x.base}_${cfg.suffix[l]}.docx`;
        excludedTargets.set(norm(path.join(tdir, name)), `${set.id}:${name}`);
        sr.excluded.push(name);
      }
    }
    // diagrams: every <prefix>*.html of the set dir (not visual-check, not "_")
    if (fs.existsSync(set.dir)) {
      const esc = set.diagramPrefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const re = new RegExp(`^${esc}.+\\.html$`);
      for (const f of fs.readdirSync(set.dir).sort()) {
        if (f.startsWith('_') || f.includes('.visual-check.') || !re.test(f) || !isFile(path.join(set.dir, f))) continue;
        add({ target: path.join(tdir, f), source: path.join(set.dir, f), kind: 'diagram', set: set.id });
        sr.diagrams.push(f);
      }
    }
    // index.html: byte copy when nothing is left out, else the filtered rendering
    const srcIndex = path.join(set.dir, 'index.html');
    if (!g.excluded.length && isFile(srcIndex)) {
      add({ target: path.join(tdir, 'index.html'), source: srcIndex, kind: 'index', set: set.id });
      sr.index = 'copied';
    } else {
      if (!g.excluded.length) warnings.push(`[${set.id}] ${srcIndex} not found — index.html of the copy is rendered (run make-nav for the set itself)`);
      add({ target: path.join(tdir, 'index.html'), text: html, kind: 'index', set: set.id });
      sr.index = g.excluded.length ? `rendered without ${g.excluded.map((x) => x.base).join(', ')}` : 'rendered';
    }
    report.sets.push(sr);
  }

  // No manifest: the destination is ours only if it holds nothing beyond the plan (an empty
  // directory, or a copy by an older make-clear with the same file set). Anything else is refused.
  if (!owned) {
    const extra = existing.filter((f) => !plan.has(norm(f)));
    if (extra.length) {
      throw new ConfigError(`destination ${dest} holds ${extra.length} file(s) outside the plan (e.g. ${path.relative(dest, extra[0])}) and has no make-clear manifest (${manifestFile}) — it is not ours to clean; pick an empty or new directory`);
    }
  }
  // ---- stale files (ours, no longer produced) and foreign files (never ours: left in place)
  const stale = existing.filter((f) => !plan.has(norm(f)) && ownedSet.has(norm(f)));
  const foreign = existing.filter((f) => !plan.has(norm(f)) && !ownedSet.has(norm(f)));
  for (const f of foreign) findings.push(`foreign file in the copy, not removed: ${path.relative(dest, f)}`);
  // ---- write
  const copied = []; const unchanged = [];
  if (!args.dryRun) {
    const emptied = [];
    for (const f of stale) { fs.unlinkSync(f); emptied.push(...removeEmptyParents(f, dest)); }
    report.removedDirs = emptied;
    for (const e of plan.values()) {
      const buf = e.source ? fs.readFileSync(e.source) : Buffer.from(e.text, 'utf8');
      if (isFile(e.target) && fs.readFileSync(e.target).equals(buf)) { unchanged.push(e.target); continue; }
      fs.mkdirSync(path.dirname(e.target), { recursive: true });
      fs.writeFileSync(e.target, buf);
      copied.push(e.target);
    }
    // the manifest records exactly what the copy now holds from us — the next run may remove only these
    const files = [...plan.values()].map((e) => path.relative(dest, e.target).split(path.sep).join('/')).sort();
    fs.writeFileSync(manifestFile, JSON.stringify({ tool: MANIFEST_TOOL, writtenAt: new Date().toISOString(), files }, null, 2) + '\n');
  }

  // ---- byte comparison (independent re-read of both sides)
  const mismatches = [];
  if (!args.dryRun) {
    for (const e of plan.values()) {
      const want = e.source ? sha(fs.readFileSync(e.source)) : sha(Buffer.from(e.text, 'utf8'));
      const got = isFile(e.target) ? sha(fs.readFileSync(e.target)) : null;
      if (want !== got) mismatches.push(path.relative(dest, e.target));
    }
    for (const m of mismatches) findings.push(`byte mismatch: ${m}`);
    const foreignSet = new Set(foreign.map(norm));
    const leftovers = walk(dest).filter((f) => !plan.has(norm(f)) && !foreignSet.has(norm(f)));
    for (const f of leftovers) findings.push(`unexpected file in the copy: ${path.relative(dest, f)}`);
  }

  // ---- links inside the copy (dry run: against the planned copy, reading the sources)
  const bytesOf = (e) => (!args.dryRun && isFile(e.target) ? fs.readFileSync(e.target) : e.source ? fs.readFileSync(e.source) : Buffer.from(e.text, 'utf8'));
  const links = { checked: 0, external: 0, ok: 0, broken: [], toExcluded: [] };
  const resolve = (from, href, what) => {
    if (!href || href.startsWith('#')) return;
    if (isExternal(href)) { links.external++; return; }
    links.checked++;
    const raw = href.split('#')[0].split('?')[0];
    const cands = [path.resolve(path.dirname(from), safeDecode(raw)), path.resolve(path.dirname(from), raw)];
    if (cands.some((c) => plan.has(norm(c)))) { links.ok++; return; }
    const ex = cands.map((c) => excludedTargets.get(norm(c))).find(Boolean);
    const rec = { from: path.relative(dest, from).split(path.sep).join('/'), href, via: what };
    if (ex) links.toExcluded.push({ ...rec, excluded: ex }); else links.broken.push(rec);
  };
  const htmlErrors = [];
  for (const e of plan.values()) {
    const buf = bytesOf(e);
    if (e.kind === 'index') {
      const hc = nav.checkHtml(buf.toString('utf8'));
      for (const err of hc.errors) htmlErrors.push(`${path.relative(dest, e.target)}: ${err}`);
      for (const h of hc.hrefs) resolve(e.target, decodeHtml(h), 'index href');
    } else if (e.kind === 'diagram') {
      for (const l of diagramLinks(buf.toString('utf8'))) resolve(e.target, l.href, l.attr);
    } else if (e.kind === 'docx') {
      let targets = [];
      try { targets = docxExternalTargets(buf); } catch (err) { findings.push(`${path.relative(dest, e.target)}: cannot read docx relationships (${err.message})`); }
      for (const t of targets) resolve(e.target, t.target, `docx ${t.part}`);
    }
  }
  for (const h of htmlErrors) findings.push(`index.html malformed: ${h}`);
  const grouped = (arr) => {
    const m = new Map();
    for (const b of arr) { const k = `${b.from} -> ${b.href}`; m.set(k, (m.get(k) || 0) + 1); }
    return [...m].map(([k, n]) => `${k}${n > 1 ? ` (×${n})` : ''}`);
  };
  for (const b of grouped(links.broken)) findings.push(`broken link: ${b}`);
  for (const b of grouped(links.toExcluded)) (args.allowExcludedLinks ? warnings : findings).push(`link to a left-out document${args.allowExcludedLinks ? ' (allowed)' : ''}: ${b}`);

  // ---- console + report
  console.log(`make-clear ${args.dryRun ? '(dry run) ' : ''}-> ${dest}${args.includeInternal ? ' · internal documents included' : ''}`);
  for (const s of report.sets) {
    console.log(`[${s.id}] ${path.relative(dest, s.target) || '.'}: index.html (${s.index}), ${s.diagrams.length} diagram(s), ${s.documents.length} docx`);
    if (s.excluded.length) console.log(`    left out (internalDocs): ${s.excluded.join(', ')}`);
  }
  const byKind = (k) => [...plan.values()].filter((e) => e.kind === k).length;
  const totalBytes = [...plan.values()].reduce((n, e) => n + (e.source ? fs.statSync(e.source).size : Buffer.byteLength(e.text)), 0);
  console.log(`files     : ${plan.size} (${byKind('index')} index, ${byKind('diagram')} diagrams, ${byKind('docx')} docx), ${totalBytes} bytes`);
  if (!args.dryRun) console.log(`written   : ${copied.length} copied/updated, ${unchanged.length} already identical; byte comparison: ${plan.size - mismatches.length}/${plan.size} identical`);
  console.log(`stale     : ${stale.length} file(s) of the previous copy ${args.dryRun ? 'would be removed' : 'removed'}${stale.length ? ':' : ''}`);
  for (const f of stale) console.log(`    - ${path.relative(dest, f)}`);
  if (foreign.length) console.log(`foreign   : ${foreign.length} file(s) not written by make-clear — left in place`);
  if (args.dryRun) console.log('DRY RUN   : nothing written. Re-run with --apply to write the copy.');
  const exSummary = new Map();
  for (const b of links.toExcluded) exSummary.set(b.excluded, (exSummary.get(b.excluded) || 0) + 1);
  console.log(`links     : ${links.checked} relative checked, ${links.ok} resolve inside the copy, ${links.broken.length} broken, ${links.toExcluded.length} to left-out documents${exSummary.size ? ` (${[...exSummary].map(([k, v]) => `${k} ×${v}`).join(', ')})` : ''}; ${links.external} external (not checked)`);
  for (const w of warnings) console.log(`warning   : ${w}`);
  for (const f of findings.slice(0, 60)) console.log(`FINDING   : ${f}`);
  if (findings.length > 60) console.log(`FINDING   : … ${findings.length - 60} more in the report`);
  const exitCode = findings.length ? 1 : 0;
  Object.assign(report, {
    finishedAt: new Date().toISOString(), exitCode,
    files: [...plan.values()].map((e) => ({ path: path.relative(dest, e.target).split(path.sep).join('/'), kind: e.kind, source: e.source || '(rendered)' })),
    totals: { files: plan.size, bytes: totalBytes, copied: copied.length, unchanged: unchanged.length, mismatches: mismatches.length },
    stale: stale.map((f) => path.relative(dest, f).split(path.sep).join('/')),
    foreign: foreign.map((f) => path.relative(dest, f).split(path.sep).join('/')),
    manifest: manifestFile, links, warnings, findings,
  });
  writeJsonReport(reportFile, report);
  console.log(`RESULT: ${exitCode ? 'findings (exit 1)' : 'clean (exit 0)'} · report ${reportFile}`);
  return exitCode;
}

runMain('make-clear', main);
