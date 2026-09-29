#!/usr/bin/env node
// check-lifecycle.mjs — lifecycle diagrams against the enumerations of the configuration.
//
//   node check-lifecycle.mjs --config <cfg.json> [<diagram.lifecycle.json> ...]
//                            [--inventory <inventory.json>] [--enum <stem>=<EnumName>]... [--report <file>]
//
// A lifecycle diagram (archify, diagram_type "lifecycle") should draw the values of one status
// enumeration. For each diagram the script finds that enumeration and compares the states with
// its values from inventory.json (value name and synonyms in every language of the dump):
//   * which enumeration: --enum <stem>=<Name> > names in meta.title / meta.subtitle > names in the
//     states' descriptions ("Объект 1С: …" / "Objeto 1C: …" / "Object 1C: …": `Перечисление.X.Y`,
//     `Enum.X.Y`, `Enumeración.X.Y`, or a `backticked` enum name) > the enum whose values match
//     most state labels (at least 2). archify's meta has no free keys, so the hint goes into
//     meta.subtitle (e.g. "Перечисление.СтатусыФайлов").
//   * a state is an enum value when its first description line names `<Enum>.<Value>` or its
//     label (or id) equals a value name / synonym (case, "ё"/"е", spaces and punctuation ignored).
//
// Marker convention for states that are NOT statuses (risks, situations, pseudo-states):
//   the state's `tag` contains "riesgo" / "риск" / "risk", or its id starts with "risk-".
//   type "start" is an entry point and needs no marker.
// Findings:
//   error   — a non-enum state that SAYS it is a risk / not a status (label, sublabel, lane label
//             or first description line: риск, risk, riesgo, «не статус», "not a status",
//             "no es un estado", «не значение перечисления», "pseudo") but has no marker;
//   warning — a non-enum state without marker and without such text (a situation drawn as a
//             status?), an enum value that carries the risk marker, enum values not shown,
//             a diagram whose enumeration cannot be identified.
// Exit codes: 0 = no errors (warnings allowed) · 1 = marker convention violated or a diagram
// unreadable · 2 = usage/config error, no inventory. Report: <reportDir>/lifecycle-report.json.
import fs from 'node:fs';
import path from 'node:path';
import { loadConfig, parseArgs, runMain, UsageError, ConfigError, writeJsonReport } from './lib/config.mjs';

const USAGE = 'usage: node check-lifecycle.mjs --config <cfg.json> [<diagram.lifecycle.json> ...] [--inventory <inventory.json>] [--enum <stem>=<EnumName>]... [--report <file>]';
const MARK_TAG_RE = /riesgo|риск|risk/i;
const HINT_RE = /риск|risk|riesgo|не\s+статус|not\s+a\s+status|no\s+es\s+(?:un\s+)?estado|не\s+значени[ея]\s+перечислени|pseudo|псевдо/i;
const OBJECT_LINE_RE = /^\s*(?:Объект\s+1[СC]|Objeto\s+1[СC]|Object\s+1[СC])\s*:/i;
const ENUM_REF_RE = /(?:Перечислени[ея]|Enums?|Enumeraci[oó]n(?:es)?)\.([\p{L}_][\p{L}\p{N}_]*)(?:\.([\p{L}_][\p{L}\p{N}_]*))?/gu;
const key = (s) => String(s || '').toLowerCase().replace(/ё/g, 'е').replace(/[^\p{L}\p{N}]/gu, '');
const firstLine = (d) => (Array.isArray(d) ? d[0] : typeof d === 'string' ? d : '') || '';

function main() {
  const startedAt = new Date().toISOString();
  const args = parseArgs(process.argv.slice(2), { config: 'string', inventory: 'string', enum: 'list', report: 'string' });
  if (args.help) { console.log(USAGE); return 0; }
  const cfg = loadConfig(args.config);
  const invFile = args.inventory ? path.resolve(args.inventory) : path.join(cfg.factsDir, 'inventory.json');
  let inv;
  try { inv = JSON.parse(fs.readFileSync(invFile, 'utf8')); } catch (e) { throw new ConfigError(`cannot read inventory ${invFile}: ${e.message}`); }
  if (!inv || !Array.isArray(inv.objects)) throw new ConfigError(`${invFile} is not an inventory.json`);
  const reportFile = args.report ? path.resolve(args.report) : path.join(cfg.reportDir, 'lifecycle-report.json');
  const overrides = new Map();
  for (const e of args.enum) {
    const m = /^([^=]+)=(.+)$/.exec(e);
    if (!m) throw new UsageError(`--enum expects <diagram stem>=<EnumName>, got "${e}"`);
    overrides.set(m[1].replace(/\.json$/, ''), m[2].replace(/^(?:Перечисление|Enum)\./, ''));
  }

  // enumerations: name -> { name, values: [{ name, keys:Set }] }
  const enums = new Map();
  for (const o of inv.objects.filter((x) => x.kind === 'Enum')) {
    const values = (o.values || []).map((v) => ({
      name: v.name,
      keys: new Set([v.name, ...Object.values(v.syn || {}), ...Object.entries(v).filter(([k]) => k.startsWith('name_')).map(([, x]) => x)].filter(Boolean).map(key)),
    }));
    enums.set(o.name, { name: o.name, values });
  }
  const enumByKey = new Map([...enums.keys()].map((n) => [key(n), n]));
  for (const [stem, n] of overrides) if (!enums.has(n)) throw new UsageError(`--enum ${stem}=${n}: no enumeration "${n}" in ${invFile}`);

  // diagrams
  const files = [];
  for (const f of args._) {
    if (!fs.existsSync(f)) throw new UsageError(`diagram not found: ${f}`);
    files.push(path.resolve(f));
  }
  if (!args._.length) {
    for (const s of cfg.sets) {
      if (!fs.existsSync(s.dir)) continue;
      for (const f of fs.readdirSync(s.dir).sort()) {
        if (f.startsWith('_') || f.includes('.visual-check.') || !f.startsWith(s.diagramPrefix) || !f.endsWith('.lifecycle.json')) continue;
        files.push(path.join(s.dir, f));
      }
    }
  }

  const results = [];
  for (const file of files) {
    const stem = path.basename(file).replace(/\.json$/, '');
    const r = { diagram: file, stem, enum: null, enumVia: null, states: [], missingValues: [], errors: [], warnings: [] };
    results.push(r);
    let j;
    try { j = JSON.parse(fs.readFileSync(file, 'utf8').replace(/^﻿/, '')); } catch (e) { r.errors.push(`not valid JSON: ${e.message}`); continue; }
    if (!Array.isArray(j.states)) { r.errors.push('no "states" array (is it a lifecycle diagram?)'); continue; }
    const lanes = new Map((j.lanes || []).map((l) => [l.id, l.label || '']));
    const meta = j.meta || {};

    // ---- which enumeration
    const mentions = new Map(); // enum -> weight
    const mention = (n, w) => { if (enums.has(n)) mentions.set(n, (mentions.get(n) || 0) + w); };
    const scanText = (t, w) => {
      for (const m of String(t).matchAll(ENUM_REF_RE)) mention(m[1], w);
      for (const m of String(t).matchAll(/`([^`]+)`/g)) { const n = enumByKey.get(key(m[1])); if (n && key(m[1]) === key(n)) mention(n, w); }
    };
    scanText(`${meta.title || ''} ${meta.subtitle || ''}`, 10);
    for (const s of j.states) { const d0 = firstLine(s.description); if (OBJECT_LINE_RE.test(d0)) scanText(d0, 1); }
    const labelScore = (n) => j.states.filter((s) => enums.get(n).values.some((v) => v.keys.has(key(s.label)) || v.keys.has(key(s.id)))).length;
    let chosen = null;
    if (overrides.has(stem)) { chosen = overrides.get(stem); r.enumVia = '--enum'; } else if (mentions.size) {
      chosen = [...mentions.keys()].sort((a, b) => (mentions.get(b) + labelScore(b)) - (mentions.get(a) + labelScore(a)) || (a < b ? -1 : 1))[0];
      r.enumVia = `named in the diagram (${[...mentions].map(([n, w]) => `${n}×${w}`).join(', ')})`;
    } else {
      const best = [...enums.keys()].map((n) => [n, labelScore(n)]).sort((a, b) => b[1] - a[1])[0];
      if (best && best[1] >= 2) { chosen = best[0]; r.enumVia = `best label match (${best[1]} states)`; }
    }
    r.enum = chosen;
    if (!chosen) r.warnings.push('no enumeration identified: name it in meta.subtitle ("Перечисление.<Имя>") or pass --enum');
    const E = chosen ? enums.get(chosen) : null;

    // ---- states
    const shown = new Set();
    for (const s of j.states) {
      const d0 = firstLine(s.description);
      const st = { id: s.id, label: s.label, type: s.type, lane: s.lane, tag: s.tag || null, class: null, value: null };
      if (E) {
        if (OBJECT_LINE_RE.test(d0)) {
          for (const m of d0.matchAll(ENUM_REF_RE)) if (m[1] === chosen && m[2] && E.values.some((v) => v.name === m[2])) { st.value = m[2]; break; }
        }
        if (!st.value) { const v = E.values.find((x) => x.keys.has(key(s.label)) || x.keys.has(key(s.id))); if (v) st.value = v.name; }
      }
      const marked = MARK_TAG_RE.test(s.tag || '') || /^risk-/i.test(s.id || '');
      const hintText = [s.label, s.sublabel, lanes.get(s.lane), d0].filter(Boolean).join(' · ');
      const hint = HINT_RE.exec(hintText);
      if (st.value) {
        shown.add(st.value);
        st.class = 'enum';
        if (marked) { st.class = 'enum-marked-risk'; r.warnings.push(`state "${s.id}" (${s.label}) is the enum value ${chosen}.${st.value} but carries the risk marker`); }
      } else if (marked) st.class = 'marked-risk';
      else if (s.type === 'start') st.class = 'entry';
      else if (hint) {
        st.class = 'violation';
        r.errors.push(`state "${s.id}" (${s.label}) is not a value of ${chosen || 'any identified enumeration'} and its text says so ("${hint[0]}" in: ${hintText.slice(0, 140)}), but it has no marker — add "риск"/"risk"/"riesgo" to its tag or start its id with "risk-"`);
      } else {
        st.class = 'unmarked';
        if (E) r.warnings.push(`state "${s.id}" (${s.label}) is not a value of ${chosen}: a status that the enumeration lacks, or a situation drawn as a status (mark it as a risk if it is one)`);
      }
      r.states.push(st);
    }
    if (E) r.missingValues = E.values.map((v) => v.name).filter((n) => !shown.has(n));
    if (r.missingValues.length) r.warnings.push(`values of ${chosen} not shown: ${r.missingValues.join(', ')}`);
  }

  // ---- output
  console.log(`check-lifecycle · ${files.length} lifecycle diagram(s) · inventory ${invFile}`);
  for (const r of results) {
    console.log('');
    const n = (c) => r.states.filter((s) => s.class === c).length;
    console.log(`${r.errors.length ? 'FAIL' : r.warnings.length ? 'WARN' : 'OK  '} ${r.stem}`);
    console.log(`     enumeration: ${r.enum || '—'}${r.enumVia ? ` (${r.enumVia})` : ''}`);
    if (r.states.length) {
      console.log(`     states: ${r.states.length} — ${n('enum')} enum values, ${n('marked-risk')} marked risks, ${n('entry')} entry, ${n('unmarked')} unmarked non-enum, ${n('violation')} marker violations${n('enum-marked-risk') ? `, ${n('enum-marked-risk')} enum values marked as risk` : ''}`);
      for (const s of r.states) console.log(`       ${s.class.padEnd(16)} ${String(s.id).padEnd(12)} ${s.label}${s.value ? `  = ${r.enum}.${s.value}` : ''}${s.tag ? `  [tag: ${s.tag}]` : ''}`);
    }
    for (const e of r.errors) console.log(`     x ${e}`);
    for (const w of r.warnings) console.log(`     ! ${w}`);
  }
  const errors = results.reduce((k, r) => k + r.errors.length, 0);
  const warnings = results.reduce((k, r) => k + r.warnings.length, 0);
  const exitCode = errors ? 1 : 0;
  writeJsonReport(reportFile, { tool: 'check-lifecycle.mjs', config: cfg.file, inventory: invFile, startedAt, finishedAt: new Date().toISOString(), exitCode,
    convention: { markerTag: MARK_TAG_RE.source, markerIdPrefix: 'risk-', hint: HINT_RE.source }, totals: { diagrams: results.length, errors, warnings }, diagrams: results });
  console.log('');
  console.log(`exit ${exitCode}: ${results.length} diagram(s), ${errors} error(s), ${warnings} warning(s) · report ${reportFile}`);
  return exitCode;
}

runMain('check-lifecycle', main);
