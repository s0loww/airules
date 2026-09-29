#!/usr/bin/env node
// callgraph.mjs — who calls what in a 1C configuration dump: an aid for analysts
// ("confirmed by a call site"), not a compiler. Fast, deterministic, language-agnostic
// (Russian and English BSL keywords).
//
//   node callgraph.mjs --config <cfg.json> [--src-root <dir>] [--out <dir>] [--max-sites <n>]
//
// Reads every *.bsl under the dump (source.srcRoot, or --src-root) — common, object, manager,
// record set, command and FORM modules alike — plus the XML of event subscriptions, scheduled
// jobs, enumerations, constants and forms. Writes <out>/callgraph.json and
// <out>/callgraph-summary.md (<out> = --out, else <outputRoot>/<factsDir>).
//
// What is counted:
//   * exported procedures/functions of common modules (`Процедура|Функция|Procedure|Function
//     Имя(…) Экспорт|Export`): definition file:line; call sites `Модуль.Имя(` from any module
//     (external), `Имя(` inside the same module (internal), `Имя(` from any module for a
//     Global module; metadata references (event subscription Handler, scheduled job
//     MethodName); string references ("Модуль.Имя" literals, `ОписаниеОповещения("Имя", Модуль)`
//     / `NotifyDescription`). Every site carries file, line, module and enclosing procedure.
//   * enumeration values: `Перечисления.X.Y` / `Enums.X.Y` in code, `Перечисление.X.Y` /
//     `Enum.X.Y` in query texts and strings, `Enum.X.EnumValue.Y` / query texts in XML (forms,
//     templates, DCS, predefined data).
//   * constants: `Константы.X.Установить(` / `.Set(` (write), `.СоздатьМенеджерЗначения(` /
//     `.CreateValueManager(` (write through a value manager), `.Получить(` / `.Get(` (read),
//     any other `Константы.X` / `Константа.X` (query field and the like: "other"), and form
//     fields bound to a ConstantsSet attribute (read + write through the UI: "ui").
// Lists: exported methods with no external call site and no metadata/string reference
// (`unusedExports`), exported methods referenced only by metadata or strings, enum values never
// referenced in BSL or XML, constants never written (no write, no manager, not on a form) and
// never read (no read, no other reference, not on a form), constants not on any form.
//
// Limits (say so when citing it): dynamic calls are invisible — `Выполнить`/`Execute`,
// `Вычислить`/`Eval`, `ОбщегоНазначения.ОбщийМодуль("…")`, `ВыполнитьМетодКонфигурации`, methods
// called through a variable holding a module, `Перечисления.X[Имя]`, iterating metadata;
// a local procedure with the same name as an export of a global module shadows it (handled per
// module); comments and string literals are blanked before call matching, so commented-out calls
// do not count; the dump of an extension sees only the extension's own code.
//
// Exit codes: 0 = written · 1 = some files could not be read (still written) · 2 = config error.
import fs from 'node:fs';
import path from 'node:path';
import { loadConfig, parseArgs, runMain, UsageError, ConfigError, writeJsonReport } from './lib/config.mjs';

const USAGE = 'usage: node callgraph.mjs --config <cfg.json> [--src-root <dir>] [--out <dir>] [--max-sites <n>]';
const ID = '[\\p{L}_][\\p{L}\\p{N}_]*';
const NB = '(?<![\\p{L}\\p{N}_.&#~])'; // not preceded by an identifier char, "." or an annotation/preprocessor sign
const FOLDER_KIND = {
  Catalogs: 'Catalog', Documents: 'Document', InformationRegisters: 'InformationRegister', AccumulationRegisters: 'AccumulationRegister',
  AccountingRegisters: 'AccountingRegister', CalculationRegisters: 'CalculationRegister', ChartsOfAccounts: 'ChartOfAccounts',
  ChartsOfCharacteristicTypes: 'ChartOfCharacteristicTypes', ChartsOfCalculationTypes: 'ChartOfCalculationTypes', Enums: 'Enum', Reports: 'Report',
  DataProcessors: 'DataProcessor', CommonModules: 'CommonModule', CommonForms: 'CommonForm', CommonCommands: 'CommonCommand', Constants: 'Constant',
  ExchangePlans: 'ExchangePlan', HTTPServices: 'HTTPService', WebServices: 'WebService', DocumentJournals: 'DocumentJournal',
  BusinessProcesses: 'BusinessProcess', Tasks: 'Task', FilterCriteria: 'FilterCriterion', Sequences: 'Sequence', SettingsStorages: 'SettingsStorage',
};
const lc = (s) => s.toLowerCase();

// ---------------------------------------------------------------- text preparation
// Returns { code, noComments }: `code` has comments AND string/date literals blanked (spaces,
// newlines kept -> offsets and line numbers stay valid); `noComments` keeps the literals.
function prepare(src) {
  const n = src.length;
  const code = src.split('');
  const noc = src.split('');
  let i = 0;
  while (i < n) {
    const ch = src[i];
    if (ch === '/' && src[i + 1] === '/') {
      while (i < n && src[i] !== '\n') { if (src[i] !== '\r') { code[i] = ' '; noc[i] = ' '; } i++; }
      continue;
    }
    if (ch === '"' || ch === "'") {
      const q = ch;
      i++;
      while (i < n) {
        if (src[i] === q) { if (q === '"' && src[i + 1] === '"') { code[i] = ' '; code[i + 1] = ' '; i += 2; continue; } break; }
        if (src[i] !== '\n' && src[i] !== '\r') code[i] = ' ';
        i++;
      }
      i++;
      continue;
    }
    i++;
  }
  return { code: code.join(''), noComments: noc.join('') };
}

function lineIndex(text) {
  const starts = [0];
  for (let i = 0; i < text.length; i++) if (text.charCodeAt(i) === 10) starts.push(i + 1);
  return (off) => { let lo = 0; let hi = starts.length - 1; while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (starts[mid] <= off) lo = mid; else hi = mid - 1; } return lo + 1; };
}

// module identity from the path relative to the dump root
function moduleOf(rel) {
  const s = rel.split('/');
  if (s[0] === 'Ext') return { module: `Configuration.${s[1].replace(/\.bsl$/, '')}`, kind: 'ConfigurationModule' };
  const kind = FOLDER_KIND[s[0]] || s[0];
  const obj = s[1];
  if (s[0] === 'CommonModules') return { module: obj, kind: 'CommonModule', common: obj };
  const fi = s.indexOf('Forms');
  if (fi >= 0 && s[fi + 1]) return { module: `${kind}.${obj}.Form.${s[fi + 1]}`, kind: 'FormModule' };
  if (s[0] === 'CommonForms') return { module: `CommonForm.${obj}`, kind: 'FormModule' };
  const ci = s.indexOf('Commands');
  if (ci >= 0 && s[ci + 1]) return { module: `${kind}.${obj}.Command.${s[ci + 1]}`, kind: 'CommandModule' };
  if (s[0] === 'CommonCommands') return { module: `CommonCommand.${obj}`, kind: 'CommandModule' };
  const file = s[s.length - 1].replace(/\.bsl$/, '');
  return { module: `${kind}.${obj}.${file}`, kind: file };
}

function listFiles(dir, ext, rel = '', out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const d of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))) {
    const r = rel ? `${rel}/${d.name}` : d.name;
    if (d.isDirectory()) listFiles(path.join(dir, d.name), ext, r, out);
    else if (d.isFile() && d.name.toLowerCase().endsWith(ext)) out.push(r);
  }
  return out;
}

// ---------------------------------------------------------------- main
function main() {
  const t0 = Date.now();
  const args = parseArgs(process.argv.slice(2), { config: 'string', srcRoot: 'string', out: 'string', maxSites: 'string' });
  if (args.help) { console.log(USAGE); return 0; }
  if (args._.length) throw new UsageError(`unexpected argument ${args._[0]}`);
  const cfg = loadConfig(args.config);
  const root = args.srcRoot ? path.resolve(args.srcRoot) : cfg.source.srcRoot;
  if (!root || !fs.existsSync(root) || !fs.statSync(root).isDirectory()) throw new ConfigError(`source root not found: ${root} (source.worktree + source.srcRoot, or --src-root)`);
  const outDir = args.out ? path.resolve(args.out) : cfg.factsDir;
  const maxSites = args.maxSites ? Number(args.maxSites) : 200;
  if (!Number.isInteger(maxSites) || maxSites < 1) throw new UsageError('--max-sites expects a positive integer');
  const lang = (cfg.raw.inventory && cfg.raw.inventory.summaryLanguage) === 'ru' ? 'ru' : 'en';
  const problems = [];
  const read = (rel) => { try { return fs.readFileSync(path.join(root, rel), 'utf8').replace(/^﻿/, ''); } catch (e) { problems.push(`${rel}: ${e.message}`); return null; } };

  // ---- sources
  const bslFiles = listFiles(root, '.bsl');
  const xmlFiles = listFiles(root, '.xml');
  const files = [];
  let lines = 0;
  for (const rel of bslFiles) {
    const src = read(rel);
    if (src === null) continue;
    const { code, noComments } = prepare(src);
    const m = moduleOf(rel);
    files.push({ rel, ...m, code, noComments, line: lineIndex(src) });
    lines += (src.match(/\n/g) || []).length + 1;
  }

  // ---- common modules: global flag from XML
  const commons = new Map(); // lc name -> { name, global, file, exports: Map lc proc -> rec, procs: Set lc }
  for (const rel of xmlFiles.filter((f) => /^CommonModules\/[^/]+\.xml$/.test(f))) {
    const x = read(rel);
    const name = rel.slice('CommonModules/'.length, -4);
    commons.set(lc(name), { name, global: !!x && /<Global>true<\/Global>/.test(x), file: null, exports: new Map(), procs: new Set() });
  }

  // ---- definitions (every module): procedures with ranges; exports of common modules
  const DEF_RE = new RegExp(`^[ \\t]*(Процедура|Функция|Procedure|Function)[ \\t]+(${ID})[ \\t]*\\(`, 'gimu');
  const END_RE = /^[ \t]*(КонецПроцедуры|КонецФункции|EndProcedure|EndFunction)\b/gimu;
  for (const f of files) {
    f.procs = [];
    for (const m of f.code.matchAll(DEF_RE)) {
      // parameters: up to the matching ")" (literals are blanked, so no quotes to worry about)
      let depth = 0; let j = m.index + m[0].length - 1;
      for (; j < f.code.length; j++) { if (f.code[j] === '(') depth++; else if (f.code[j] === ')' && --depth === 0) break; }
      const after = f.code.slice(j + 1, j + 200);
      const exported = /^[ \t]*(Экспорт|Export)(?![\p{L}\p{N}_])/iu.test(after);
      f.procs.push({ name: m[2], kind: /^(Функция|Function)$/i.test(m[1]) ? 'Function' : 'Procedure', line: f.line(m.index + m[0].search(/\S/)), exported, params: f.code.slice(m.index + m[0].length, j).replace(/\s+/g, ' ').trim() });
    }
    f.ends = [...f.code.matchAll(END_RE)].map((m) => f.line(m.index + m[0].search(/\S/)));
    f.procSet = new Set(f.procs.map((p) => lc(p.name)));
    if (f.kind === 'CommonModule') {
      const c = commons.get(lc(f.common)) || { name: f.common, global: false, exports: new Map(), procs: new Set() };
      commons.set(lc(f.common), c);
      c.file = f.rel; c.procs = f.procSet;
      for (const p of f.procs) if (p.exported) c.exports.set(lc(p.name), { ...p, file: f.rel, external: [], internal: [], metadata: [], strings: [] });
    }
  }
  const callerOf = (f, ln) => {
    let best = null;
    for (const p of f.procs) if (p.line <= ln && (!best || p.line > best.line)) best = p;
    if (!best) return null;
    const end = f.ends.find((e) => e >= best.line);
    return end !== undefined && end < ln ? null : best.name;
  };
  const site = (f, off, via) => { const ln = f.line(off); return { file: f.rel, line: ln, module: f.module, caller: callerOf(f, ln), via }; };
  const globals = [...commons.values()].filter((c) => c.global);

  // ---- call sites
  const QUAL_RE = new RegExp(`${NB}(${ID})[ \\t]*\\.[ \\t]*(${ID})[ \\t]*\\(`, 'gu');
  const UNQ_RE = new RegExp(`${NB}(${ID})[ \\t]*\\(`, 'gu');
  const DEF_WORD_RE = /(Процедура|Функция|Procedure|Function)[ \t]+$/i;
  for (const f of files) {
    for (const m of f.code.matchAll(QUAL_RE)) {
      const c = commons.get(lc(m[1]));
      const e = c && c.exports.get(lc(m[2]));
      if (!e) continue;
      (f.kind === 'CommonModule' && lc(f.common) === lc(c.name) ? e.internal : e.external).push(site(f, m.index + m[0].search(/\S/), 'qualified'));
    }
    const own = f.kind === 'CommonModule' ? commons.get(lc(f.common)) : null;
    for (const m of f.code.matchAll(UNQ_RE)) {
      const name = lc(m[1]);
      if (DEF_WORD_RE.test(f.code.slice(Math.max(0, m.index - 20), m.index + (m[0].length - m[0].trimStart().length)))) continue; // the definition itself
      if (own && own.exports.has(name)) { own.exports.get(name).internal.push(site(f, m.index + m[0].search(/\S/), 'unqualified')); continue; }
      if (f.procSet.has(name)) continue; // a local procedure shadows global-module exports
      for (const g of globals) {
        if (own && g === own) continue;
        const e = g.exports.get(name);
        if (e) e.external.push(site(f, m.index + m[0].search(/\S/), 'global'));
      }
    }
    // string references: "Module.Proc" literals; ОписаниеОповещения("Proc", Module)
    for (const m of f.noComments.matchAll(new RegExp(`"(${ID})\\.(${ID})"`, 'gu'))) {
      const c = commons.get(lc(m[1])); const e = c && c.exports.get(lc(m[2]));
      if (e) e.strings.push(site(f, m.index, 'string "Module.Proc"'));
    }
    for (const m of f.noComments.matchAll(new RegExp(`(?:ОписаниеОповещения|NotifyDescription)\\s*\\(\\s*"(${ID})"\\s*,\\s*(${ID})`, 'giu'))) {
      const c = commons.get(lc(m[2])); const e = c && c.exports.get(lc(m[1]));
      if (e) e.strings.push(site(f, m.index, 'NotifyDescription'));
    }
  }

  // ---- metadata references (event subscriptions, scheduled jobs)
  for (const rel of xmlFiles.filter((f) => /^(EventSubscriptions|ScheduledJobs)\/[^/]+\.xml$/.test(f))) {
    const x = read(rel);
    if (!x) continue;
    for (const m of x.matchAll(/<(Handler|MethodName)>CommonModule\.([^.<\s]+)\.([^<\s]+)<\/\1>/g)) {
      const c = commons.get(lc(m[2])); const e = c && c.exports.get(lc(m[3]));
      const ref = { file: rel, line: x.slice(0, m.index).split('\n').length, module: `${rel.startsWith('Event') ? 'EventSubscription' : 'ScheduledJob'}.${path.basename(rel, '.xml')}`, via: m[1] };
      if (e) e.metadata.push(ref); else problems.push(`${rel}: ${m[1]} CommonModule.${m[2]}.${m[3]} — no such exported method in the dump`);
    }
  }

  // ---- enumerations
  const enums = new Map(); // lc enum -> { name, values: Map lc -> { name, bsl: [], xml: [] } }
  for (const rel of xmlFiles.filter((f) => /^Enums\/[^/]+\.xml$/.test(f))) {
    const x = read(rel);
    if (!x) continue;
    const name = path.basename(rel, '.xml');
    const values = new Map();
    for (const m of x.matchAll(/<EnumValue\b[^>]*>\s*<Properties>\s*<Name>([^<]+)<\/Name>/g)) values.set(lc(m[1]), { name: m[1], bsl: [], xml: [] });
    enums.set(lc(name), { name, values });
  }
  const ENUM_RE = new RegExp(`(?<![\\p{L}\\p{N}_])(?:Перечисления|Перечисление|Enums|Enum)\\s*\\.\\s*(${ID})\\s*\\.\\s*(?:EnumValue\\s*\\.\\s*)?(${ID})`, 'giu');
  // aliases: `Статусы = Перечисления.X;` then `Статусы.Y` (the nearest preceding assignment of the
  // alias in the file wins); dynamic access `Перечисления.X[…]` / `Метаданные.Перечисления.X` is flagged
  const ALIAS_RE = new RegExp(`(?<![\\p{L}\\p{N}_.])(${ID})\\s*=\\s*(?:Перечисления|Enums)\\s*\\.\\s*(${ID})\\s*(?![\\s.\\[\\p{L}\\p{N}_])`, 'giu');
  const DYN_RE = new RegExp(`(?:(?<![\\p{L}\\p{N}_.])(?:Перечисления|Enums)\\s*\\.\\s*(${ID})\\s*\\[|(?:Метаданные|Metadata)\\s*\\.\\s*(?:Перечисления|Enums)\\s*\\.\\s*(${ID}))`, 'giu');
  for (const f of files) {
    for (const m of f.noComments.matchAll(ENUM_RE)) {
      const v = enums.get(lc(m[1]))?.values.get(lc(m[2]));
      if (v) v.bsl.push(site(f, m.index, 'code/query'));
    }
    const assigns = [...f.code.matchAll(ALIAS_RE)].filter((m) => enums.has(lc(m[2]))).map((m) => ({ alias: lc(m[1]), en: enums.get(lc(m[2])), at: m.index }));
    for (const a of new Set(assigns.map((x) => x.alias))) {
      const esc = a.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      for (const m of f.code.matchAll(new RegExp(`(?<![\\p{L}\\p{N}_.])${esc}\\s*\\.\\s*(${ID})`, 'giu'))) {
        const last = assigns.filter((x) => x.alias === a && x.at < m.index).pop();
        const v = last && last.en.values.get(lc(m[1]));
        if (v) v.bsl.push(site(f, m.index, `alias ${m[0].split('.')[0].trim()} = Перечисления.${last.en.name}`));
      }
    }
    for (const m of f.code.matchAll(DYN_RE)) {
      const en = enums.get(lc(m[1] || m[2]));
      if (en) (en.dynamic ||= []).push(site(f, m.index, m[1] ? 'Перечисления.X[…]' : 'Метаданные.Перечисления.X'));
    }
  }
  // Not references: the enum's own descriptor, and ConfigDumpInfo.xml — the dump's table of
  // contents lists every value of every enum, so scanning it made every value "referenced".
  const xmlScan = xmlFiles.filter((f) => !/^(Enums)\/[^/]+\.xml$/.test(f) && !/(^|\/)ConfigDumpInfo\.xml$/i.test(f));
  const lineOfXml = (x, off) => x.slice(0, off).split('\n').length;

  // ---- constants
  const consts = new Map(); // lc -> { name, write: [], manager: [], read: [], other: [], ui: [] }
  for (const rel of xmlFiles.filter((f) => /^Constants\/[^/]+\.xml$/.test(f))) {
    const name = path.basename(rel, '.xml');
    consts.set(lc(name), { name, write: [], manager: [], read: [], other: [], ui: [] });
  }
  const CONST_RE = new RegExp(`(?<![\\p{L}\\p{N}_.])(?:Константы|Константа|Constants|Constant)\\s*\\.\\s*(${ID})(?:\\s*\\.\\s*(${ID})\\s*\\()?`, 'giu');
  for (const f of files) {
    for (const m of f.noComments.matchAll(CONST_RE)) {
      const c = consts.get(lc(m[1]));
      if (!c) continue;
      const meth = m[2] ? lc(m[2]) : '';
      const s = site(f, m.index, meth || 'reference');
      if (meth === 'установить' || meth === 'set') c.write.push(s);
      else if (meth === 'создатьменеджерзначения' || meth === 'createvaluemanager') c.manager.push(s);
      else if (meth === 'получить' || meth === 'get') c.read.push(s);
      else c.other.push(s);
    }
  }
  // XML: enum references anywhere; constants bound to ConstantsSet form attributes; constant refs in query texts
  for (const rel of xmlScan) {
    const x = read(rel);
    if (!x) continue;
    if (/Enum|Перечислен/.test(x)) {
      for (const m of x.matchAll(ENUM_RE)) {
        const v = enums.get(lc(m[1]))?.values.get(lc(m[2]));
        if (v) v.xml.push({ file: rel, line: lineOfXml(x, m.index), via: 'xml' });
      }
    }
    if (/Form\.xml$/.test(rel) && x.includes('ConstantsSet')) {
      const attrs = [...x.matchAll(/<Attribute\s+name="([^"]+)"[^>]*>(?:(?!<\/Attribute>)[\s\S])*?cfg:ConstantsSet/g)].map((m) => m[1]);
      for (const a of attrs) {
        const esc = a.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        for (const m of x.matchAll(new RegExp(`<DataPath>(?:\\d+\\/)?${esc}\\.([^<.]+)<\\/DataPath>`, 'g'))) {
          const c = consts.get(lc(m[1]));
          if (c) c.ui.push({ file: rel, line: lineOfXml(x, m.index), via: `form field ${a}.${m[1]}` });
        }
      }
    }
    if (/Template\.xml$|Form\.xml$/.test(rel) && /Констант|Constant/.test(x)) {
      for (const m of x.matchAll(CONST_RE)) {
        const c = consts.get(lc(m[1]));
        if (c && !m[2]) c.other.push({ file: rel, line: lineOfXml(x, m.index), via: 'xml query/reference' });
      }
    }
  }

  // ---- results
  const cap = (arr) => (arr.length > maxSites ? arr.slice(0, maxSites) : arr);
  const modules = {};
  const unusedExports = []; const metadataOnly = [];
  for (const c of [...commons.values()].sort((a, b) => (a.name < b.name ? -1 : 1))) {
    if (!c.file) continue;
    const ex = [...c.exports.values()].sort((a, b) => a.line - b.line);
    modules[c.name] = {
      file: c.file, global: c.global, exports: ex.map((e) => ({
        name: e.name, kind: e.kind, line: e.line, params: e.params,
        counts: { external: e.external.length, internal: e.internal.length, metadata: e.metadata.length, strings: e.strings.length },
        external: cap(e.external), internal: cap(e.internal), metadata: e.metadata, strings: cap(e.strings),
      })),
    };
    for (const e of ex) {
      const id = `${c.name}.${e.name}`;
      if (!e.external.length && !e.metadata.length && !e.strings.length) unusedExports.push({ method: id, file: `${c.file}:${e.line}`, internalCalls: e.internal.length });
      else if (!e.external.length) metadataOnly.push({ method: id, file: `${c.file}:${e.line}`, metadata: e.metadata.length, strings: e.strings.length });
    }
  }
  const enumsOut = {}; const unreferencedEnumValues = []; const enumValuesOnlyInXml = [];
  for (const en of [...enums.values()].sort((a, b) => (a.name < b.name ? -1 : 1))) {
    enumsOut[en.name] = { dynamicAccess: (en.dynamic || []).length, dynamicSites: cap(en.dynamic || []), values: {} };
    const dyn = (en.dynamic || []).length ? ` (enum accessed dynamically: ${[...new Set(en.dynamic.map((s) => `${s.file}:${s.line}`))].slice(0, 3).join(', ')})` : '';
    for (const v of en.values.values()) {
      enumsOut[en.name].values[v.name] = { bsl: v.bsl.length, xml: v.xml.length, sites: cap([...v.bsl, ...v.xml]) };
      if (!v.bsl.length && !v.xml.length) unreferencedEnumValues.push(`${en.name}.${v.name}${dyn}`);
      else if (!v.bsl.length) enumValuesOnlyInXml.push(`${en.name}.${v.name}`);
    }
  }
  const constsOut = {}; const neverWritten = []; const neverRead = []; const notOnForms = [];
  for (const c of [...consts.values()].sort((a, b) => (a.name < b.name ? -1 : 1))) {
    constsOut[c.name] = { write: c.write.length, manager: c.manager.length, read: c.read.length, other: c.other.length, ui: c.ui.length,
      sites: cap([...c.write, ...c.manager, ...c.read, ...c.other, ...c.ui]) };
    if (!c.write.length && !c.manager.length && !c.ui.length) neverWritten.push(c.name);
    if (!c.read.length && !c.other.length && !c.ui.length) neverRead.push(c.name);
    if (!c.ui.length) notOnForms.push(c.name);
  }
  const exportsTotal = Object.values(modules).reduce((n, m) => n + m.exports.length, 0);
  const header = {
    tool: 'callgraph.mjs', config: cfg.file, srcRoot: root, generatedAt: new Date().toISOString(), ms: Date.now() - t0,
    bslFiles: files.length, bslLines: lines, xmlFiles: xmlFiles.length, commonModules: Object.keys(modules).length, exports: exportsTotal,
    enums: enums.size, constants: consts.size, maxSitesPerList: maxSites,
    limits: 'dynamic calls (Выполнить/Execute, Вычислить/Eval, ОбщийМодуль("…"), method via a variable), Перечисления.X[Имя], metadata iteration are not seen; comments and literals are blanked before call matching',
  };
  const result = { header, modules, unusedExports, metadataOnlyExports: metadataOnly, enums: enumsOut, unreferencedEnumValues, enumValuesOnlyInXml,
    constants: constsOut, constantsNeverWritten: neverWritten, constantsNeverRead: neverRead, constantsNotOnForms: notOnForms, problems };

  fs.mkdirSync(outDir, { recursive: true });
  const outJson = path.join(outDir, 'callgraph.json');
  const outMd = path.join(outDir, 'callgraph-summary.md');
  const jsonText = JSON.stringify(result, null, 1) + '\n';
  fs.writeFileSync(outJson, jsonText, 'utf8');
  fs.writeFileSync(outMd, summary(lang, result), 'utf8');
  const back = JSON.parse(fs.readFileSync(outJson, 'utf8'));
  if (Object.keys(back.modules).length !== Object.keys(modules).length) throw new Error('re-read mismatch of callgraph.json');

  console.log(`callgraph · ${root}`);
  console.log(`  ${files.length} BSL files (${lines} lines), ${xmlFiles.length} XML; ${Object.keys(modules).length} common modules, ${exportsTotal} exported methods, ${enums.size} enums, ${consts.size} constants · ${Date.now() - t0} ms`);
  console.log(`  exported without external call sites: ${unusedExports.length}; referenced only by metadata/strings: ${metadataOnly.length}`);
  console.log(`  enum values never referenced: ${unreferencedEnumValues.length}; only in XML: ${enumValuesOnlyInXml.length}`);
  console.log(`  constants never written: ${neverWritten.length}; never read: ${neverRead.length}; not on any form: ${notOnForms.length}`);
  for (const p of problems) console.log(`  problem: ${p}`);
  console.log(`  wrote ${outJson}`);
  console.log(`  wrote ${outMd}`);
  const exitCode = problems.some((p) => !/no such exported method/.test(p)) ? 1 : 0;
  console.log(`exit ${exitCode}`);
  return exitCode;
}

// ---------------------------------------------------------------- markdown summary
const MD = {
  en: {
    title: '# Call graph — summary', src: 'Source', gen: 'Generated', counts: 'Counts',
    limits: 'Limits: dynamic calls (`Выполнить`/`Execute`, `Вычислить`/`Eval`, `ОбщегоНазначения.ОбщийМодуль("…")`, a method called through a variable), `Перечисления.X[Имя]` and metadata iteration are invisible. "No call site" is a lead to check, not a verdict.',
    unusedH: '## Exported methods without external call sites', unusedNote: 'No call from another module, no event subscription / scheduled job, no string reference. "internal" = calls inside its own module.',
    metaH: '## Exported methods referenced only by metadata or strings', enumH: '## Enum values never referenced (BSL and XML)', enumXmlH: '## Enum values referenced only in XML (forms, templates, DCS)',
    cwH: '## Constants never written (no Set, no value manager, not on a form)', crH: '## Constants never read (no Get, no other reference, not on a form)', cfH: '## Constants not on any form (set only in code, if at all)',
    colMethod: 'Method', colDef: 'Definition', colInt: 'internal', colMeta: 'metadata', colStr: 'strings', none: '_(none)_',
  },
  ru: {
    title: '# Граф вызовов — сводка', src: 'Источник', gen: 'Сгенерировано', counts: 'Счётчики',
    limits: 'Ограничения: не видны динамические вызовы (`Выполнить`, `Вычислить`, `ОбщегоНазначения.ОбщийМодуль("…")`, метод через переменную), `Перечисления.X[Имя]` и обход метаданных. «Нет мест вызова» — повод проверить, а не приговор.',
    unusedH: '## Экспортные методы без внешних мест вызова', unusedNote: 'Нет вызова из другого модуля, нет подписки на событие / регламентного задания, нет ссылки строкой. «внутр.» — вызовы внутри своего модуля.',
    metaH: '## Экспортные методы, на которые ссылаются только метаданные или строки', enumH: '## Значения перечислений без единой ссылки (BSL и XML)', enumXmlH: '## Значения перечислений, на которые ссылается только XML (формы, макеты, СКД)',
    cwH: '## Константы, которые никто не пишет (нет Установить, менеджера значения, поля формы)', crH: '## Константы, которые никто не читает (нет Получить, прочих ссылок, поля формы)', cfH: '## Константы, которых нет ни на одной форме (задаются только кодом, если вообще задаются)',
    colMethod: 'Метод', colDef: 'Определение', colInt: 'внутр.', colMeta: 'метаданные', colStr: 'строки', none: '_(нет)_',
  },
};
function summary(lang, r) {
  const S = MD[lang]; const H = r.header;
  const L = [S.title, '', `- ${S.src}: \`${H.srcRoot}\``, `- ${S.gen}: ${H.generatedAt}`,
    `- ${S.counts}: BSL ${H.bslFiles} (${H.bslLines}), XML ${H.xmlFiles}, CommonModule ${H.commonModules}, export ${H.exports}, Enum ${H.enums}, Constant ${H.constants}`, '', S.limits, ''];
  L.push(S.unusedH, '', S.unusedNote, '', `| ${S.colMethod} | ${S.colDef} | ${S.colInt} |`, '|---|---|--:|');
  for (const u of r.unusedExports) L.push(`| \`${u.method}\` | \`${u.file}\` | ${u.internalCalls} |`);
  if (!r.unusedExports.length) L.push(`| ${S.none} | | |`);
  L.push('', S.metaH, '', `| ${S.colMethod} | ${S.colDef} | ${S.colMeta} | ${S.colStr} |`, '|---|---|--:|--:|');
  for (const u of r.metadataOnlyExports) L.push(`| \`${u.method}\` | \`${u.file}\` | ${u.metadata} | ${u.strings} |`);
  if (!r.metadataOnlyExports.length) L.push(`| ${S.none} | | | |`);
  const list = (h, arr) => { L.push('', h, ''); if (arr.length) for (const x of arr) L.push(`- \`${x}\``); else L.push(S.none); };
  list(S.enumH, r.unreferencedEnumValues);
  list(S.enumXmlH, r.enumValuesOnlyInXml);
  list(S.cwH, r.constantsNeverWritten);
  list(S.crH, r.constantsNeverRead);
  list(S.cfH, r.constantsNotOnForms);
  L.push('');
  return L.join('\n');
}

runMain('callgraph', main);
