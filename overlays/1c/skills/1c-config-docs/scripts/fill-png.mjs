#!/usr/bin/env node
// fill-png.mjs — put the PNG of every diagram into the `diagram` blocks of the content JSON.
//
//   node fill-png.mjs --config <cfg.json> [<content.json> ...] [--dry-run] [--report <file>]
//
// For every block {"type": "diagram", "href": "<dir>/<name>.html", ...} whose href base name
// has a PNG <pngDir>/<name>.png, the block gets "png": "<path relative to the content file>".
// Nothing else changes: the file text is edited in place (the "png" value is replaced, or
// `"png": "…"` is inserted right after the href value with the same indentation), then the
// result is parsed and compared with the original — every value except those "png" fields
// must be identical, otherwise nothing is written (exit 2).
// A block whose "png" already resolves to that same file is left untouched.
//
// Files: the given content files (looked up in the cwd, then in contentDir), else every
// content file (<contentDir>/*.json + generated/, "_"-prefixed skipped).
// Exit codes: 0 = every diagram block has its PNG (filled or already there) · 1 = some block
// has no PNG in pngDir, or a content file is not valid JSON (the rest is still filled) ·
// 2 = execution/config error. Report: <reportDir>/fill-png-report.json (or --report).
import fs from 'node:fs';
import path from 'node:path';
import { loadConfig, parseArgs, runMain, UsageError, listContentFiles, samePath, writeJsonReport } from './lib/config.mjs';

const USAGE = 'usage: node fill-png.mjs --config <cfg.json> [<content.json> ...] [--dry-run] [--report <file>]';
const safeDecode = (s) => { try { return decodeURIComponent(s); } catch { return s; } };
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

// ---------------------------------------------------------------- JSON with positions
// Minimal RFC 8259 parser that keeps source offsets: objects -> { type, start, end, keys:
// [{ key, keyStart, keyEnd, value }] }, arrays -> { type, start, end, items }, scalars ->
// { type, start, end }. Used only to locate the text to edit; JSON.parse stays the judge.
function parsePositions(text) {
  let i = text.charCodeAt(0) === 0xfeff ? 1 : 0;
  const fail = (m) => { throw new SyntaxError(`${m} at offset ${i}`); };
  const ws = () => { while (i < text.length && ' \t\r\n'.includes(text[i])) i++; };
  const str = () => {
    const start = i;
    if (text[i] !== '"') fail('expected string');
    i++;
    while (i < text.length && text[i] !== '"') i += text[i] === '\\' ? 2 : 1;
    if (text[i] !== '"') fail('unterminated string');
    i++;
    return { type: 'string', start, end: i, value: JSON.parse(text.slice(start, i)) };
  };
  const value = () => {
    ws();
    const start = i;
    const c = text[i];
    if (c === '{') {
      i++;
      const node = { type: 'object', start, keys: [] };
      ws();
      if (text[i] === '}') { i++; node.end = i; return node; }
      for (;;) {
        ws();
        const k = str();
        ws();
        if (text[i] !== ':') fail('expected ":"');
        i++;
        const v = value();
        node.keys.push({ key: k.value, keyStart: k.start, keyEnd: k.end, value: v });
        ws();
        if (text[i] === ',') { i++; continue; }
        if (text[i] !== '}') fail('expected "," or "}"');
        i++; node.end = i; return node;
      }
    }
    if (c === '[') {
      i++;
      const node = { type: 'array', start, items: [] };
      ws();
      if (text[i] === ']') { i++; node.end = i; return node; }
      for (;;) {
        node.items.push(value());
        ws();
        if (text[i] === ',') { i++; continue; }
        if (text[i] !== ']') fail('expected "," or "]"');
        i++; node.end = i; return node;
      }
    }
    if (c === '"') return str();
    const m = /^(?:-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null)/.exec(text.slice(i, i + 64));
    if (!m) fail('unexpected token');
    i += m[0].length;
    return { type: 'scalar', start, end: i };
  };
  const root = value();
  ws();
  if (i !== text.length) fail('trailing content');
  return root;
}

const keyOf = (node, k) => (node && node.type === 'object' ? node.keys.find((x) => x.key === k) : undefined);

function deepEqual(a, b) {
  if (a === b) return true;
  if (Array.isArray(a)) return Array.isArray(b) && a.length === b.length && a.every((x, i) => deepEqual(x, b[i]));
  if (isObj(a)) {
    if (!isObj(b)) return false;
    const ka = Object.keys(a); const kb = Object.keys(b);
    return ka.length === kb.length && ka.every((k) => Object.prototype.hasOwnProperty.call(b, k) && deepEqual(a[k], b[k]));
  }
  return false;
}

// ---------------------------------------------------------------- one file
function fillFile(cfg, file) {
  const entry = { content: file, status: 'ok', blocks: [], changed: 0, missing: 0, errors: [], warnings: [] };
  const text = fs.readFileSync(file, 'utf8');
  let json; let tree;
  try { json = JSON.parse(text.replace(/^﻿/, '')); tree = parsePositions(text); } catch (e) {
    entry.status = 'invalid'; entry.errors.push(`not valid JSON: ${e.message}`); return { entry };
  }
  const blocksNode = keyOf(tree, 'blocks');
  if (!isObj(json) || !Array.isArray(json.blocks) || !blocksNode || blocksNode.value.type !== 'array') return { entry };
  const baseDir = path.dirname(file);
  const edits = [];
  const expected = JSON.parse(JSON.stringify(json));
  json.blocks.forEach((b, idx) => {
    if (!isObj(b) || b.type !== 'diagram') return;
    const where = `blocks[${idx}]`;
    const node = blocksNode.value.items[idx];
    if (typeof b.href !== 'string' || !b.href.trim()) { entry.warnings.push(`${where}: diagram block without href`); return; }
    const stem = path.basename(safeDecode(b.href.split('#')[0].split('?')[0])).replace(/\.[^.]+$/, '');
    const pngAbs = path.join(cfg.pngDir, `${stem}.png`);
    const rel = path.relative(baseDir, pngAbs).split(path.sep).join('/');
    const rec = { block: where, href: b.href, png: rel };
    const hasPng = fs.existsSync(pngAbs) && fs.statSync(pngAbs).isFile();
    const current = typeof b.png === 'string' ? b.png : null;
    // a png outside pngDir is acceptable only when it is the PNG of this very diagram (same base name)
    const currentExists = current !== null && fs.existsSync(path.resolve(baseDir, current));
    const currentOk = currentExists && path.basename(current).replace(/\.png$/i, '') === stem;
    if (!hasPng) {
      if (currentOk) {
        rec.action = 'kept'; rec.png = current;
        entry.warnings.push(`${where}: ${stem}.png is not in ${cfg.pngDir}; existing "png": "${current}" kept`);
      } else {
        rec.action = 'missing'; entry.missing++;
        if (current !== null) rec.was = current;
        const why = current === null ? '' : `; its "png": "${current}" is ${currentExists ? 'the PNG of another diagram' : 'not found'}`;
        entry.errors.push(`${where}: no PNG for ${b.href} (expected ${pngAbs})${why}`);
      }
      entry.blocks.push(rec);
      return;
    }
    if (current !== null && samePath(path.resolve(baseDir, current), pngAbs)) { rec.action = 'unchanged'; entry.blocks.push(rec); return; }
    rec.action = current === null ? 'added' : 'replaced';
    if (current !== null) rec.was = current;
    entry.blocks.push(rec);
    entry.changed++;
    expected.blocks[idx].png = rel;
    const lit = JSON.stringify(rel);
    const pngKey = keyOf(node, 'png');
    if (pngKey) { edits.push({ at: pngKey.value.start, end: pngKey.value.end, text: lit }); return; }
    const hrefKey = keyOf(node, 'href');
    const colon = text.slice(hrefKey.keyEnd, hrefKey.value.start); // `: ` as written
    const lineStart = text.lastIndexOf('\n', hrefKey.keyStart) + 1;
    const indent = text.slice(lineStart, hrefKey.keyStart);
    const multiLine = /^[ \t]*$/.test(indent) && text.slice(node.start, hrefKey.keyStart).includes('\n');
    const nl = text.includes('\r\n') ? '\r\n' : '\n';
    edits.push({ at: hrefKey.value.end, end: hrefKey.value.end, text: multiLine ? `,${nl}${indent}"png"${colon}${lit}` : `, "png"${colon}${lit}` });
  });
  if (entry.errors.length) entry.status = 'invalid';
  if (!edits.length) return { entry };
  let out = text;
  for (const e of edits.sort((a, b) => b.at - a.at)) out = out.slice(0, e.at) + e.text + out.slice(e.end);
  // the edit must change exactly the png fields: parse and compare with the expected object
  let back;
  try { back = JSON.parse(out.replace(/^﻿/, '')); } catch (e) { throw new Error(`${file}: edited text is not valid JSON (${e.message}) — nothing written`); }
  if (!deepEqual(back, expected)) throw new Error(`${file}: edited JSON differs from the original beyond the png fields — nothing written`);
  return { entry, out };
}

// ---------------------------------------------------------------- main
function main() {
  const startedAt = new Date().toISOString();
  const args = parseArgs(process.argv.slice(2), { config: 'string', dryRun: 'bool', report: 'string' });
  if (args.help) { console.log(USAGE); return 0; }
  const cfg = loadConfig(args.config);
  const reportFile = args.report ? path.resolve(args.report) : path.join(cfg.reportDir, 'fill-png-report.json');
  const files = [];
  for (const f of args._) {
    if (fs.existsSync(f)) files.push(path.resolve(f));
    else if (fs.existsSync(path.join(cfg.contentDir, f))) files.push(path.join(cfg.contentDir, f));
    else throw new UsageError(`content file not found: ${f} (also looked in ${cfg.contentDir})`);
  }
  if (!args._.length) files.push(...listContentFiles(cfg));
  if (!files.length) throw new UsageError(`no content files (contentDir ${cfg.contentDir})\n${USAGE}`);

  console.log(`fill-png ${args.dryRun ? '(dry run) ' : ''}· pngDir ${cfg.pngDir} · ${files.length} content file(s)`);
  const entries = [];
  for (const f of files) {
    const { entry, out } = fillFile(cfg, f);
    if (out !== undefined && !args.dryRun) {
      fs.writeFileSync(f, out, 'utf8');
      if (fs.readFileSync(f, 'utf8') !== out) throw new Error(`re-read mismatch after writing ${f}`);
      entry.written = true;
    }
    entries.push(entry);
    const diag = entry.blocks.length;
    if (!diag && !entry.errors.length) continue;
    const rel = path.relative(cfg.contentDir, f) || f;
    const st = entry.status === 'invalid' ? 'FAIL ' : entry.changed ? (args.dryRun ? 'WOULD' : 'FILL ') : 'OK   ';
    console.log(`${st} ${rel}: ${diag} diagram block(s), ${entry.changed} ${args.dryRun ? 'to change' : 'changed'}, ${entry.missing} without PNG`);
    for (const b of entry.blocks) if (b.action !== 'unchanged') console.log(`    ${b.block} ${b.action.padEnd(9)} ${b.png}${b.was ? `  (was ${b.was})` : ''}`);
    for (const e of entry.errors) console.log(`    x ${e}`);
    for (const w of entry.warnings) console.log(`    ! ${w}`);
  }
  const tot = (k) => entries.reduce((n, e) => n + e[k], 0);
  const blocks = entries.reduce((n, e) => n + e.blocks.length, 0);
  const exitCode = entries.some((e) => e.status === 'invalid') ? 1 : 0;
  writeJsonReport(reportFile, { tool: 'fill-png.mjs', config: cfg.file, dryRun: !!args.dryRun, startedAt, finishedAt: new Date().toISOString(), pngDir: cfg.pngDir, exitCode,
    totals: { files: entries.length, diagramBlocks: blocks, changed: tot('changed'), missing: tot('missing') }, files: entries });
  console.log(`exit ${exitCode}: ${blocks} diagram block(s) in ${entries.filter((e) => e.blocks.length).length} file(s); ${tot('changed')} ${args.dryRun ? 'would change' : 'changed'}; ${tot('missing')} without PNG · report ${reportFile}`);
  return exitCode;
}

runMain('fill-png', main);
