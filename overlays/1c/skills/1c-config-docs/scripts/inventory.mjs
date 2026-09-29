#!/usr/bin/env node
// Inventory a 1C configuration dump (XML "designer files" format) into a
// machine-readable JSON plus a short markdown summary.
//
//   node inventory.mjs --config <docset.config.json> [--out <dir>] [--src-root <dir>] [--baseline <ref>]
//
// Config fields used: source.worktree|repo, source.srcRoot, source.ref, source.baseline,
// source.compareAlso, languages.*.code/synonymFallback, normalizeTranslations,
// outputRoot + factsDir, inventory.summaryLanguage.
// Outputs: <outputRoot>/<factsDir>/inventory.json, inventory-summary.md, inventory-report.json
// Exit codes: 0 ok · 1 findings (objects that failed to parse; still written) · 2 execution/config error.
//
// Zero npm dependencies. Node >= 18.

import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { loadConfig, parseArgs, runMain, ConfigError, UsageError, git as gitIn, writeJsonReport } from './lib/config.mjs';

// ---------------------------------------------------------------------------
// Runtime settings (filled in main from the config)
// ---------------------------------------------------------------------------

let SOURCE_ROOT = null;   // absolute path of the dump (worktree + srcRoot)
let SRC_REL = 'src/main'; // srcRoot relative to the worktree, forward slashes
let WORKTREE_ROOT = null;
let LANG_P = 'es';        // primary language code
let LANG_S = null;        // secondary language code or null
let FALLBACK_P = [];
let FALLBACK_S = [];
let NORM_LANGS = [];      // translation languages whose added variants are ignored by `changed`
let EXT = null;           // extension mode: { name, purpose, namePrefix } from Configuration.xml, else null

// Kind -> top-level folder name (mostly identical, a few plurals differ from
// the singular "kind" name used inside <MetaDataObject>/full names).
const KIND_FOLDERS = {
  Catalog: 'Catalogs',
  Document: 'Documents',
  InformationRegister: 'InformationRegisters',
  AccumulationRegister: 'AccumulationRegisters',
  AccountingRegister: 'AccountingRegisters',
  CalculationRegister: 'CalculationRegisters',
  ChartOfAccounts: 'ChartsOfAccounts',
  ChartOfCharacteristicTypes: 'ChartsOfCharacteristicTypes',
  ChartOfCalculationTypes: 'ChartsOfCalculationTypes',
  Enum: 'Enums',
  Report: 'Reports',
  DataProcessor: 'DataProcessors',
  CommonModule: 'CommonModules',
  CommonForm: 'CommonForms',
  CommonCommand: 'CommonCommands',
  CommonTemplate: 'CommonTemplates',
  CommonAttribute: 'CommonAttributes',
  Constant: 'Constants',
  Role: 'Roles',
  FunctionalOption: 'FunctionalOptions',
  EventSubscription: 'EventSubscriptions',
  ScheduledJob: 'ScheduledJobs',
  SessionParameter: 'SessionParameters',
  ExchangePlan: 'ExchangePlans',
  HTTPService: 'HTTPServices',
  WebService: 'WebServices',
  WSReference: 'WSReferences',
  XDTOPackage: 'XDTOPackages',
  DocumentJournal: 'DocumentJournals',
  BusinessProcess: 'BusinessProcesses',
  Task: 'Tasks',
  FilterCriterion: 'FilterCriteria',
  Sequence: 'Sequences',
  StyleItem: 'StyleItems',
  CommonPicture: 'CommonPictures',
  Language: 'Languages',
};
// Subsystems handled separately (nested tree).

// ---------------------------------------------------------------------------
// Tiny generic XML -> tree parser (handles the designer dump dialect: no CDATA,
// no processing instructions besides the XML decl, no entity refs beyond the
// standard 5, self-closing tags, xsi:nil attributes, tag names with colons
// treated as opaque strings).
// ---------------------------------------------------------------------------

function stripBom(s) {
  return s.charCodeAt(0) === 0xfeff ? s.slice(1) : s;
}

const ENTITY_MAP = { lt: '<', gt: '>', amp: '&', apos: "'", quot: '"' };
function decodeEntities(s) {
  if (s.indexOf('&') === -1) return s;
  return s.replace(/&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z]+);/g, (m, ent) => {
    if (ent[0] === '#') {
      const cp = ent[1] === 'x' || ent[1] === 'X' ? parseInt(ent.slice(2), 16) : parseInt(ent.slice(1), 10);
      return Number.isFinite(cp) ? String.fromCodePoint(cp) : m;
    }
    return ENTITY_MAP[ent] ?? m;
  });
}

// Node shape: { tag, attrs: {name:value}, children: [Node], text: string }
function parseXml(xmlText) {
  const s = stripBom(xmlText);
  let i = 0;
  if (s.startsWith('<?xml')) {
    const end = s.indexOf('?>', 5);
    i = end === -1 ? 0 : end + 2;
  }
  const root = { tag: '#root', attrs: {}, children: [], text: '' };
  const stack = [root];
  const top = () => stack[stack.length - 1];
  const TAG_RE = /<(\/?)([A-Za-z_][\w:.\-]*)((?:\s+[A-Za-z_][\w:.\-]*\s*=\s*"(?:[^"]*)")*)\s*(\/?)>/g;
  const ATTR_RE = /([A-Za-z_][\w:.\-]*)\s*=\s*"([^"]*)"/g;
  TAG_RE.lastIndex = i;
  let lastIndex = i;
  let m;
  while ((m = TAG_RE.exec(s)) !== null) {
    const textBetween = s.slice(lastIndex, m.index);
    if (textBetween.length) {
      const decoded = decodeEntities(textBetween);
      if (decoded.trim().length) top().text += decoded;
    }
    const [, closing, tagName, attrsRaw, selfClose] = m;
    if (closing) {
      for (let k = stack.length - 1; k > 0; k--) {
        if (stack[k].tag === tagName) { stack.length = k; break; }
      }
    } else {
      const attrs = {};
      if (attrsRaw) {
        ATTR_RE.lastIndex = 0;
        let am;
        while ((am = ATTR_RE.exec(attrsRaw)) !== null) attrs[am[1]] = decodeEntities(am[2]);
      }
      const node = { tag: tagName, attrs, children: [], text: '' };
      top().children.push(node);
      if (!selfClose) stack.push(node);
    }
    lastIndex = TAG_RE.lastIndex;
  }
  return root;
}

// ---------------------------------------------------------------------------
// Tree query helpers
// ---------------------------------------------------------------------------

function child(node, tag) {
  if (!node) return null;
  return node.children.find((c) => c.tag === tag) || null;
}
function children(node, tag) {
  if (!node) return [];
  return node.children.filter((c) => c.tag === tag);
}
function text(node) {
  if (!node) return '';
  return node.text.trim();
}
function textOf(node, tag) {
  return text(child(node, tag));
}
// Every object's XML wraps its real root in <MetaDataObject>; unwrap once
// (Predefined.xml is the exception: its root IS <PredefinedData>).
function mdRoot(tree) {
  return child(tree, 'MetaDataObject');
}

// <Synonym>/<ToolTip>/<Explanation> -> { <lang>: content } raw map.
function parseLangMap(node) {
  const out = {};
  if (!node) return out;
  for (const item of children(node, 'v8:item')) {
    const lang = textOf(item, 'v8:lang');
    const content = textOf(item, 'v8:content');
    if (lang) out[lang] = content;
  }
  return out;
}

// Primary name: primary synonym, then the fallback languages, then `fallback`.
function resolveP(syn, fallback) {
  if (syn[LANG_P]) return syn[LANG_P];
  for (const l of FALLBACK_P) if (syn[l]) return syn[l];
  return fallback;
}
// Secondary name: secondary synonym, then its fallbacks, else null (never invented).
function resolveS(syn) {
  if (syn[LANG_S]) return syn[LANG_S];
  for (const l of FALLBACK_S) if (syn[l]) return syn[l];
  return null;
}
// Adds name_<p> [, name_<s>] in this key order.
function names(rec, syn, fallback) {
  rec[`name_${LANG_P}`] = resolveP(syn, fallback);
  if (LANG_S) rec[`name_${LANG_S}`] = resolveS(syn);
  return rec;
}

// ---------------------------------------------------------------------------
// Type parsing
// ---------------------------------------------------------------------------

function parseTypeNode(typeNode) {
  if (!typeNode) return [];
  const types = children(typeNode, 'v8:Type').map((t) => text(t));
  const strQ = child(typeNode, 'v8:StringQualifiers');
  const numQ = child(typeNode, 'v8:NumberQualifiers');
  const dateQ = child(typeNode, 'v8:DateQualifiers');
  return types.map((t) => {
    if (t === 'xs:string' && strQ) return `xs:string(${textOf(strQ, 'v8:Length') || '0'})`;
    if (t === 'xs:decimal' && numQ) return `xs:decimal(${textOf(numQ, 'v8:Digits') || '0'},${textOf(numQ, 'v8:FractionDigits') || '0'})`;
    if (t === 'xs:dateTime' && dateQ) return `xs:dateTime(${textOf(dateQ, 'v8:DateFractions') || 'DateTime'})`;
    return t;
  });
}

// ---------------------------------------------------------------------------
// Attribute-like child parsing (Attribute / Dimension / Resource / EnumValue)
// ---------------------------------------------------------------------------

function parseAttributeLike(node) {
  const props = child(node, 'Properties');
  const name = textOf(props, 'Name');
  const syn = parseLangMap(child(props, 'Synonym'));
  const tooltip = parseLangMap(child(props, 'ToolTip'));
  const comment = textOf(props, 'Comment') || null;
  const rec = names({ name }, syn, name);
  rec.syn = syn;
  rec.type = parseTypeNode(child(props, 'Type'));
  if (comment) rec.comment = comment;
  if (Object.keys(tooltip).length) {
    rec[`tooltip_${LANG_P}`] = resolveP(tooltip, null);
    if (LANG_S) rec[`tooltip_${LANG_S}`] = resolveS(tooltip);
  }
  return markAdopted(rec, props);
}

// Extension mode only: a member (attribute, tabular section, dimension, enum value…) borrowed
// from the base configuration carries <ObjectBelonging>Adopted</ObjectBelonging>; own members
// of the extension carry nothing. Adopted members get `belonging: "adopted"`, own ones no field.
function isAdopted(props) {
  return textOf(props, 'ObjectBelonging') === 'Adopted';
}
function markAdopted(rec, props) {
  if (EXT && isAdopted(props)) rec.belonging = 'adopted';
  return rec;
}

function parseTabularSection(node) {
  const props = child(node, 'Properties');
  const name = textOf(props, 'Name');
  const syn = parseLangMap(child(props, 'Synonym'));
  const attrs = children(child(node, 'ChildObjects'), 'Attribute').map(parseAttributeLike);
  const rec = names({ name }, syn, name);
  rec.syn = syn;
  rec.attributes = sortByName(attrs);
  return markAdopted(rec, props);
}

function parseEnumValue(node) {
  const props = child(node, 'Properties');
  const name = textOf(props, 'Name');
  const syn = parseLangMap(child(props, 'Synonym'));
  const rec = names({ name }, syn, name);
  rec.syn = syn;
  return markAdopted(rec, props);
}

function sortByName(arr) {
  return arr.slice().sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

// ---------------------------------------------------------------------------
// Filesystem helpers
// ---------------------------------------------------------------------------

function listXmlFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).filter((d) => d.isFile() && d.name.endsWith('.xml')).map((d) => d.name).sort();
}

function listSubdirNames(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name).sort();
}

function readIfExists(p) {
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null;
}

function countLines(t) {
  if (t === null || t === undefined || t.length === 0) return 0;
  const normalized = t.replace(/\r\n/g, '\n');
  const trimmedTrailing = normalized.endsWith('\n') ? normalized.slice(0, -1) : normalized;
  if (trimmedTrailing.length === 0) return 0;
  return trimmedTrailing.split('\n').length;
}

function objFolder(kindFolder, name) {
  return path.join(SOURCE_ROOT, kindFolder, name);
}

function formsAndTemplates(objDir) {
  const subs = listSubdirNames(objDir);
  const forms = subs.includes('Forms') ? listXmlFiles(path.join(objDir, 'Forms')).map((f) => f.replace(/\.xml$/, '')) : [];
  const templates = subs.includes('Templates') ? listXmlFiles(path.join(objDir, 'Templates')).map((f) => f.replace(/\.xml$/, '')) : [];
  return { forms: forms.sort(), templates: templates.sort() };
}

function hasMainDcsSchema(objDir) {
  const templatesDir = path.join(objDir, 'Templates');
  if (!fs.existsSync(templatesDir)) return { has: false, name: null };
  for (const f of listXmlFiles(templatesDir)) {
    const xml = readIfExists(path.join(templatesDir, f));
    if (!xml) continue;
    const tree = mdRoot(parseXml(xml));
    const templateType = textOf(child(child(tree, 'Template'), 'Properties'), 'TemplateType');
    if (templateType === 'DataCompositionSchema') return { has: true, name: f.replace(/\.xml$/, '') };
  }
  return { has: false, name: null };
}

function predefinedCount(objDir) {
  const xml = readIfExists(path.join(objDir, 'Ext', 'Predefined.xml'));
  if (!xml) return 0;
  const root = parseXml(xml).children[0]; // <PredefinedData>
  return root ? children(root, 'Item').length : 0;
}

// ---------------------------------------------------------------------------
// Configuration extensions (.cfe dumps)
//
// Configuration.xml of an extension carries <ConfigurationExtensionPurpose> (AddOn /
// Customization / Patch) and <NamePrefix>. Every object the extension borrows from the base
// configuration has <ObjectBelonging>Adopted</ObjectBelonging> in its Properties; the
// extension's own objects have no such element.
// ---------------------------------------------------------------------------

function detectExtension(sourceRoot) {
  const xml = readIfExists(path.join(sourceRoot, 'Configuration.xml'));
  if (!xml) return null;
  const props = child(child(mdRoot(parseXml(xml)), 'Configuration'), 'Properties');
  const purpose = textOf(props, 'ConfigurationExtensionPurpose');
  if (!purpose) return null;
  return { name: textOf(props, 'Name'), purpose, namePrefix: textOf(props, 'NamePrefix') || null };
}

function listBslFiles(dir, rel = '') {
  if (!fs.existsSync(dir)) return [];
  const out = [];
  for (const d of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))) {
    const r = rel ? `${rel}/${d.name}` : d.name;
    if (d.isDirectory()) out.push(...listBslFiles(path.join(dir, d.name), r));
    else if (d.isFile() && d.name.endsWith('.bsl')) out.push(r);
  }
  return out;
}

// Adopted object: what the extension adds to it. Own members (no ObjectBelonging) of the
// record, own forms/templates/commands (their XML without ObjectBelonging) and every module
// file of the object in the extension dump (Ext/ObjectModule.bsl, Forms/<f>/Ext/Form/Module.bsl…:
// in an extension a module exists only when the extension adds or intercepts code).
function extensionAdds(rec, kindNode, objDir) {
  const own = (arr) => (arr || []).filter((x) => x.belonging !== 'adopted').map((x) => x.name);
  const adds = {};
  const put = (k, v) => { if (v.length) adds[k] = v; };
  const tsAttrs = [];
  for (const ts of rec.tabularSections || []) if (ts.belonging === 'adopted') for (const a of own(ts.attributes)) tsAttrs.push(`${ts.name}.${a}`);
  put('attributes', [...own(rec.attributes), ...tsAttrs]);
  put('tabularSections', own(rec.tabularSections));
  put('dimensions', own(rec.dimensions));
  put('resources', own(rec.resources));
  put('accountingFlags', own(rec.accountingFlags));
  put('values', own(rec.values));
  const childObjs = child(kindNode, 'ChildObjects');
  const ownFiles = (tag, folder) => children(childObjs, tag).map((n) => text(n)).filter(Boolean).filter((n) => {
    const x = readIfExists(path.join(objDir, folder, `${n}.xml`));
    if (!x) return true;
    const r = mdRoot(parseXml(x));
    const node = r && r.children.find((c) => child(c, 'Properties'));
    return !isAdopted(node ? child(node, 'Properties') : null);
  }).sort();
  put('forms', ownFiles('Form', 'Forms'));
  put('templates', ownFiles('Template', 'Templates'));
  put('commands', children(childObjs, 'Command').filter((n) => !isAdopted(child(n, 'Properties'))).map((n) => textOf(child(n, 'Properties'), 'Name')).sort());
  put('modules', listBslFiles(objDir));
  return adds;
}

// ---------------------------------------------------------------------------
// Git: baseline + changed flags
// ---------------------------------------------------------------------------

function git(args) {
  return gitIn(WORKTREE_ROOT, args);
}

// Read many blobs ("rev:path") through one `git cat-file --batch` per chunk.
function catBlobs(specs) {
  const res = new Map();
  const CHUNK = 400;
  for (let s = 0; s < specs.length; s += CHUNK) {
    const chunk = specs.slice(s, s + CHUNK);
    const out = execFileSync('git', ['cat-file', '--batch'], { cwd: WORKTREE_ROOT, input: chunk.join('\n') + '\n', maxBuffer: 1024 * 1024 * 1024 });
    let pos = 0;
    for (const spec of chunk) {
      const nl = out.indexOf(10, pos);
      const header = out.subarray(pos, nl).toString('utf8');
      pos = nl + 1;
      if (header.endsWith(' missing')) { res.set(spec, null); continue; }
      const size = Number(header.split(' ')[2]);
      res.set(spec, out.subarray(pos, pos + size));
      pos += size + 1;
    }
  }
  return res;
}

// ---------------------------------------------------------------------------
// Translation-noise normalization (for the `changed` flags)
//
// Bulk i18n commits add a translation to thousands of files without changing
// behaviour. With `normalizeTranslations: ["ru"]` the comparison ignores:
//   * XML: <v8:item><v8:lang>ru</v8:lang><v8:content>…</v8:content></v8:item> in
//     any multilingual block (Synonym, Title, ToolTip, formats, DCS titles…); a
//     block left empty is collapsed to <Tag/>;
//   * BSL: the `ru='…'` segment of string literals that are entirely an NStr
//     language map ("es='…'; en='…'; ru='…'", multi-line `|` literals too).
// Everywhere: CRLF/LF, BOM, trailing whitespace and blank lines.
// ---------------------------------------------------------------------------

function textOfBuf(buf) {
  let s = buf.toString('utf8');
  if (s.charCodeAt(0) === 0xfeff) s = s.slice(1);
  return s.replace(/\r\n?/g, '\n');
}

function tidyLines(s) {
  return s.split('\n').map((l) => l.replace(/[ \t]+$/, '')).filter((l) => l.length).join('\n');
}

let LANG_ITEM_RE = null;
const EMPTY_EL_RE = /<([A-Za-z_][\w:.\-]*)((?:\s+[A-Za-z_][\w:.\-]*\s*=\s*"[^"]*")*)\s*>\s*<\/\1>/g;

function normalizeXml(buf) {
  let s = textOfBuf(buf);
  if (LANG_ITEM_RE) s = s.replace(LANG_ITEM_RE, '');
  return tidyLines(s.replace(EMPTY_EL_RE, '<$1$2/>'));
}

const BSL_CONT_RE = /\n[\t ]*\|/g;
const NSTR_LANGMAP_RE = /^\s*(?:[A-Za-z]{2}\s*=\s*'(?:[^']|'')*'\s*;?\s*)+$/;
const NSTR_SEG_RE = /([A-Za-z]{2})\s*=\s*'((?:[^']|'')*)'/g;

function canonBslLiteral(lit) {
  const logical = lit.replace(BSL_CONT_RE, '\n');
  if (!NSTR_LANGMAP_RE.test(logical)) return lit;
  const segs = [];
  NSTR_SEG_RE.lastIndex = 0;
  let m;
  while ((m = NSTR_SEG_RE.exec(logical)) !== null) {
    const lang = m[1].toLowerCase();
    if (NORM_LANGS.includes(lang)) continue;
    segs.push(`${lang}='${m[2].split('\n').map((l) => l.trim()).join('\n')}'`);
  }
  return `\u0001NSTR[${segs.join(';')}]`;
}

function normalizeBsl(buf) {
  const s = textOfBuf(buf);
  const n = s.length;
  let out = '';
  let i = 0;
  while (i < n) {
    const ch = s[i];
    if (ch === '/' && s[i + 1] === '/') {
      const e = s.indexOf('\n', i);
      const end = e === -1 ? n : e;
      out += s.slice(i, end);
      i = end;
      continue;
    }
    if (ch === '"') {
      let j = i + 1;
      let lit = '';
      while (j < n) {
        if (s[j] === '"') {
          if (s[j + 1] === '"') { lit += '"'; j += 2; continue; }
          break;
        }
        lit += s[j];
        j++;
      }
      out += '"' + canonBslLiteral(lit) + '"';
      i = j + 1;
      continue;
    }
    out += ch;
    i++;
  }
  return tidyLines(out);
}

const PLAIN_TEXT_EXT_RE = /\.(txt|html?|css|js|json|xsd|wsdl|md)$/i;

function normalizeFile(p, buf) {
  if (buf === null || buf === undefined) return null;
  if (/\.xml$/i.test(p)) return normalizeXml(buf);
  if (/\.bsl$/i.test(p)) return normalizeBsl(buf);
  if (PLAIN_TEXT_EXT_RE.test(p)) return tidyLines(textOfBuf(buf));
  return buf;
}

function sameNormalized(a, b) {
  if (a === null || b === null) return a === b;
  if (Buffer.isBuffer(a) || Buffer.isBuffer(b)) return Buffer.isBuffer(a) && Buffer.isBuffer(b) && a.equals(b);
  return a === b;
}

function markRealChanges(fromRef, toRef, changedFiles) {
  const mods = changedFiles.filter((f) => f.status === 'M');
  const blobs = catBlobs(mods.flatMap((f) => [`${fromRef}:${f.path}`, `${toRef}:${f.path}`]));
  for (const f of changedFiles) {
    if (f.status !== 'M') { f.real = true; continue; }
    const a = normalizeFile(f.path, blobs.get(`${fromRef}:${f.path}`));
    const b = normalizeFile(f.path, blobs.get(`${toRef}:${f.path}`));
    f.real = !sameNormalized(a, b);
  }
  return changedFiles;
}

function commitInfo(hash) {
  const subject = git(['log', '-1', '--format=%s', hash]).trim();
  const date = git(['log', '-1', '--format=%ad', '--date=short', hash]).trim();
  return { hash, subject, date };
}

// Baseline (comparison base): configured ref, else the first commit that touched srcRoot
// (for a vendor configuration usually the vendor import; for an extension, its first commit).
function resolveBaseline(ref) {
  if (ref) return commitInfo(git(['rev-parse', '--verify', `${ref}^{commit}`]).trim());
  const firstHash = git(['log', '--reverse', '--format=%H', '--', SRC_REL]).trim().split('\n')[0];
  if (!firstHash) throw new ConfigError(`no commit touches ${SRC_REL}; set source.baseline`);
  return commitInfo(firstHash);
}

function diffAddedModified(fromRef, toRef) {
  const out = git(['-c', 'core.quotePath=false', 'diff', '--name-status', '--no-renames', '-z', fromRef, toRef, '--', SRC_REL]);
  const parts = out.split('\0');
  const changedFiles = [];
  for (let k = 0; k + 1 < parts.length; k += 2) {
    if (!parts[k]) continue;
    changedFiles.push({ status: parts[k][0], path: parts[k + 1] });
  }
  return changedFiles;
}

function newEntry() {
  return { mainAdded: false, mainDeleted: false, rawFiles: 0, realFiles: 0 };
}

function touchEntry(index, key, f, isMainFile) {
  let entry = index.get(key);
  if (!entry) { entry = newEntry(); index.set(key, entry); }
  entry.rawFiles++;
  if (f.real) entry.realFiles++;
  if (isMainFile && f.status === 'A') entry.mainAdded = true;
  if (isMainFile && f.status === 'D') entry.mainDeleted = true;
}

function buildChangedIndex(changedFiles) {
  const index = new Map();
  const prefix = `${SRC_REL}/`;
  for (const f of changedFiles) {
    if (!f.path.startsWith(prefix)) continue;
    const segs = f.path.slice(prefix.length).split('/');
    if (segs.length < 2) continue;
    const folder = segs[0];
    const objSeg = segs[1];
    const objName = objSeg.endsWith('.xml') ? objSeg.slice(0, -4) : objSeg;
    const isMainFile = segs.length === 2 && segs[1] === `${objName}.xml`;
    touchEntry(index, `${folder}/${objName}`, f, isMainFile);
  }
  return index;
}

// -> { changed: 'new'|'modified'|null, changed_raw, changed_files }
function statusFromEntry(entry) {
  if (!entry) return { changed: null, changed_raw: null, changed_files: 0 };
  if (entry.mainAdded) return { changed: 'new', changed_raw: 'new', changed_files: entry.realFiles };
  return {
    changed: entry.realFiles > 0 ? 'modified' : null,
    changed_raw: entry.rawFiles > 0 ? 'modified' : null,
    changed_files: entry.realFiles,
  };
}

function changedStatusFor(index, kindFolder, name) {
  return statusFromEntry(index.get(`${kindFolder}/${name}`));
}

// Subsystems nest (Subsystems/A/Subsystems/B...): each file belongs to the deepest
// subsystem folder that contains it.
function buildSubsystemChangedIndex(changedFiles) {
  const index = new Map();
  const prefix = `${SRC_REL}/`;
  for (const f of changedFiles) {
    if (!f.path.startsWith(`${prefix}Subsystems/`)) continue;
    const segs = f.path.slice(prefix.length).split('/');
    let k = 1;
    while (k + 2 < segs.length && segs[k + 1] === 'Subsystems') k += 2;
    const nameSeg = segs[k];
    const isMainFile = k === segs.length - 1 && nameSeg.endsWith('.xml');
    const name = isMainFile ? nameSeg.slice(0, -4) : nameSeg;
    touchEntry(index, [...segs.slice(0, k), name].join('/'), f, isMainFile);
  }
  return index;
}

const compareKey = (ref) => `changed_vs_${ref.replace(/[^A-Za-z0-9_]/g, '_')}`;

// ---------------------------------------------------------------------------
// Per-kind extraction
// ---------------------------------------------------------------------------

function baseRecord(kind, name, propsNode) {
  const syn = parseLangMap(child(propsNode, 'Synonym'));
  const comment = textOf(propsNode, 'Comment') || null;
  const rec = names({ kind, name }, syn, name);
  rec.syn = syn;
  rec.comment = comment;
  return rec;
}

function extractCatalog(root, objDir) {
  const props = child(child(root, 'Catalog'), 'Properties');
  const rec = baseRecord('Catalog', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'Catalog'), 'ChildObjects');
  rec.hierarchical = textOf(props, 'Hierarchical') === 'true';
  rec.owners = children(child(props, 'Owners'), 'xr:Item').map((n) => text(n));
  const codeLength = textOf(props, 'CodeLength');
  const descLength = textOf(props, 'DescriptionLength');
  rec.codeLength = codeLength ? Number(codeLength) : 0;
  rec.descriptionLength = descLength ? Number(descLength) : 0;
  rec.attributes = sortByName(children(childObjs, 'Attribute').map(parseAttributeLike));
  rec.tabularSections = sortByName(children(childObjs, 'TabularSection').map(parseTabularSection));
  rec.predefinedCount = predefinedCount(objDir);
  return rec;
}

function extractDocument(root, objDir) {
  const props = child(child(root, 'Document'), 'Properties');
  const rec = baseRecord('Document', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'Document'), 'ChildObjects');
  rec.posting = textOf(props, 'Posting') || null;
  rec.realTimePosting = textOf(props, 'RealTimePosting') || null;
  rec.registerRecords = children(child(props, 'RegisterRecords'), 'xr:Item').map((n) => text(n)).sort();
  rec.numerator = text(child(props, 'Numerator')) || null;
  rec.attributes = sortByName(children(childObjs, 'Attribute').map(parseAttributeLike));
  rec.tabularSections = sortByName(children(childObjs, 'TabularSection').map(parseTabularSection));
  const basedOn = children(child(props, 'BasedOn'), 'xr:Item').map((n) => text(n));
  if (basedOn.length) rec.basedOn = basedOn.sort();
  rec.hasObjectModule = fs.existsSync(path.join(objDir, 'Ext', 'ObjectModule.bsl'));
  rec.hasManagerModule = fs.existsSync(path.join(objDir, 'Ext', 'ManagerModule.bsl'));
  const { forms, templates } = formsAndTemplates(objDir);
  rec.forms = forms;
  rec.templates = templates;
  return rec;
}

function extractInformationRegister(root) {
  const props = child(child(root, 'InformationRegister'), 'Properties');
  const rec = baseRecord('InformationRegister', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'InformationRegister'), 'ChildObjects');
  rec.periodicity = textOf(props, 'InformationRegisterPeriodicity') || null;
  rec.writeMode = textOf(props, 'WriteMode') || null;
  rec.dimensions = sortByName(children(childObjs, 'Dimension').map(parseAttributeLike));
  rec.resources = sortByName(children(childObjs, 'Resource').map(parseAttributeLike));
  rec.attributes = sortByName(children(childObjs, 'Attribute').map(parseAttributeLike));
  return rec;
}

function extractAccumulationRegister(root) {
  const props = child(child(root, 'AccumulationRegister'), 'Properties');
  const rec = baseRecord('AccumulationRegister', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'AccumulationRegister'), 'ChildObjects');
  rec.registerType = textOf(props, 'RegisterType') || null;
  rec.dimensions = sortByName(children(childObjs, 'Dimension').map(parseAttributeLike));
  rec.resources = sortByName(children(childObjs, 'Resource').map(parseAttributeLike));
  rec.attributes = sortByName(children(childObjs, 'Attribute').map(parseAttributeLike));
  return rec;
}

function extractAccountingRegister(root) {
  const props = child(child(root, 'AccountingRegister'), 'Properties');
  const rec = baseRecord('AccountingRegister', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'AccountingRegister'), 'ChildObjects');
  rec.chartOfAccounts = textOf(props, 'ChartOfAccounts') || null;
  rec.correspondence = textOf(props, 'Correspondence') === 'true';
  rec.dimensions = sortByName(children(childObjs, 'Dimension').map(parseAttributeLike));
  rec.resources = sortByName(children(childObjs, 'Resource').map(parseAttributeLike));
  return rec;
}

function extractCalculationRegister(root) {
  const props = child(child(root, 'CalculationRegister'), 'Properties');
  const rec = baseRecord('CalculationRegister', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'CalculationRegister'), 'ChildObjects');
  rec.actionPeriod = textOf(props, 'ActionPeriod') === 'true';
  rec.schedule = textOf(props, 'Schedule') || null;
  rec.dimensions = sortByName(children(childObjs, 'Dimension').map(parseAttributeLike));
  rec.resources = sortByName(children(childObjs, 'Resource').map(parseAttributeLike));
  return rec;
}

function extractChartOfAccounts(root, objDir) {
  const props = child(child(root, 'ChartOfAccounts'), 'Properties');
  const rec = baseRecord('ChartOfAccounts', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'ChartOfAccounts'), 'ChildObjects');
  rec.extDimensionTypes = textOf(props, 'ExtDimensionTypes') || null;
  const maxExt = textOf(props, 'MaxExtDimensionCount');
  rec.maxExtDimensionCount = maxExt ? Number(maxExt) : 0;
  rec.codeLength = Number(textOf(props, 'CodeLength') || '0');
  rec.accountingFlags = sortByName(children(childObjs, 'AccountingFlag').map(parseAttributeLike));
  rec.attributes = sortByName(children(childObjs, 'Attribute').map(parseAttributeLike));
  rec.predefinedCount = predefinedCount(objDir);
  return rec;
}

function extractChartOfCharacteristicTypes(root, objDir) {
  const props = child(child(root, 'ChartOfCharacteristicTypes'), 'Properties');
  const rec = baseRecord('ChartOfCharacteristicTypes', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'ChartOfCharacteristicTypes'), 'ChildObjects');
  rec.valueType = parseTypeNode(child(props, 'Type'));
  rec.attributes = sortByName(children(childObjs, 'Attribute').map(parseAttributeLike));
  rec.predefinedCount = predefinedCount(objDir);
  return rec;
}

function extractChartOfCalculationTypes(root, objDir) {
  const props = child(child(root, 'ChartOfCalculationTypes'), 'Properties');
  const rec = baseRecord('ChartOfCalculationTypes', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'ChartOfCalculationTypes'), 'ChildObjects');
  rec.attributes = sortByName(children(childObjs, 'Attribute').map(parseAttributeLike));
  rec.predefinedCount = predefinedCount(objDir);
  return rec;
}

function extractEnum(root) {
  const props = child(child(root, 'Enum'), 'Properties');
  const rec = baseRecord('Enum', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'Enum'), 'ChildObjects');
  rec.values = children(childObjs, 'EnumValue').map(parseEnumValue); // declaration order is meaningful
  return rec;
}

function extractConstant(root) {
  const props = child(child(root, 'Constant'), 'Properties');
  const rec = baseRecord('Constant', textOf(props, 'Name'), props);
  rec.type = parseTypeNode(child(props, 'Type'));
  return rec;
}

function extractCommonModule(root, objDir) {
  const props = child(child(root, 'CommonModule'), 'Properties');
  const rec = baseRecord('CommonModule', textOf(props, 'Name'), props);
  rec.global = textOf(props, 'Global') === 'true';
  rec.clientManagedApplication = textOf(props, 'ClientManagedApplication') === 'true';
  rec.server = textOf(props, 'Server') === 'true';
  rec.externalConnection = textOf(props, 'ExternalConnection') === 'true';
  rec.clientOrdinaryApplication = textOf(props, 'ClientOrdinaryApplication') === 'true';
  rec.serverCall = textOf(props, 'ServerCall') === 'true';
  rec.privileged = textOf(props, 'Privileged') === 'true';
  rec.returnValuesReuse = textOf(props, 'ReturnValuesReuse') || null;
  rec.moduleLineCount = countLines(readIfExists(path.join(objDir, 'Ext', 'Module.bsl')));
  return rec;
}

function extractEventSubscription(root) {
  const props = child(child(root, 'EventSubscription'), 'Properties');
  const rec = baseRecord('EventSubscription', textOf(props, 'Name'), props);
  rec.sourceTypes = children(child(props, 'Source'), 'v8:Type').map((n) => text(n)).sort();
  rec.event = textOf(props, 'Event') || null;
  rec.handler = textOf(props, 'Handler') || null;
  return rec;
}

function extractScheduledJob(root) {
  const props = child(child(root, 'ScheduledJob'), 'Properties');
  const rec = baseRecord('ScheduledJob', textOf(props, 'Name'), props);
  rec.methodName = textOf(props, 'MethodName') || null;
  rec.use = textOf(props, 'Use') === 'true';
  rec.predefined = textOf(props, 'Predefined') === 'true';
  return rec;
}

function extractFunctionalOption(root) {
  const props = child(child(root, 'FunctionalOption'), 'Properties');
  const rec = baseRecord('FunctionalOption', textOf(props, 'Name'), props);
  rec.location = textOf(props, 'Location') || null;
  rec.contentCount = children(child(props, 'Content'), 'xr:Item').length;
  return rec;
}

function extractReportOrDataProcessor(kind, root, objDir) {
  const props = child(child(root, kind), 'Properties');
  const rec = baseRecord(kind, textOf(props, 'Name'), props);
  const { forms, templates } = formsAndTemplates(objDir);
  rec.forms = forms;
  rec.templates = templates;
  const dcs = hasMainDcsSchema(objDir);
  rec.hasMainDcsSchema = dcs.has;
  rec.dcsTemplateName = dcs.name;
  return rec;
}

function extractDocumentJournal(root) {
  const props = child(child(root, 'DocumentJournal'), 'Properties');
  const rec = baseRecord('DocumentJournal', textOf(props, 'Name'), props);
  rec.registeredDocuments = children(child(props, 'RegisteredDocuments'), 'xr:Item').map((n) => text(n)).sort();
  return rec;
}

function extractCommonAttribute(root) {
  const props = child(child(root, 'CommonAttribute'), 'Properties');
  const rec = baseRecord('CommonAttribute', textOf(props, 'Name'), props);
  rec.type = parseTypeNode(child(props, 'Type'));
  rec.autoUse = textOf(props, 'AutoUse') || null;
  rec.dataSeparation = textOf(props, 'DataSeparation') || null;
  rec.contentCount = children(child(props, 'Content'), 'xr:Item').length;
  return rec;
}

function extractSessionParameter(root) {
  const props = child(child(root, 'SessionParameter'), 'Properties');
  const rec = baseRecord('SessionParameter', textOf(props, 'Name'), props);
  rec.type = parseTypeNode(child(props, 'Type'));
  return rec;
}

function extractExchangePlan(root) {
  const props = child(child(root, 'ExchangePlan'), 'Properties');
  const rec = baseRecord('ExchangePlan', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'ExchangePlan'), 'ChildObjects');
  rec.attributes = sortByName(children(childObjs, 'Attribute').map(parseAttributeLike));
  rec.contentCount = children(child(props, 'Content'), 'xr:Item').length;
  return rec;
}

function extractHttpOrWebService(kind, root) {
  const props = child(child(root, kind), 'Properties');
  const rec = baseRecord(kind, textOf(props, 'Name'), props);
  rec.rootUrl = textOf(props, 'RootURL') || textOf(props, 'Descriptor') || null;
  return rec;
}

function extractXdtoPackage(root) {
  const props = child(child(root, 'XDTOPackage'), 'Properties');
  const rec = baseRecord('XDTOPackage', textOf(props, 'Name'), props);
  rec.namespaceUri = textOf(props, 'NamespaceURI') || textOf(props, 'Namespace') || null;
  return rec;
}

function extractBusinessProcess(root, objDir) {
  const props = child(child(root, 'BusinessProcess'), 'Properties');
  const rec = baseRecord('BusinessProcess', textOf(props, 'Name'), props);
  const childObjs = child(child(root, 'BusinessProcess'), 'ChildObjects');
  rec.attributes = sortByName(children(childObjs, 'Attribute').map(parseAttributeLike));
  rec.tabularSections = sortByName(children(childObjs, 'TabularSection').map(parseTabularSection));
  const { forms, templates } = formsAndTemplates(objDir);
  rec.forms = forms;
  rec.templates = templates;
  return rec;
}

const simple = (kind) => (root) => baseRecord(kind, textOf(child(child(root, kind), 'Properties'), 'Name'), child(child(root, kind), 'Properties'));

const EXTRACTORS = {
  Catalog: extractCatalog,
  Document: extractDocument,
  InformationRegister: extractInformationRegister,
  AccumulationRegister: extractAccumulationRegister,
  AccountingRegister: extractAccountingRegister,
  CalculationRegister: extractCalculationRegister,
  ChartOfAccounts: extractChartOfAccounts,
  ChartOfCharacteristicTypes: extractChartOfCharacteristicTypes,
  ChartOfCalculationTypes: extractChartOfCalculationTypes,
  Enum: extractEnum,
  Constant: extractConstant,
  CommonModule: extractCommonModule,
  CommonForm: simple('CommonForm'),
  CommonCommand: simple('CommonCommand'),
  CommonTemplate: simple('CommonTemplate'),
  CommonAttribute: extractCommonAttribute,
  Role: simple('Role'),
  FunctionalOption: extractFunctionalOption,
  EventSubscription: extractEventSubscription,
  ScheduledJob: extractScheduledJob,
  SessionParameter: extractSessionParameter,
  ExchangePlan: extractExchangePlan,
  HTTPService: (root) => extractHttpOrWebService('HTTPService', root),
  WebService: (root) => extractHttpOrWebService('WebService', root),
  WSReference: simple('WSReference'),
  XDTOPackage: extractXdtoPackage,
  DocumentJournal: extractDocumentJournal,
  BusinessProcess: extractBusinessProcess,
  Task: simple('Task'),
  FilterCriterion: simple('FilterCriterion'),
  Sequence: simple('Sequence'),
  StyleItem: simple('StyleItem'),
  CommonPicture: simple('CommonPicture'),
  Language: simple('Language'),
  Report: (root, objDir) => extractReportOrDataProcessor('Report', root, objDir),
  DataProcessor: (root, objDir) => extractReportOrDataProcessor('DataProcessor', root, objDir),
};

// ---------------------------------------------------------------------------
// Subsystems (recursive tree walk)
// ---------------------------------------------------------------------------

function parseSubsystemFile(xmlPath, fullPath) {
  const xml = readIfExists(xmlPath);
  if (!xml) return null;
  const subsystemNode = child(mdRoot(parseXml(xml)), 'Subsystem');
  const props = child(subsystemNode, 'Properties');
  const name = textOf(props, 'Name');
  const syn = parseLangMap(child(props, 'Synonym'));
  const rec = { kind: 'Subsystem', name, fullPath };
  names(rec, syn, name);
  rec.syn = syn;
  rec.comment = textOf(props, 'Comment') || null;
  rec.includeInCommandInterface = textOf(props, 'IncludeInCommandInterface') === 'true';
  rec.content = children(child(props, 'Content'), 'xr:Item').map((n) => text(n)).sort();
  rec.children = children(child(subsystemNode, 'ChildObjects'), 'Subsystem').map((n) => text(n)).sort();
  if (EXT) rec.belonging = isAdopted(props) ? 'adopted' : 'own';
  return rec;
}

function walkSubsystems() {
  const result = [];
  function recurse(dirPrefix, fullPathPrefix) {
    for (const f of listXmlFiles(dirPrefix)) {
      const name = f.replace(/\.xml$/, '');
      const fullPath = fullPathPrefix ? `${fullPathPrefix}.${name}` : name;
      const rec = parseSubsystemFile(path.join(dirPrefix, f), fullPath);
      if (!rec) continue;
      rec._xmlRelNoExt = path.relative(SOURCE_ROOT, path.join(dirPrefix, f)).replace(/\\/g, '/').replace(/\.xml$/, '');
      result.push(rec);
      const nestedDir = path.join(dirPrefix, name, 'Subsystems');
      if (fs.existsSync(nestedDir)) recurse(nestedDir, fullPath);
    }
  }
  recurse(path.join(SOURCE_ROOT, 'Subsystems'), '');
  return result;
}

// ---------------------------------------------------------------------------
// Markdown summary (en / ru)
// ---------------------------------------------------------------------------

const SUMMARY = {
  en: {
    title: '# 1C configuration inventory — summary', source: 'Source', head: 'Commit (worktree HEAD)', baseline: 'Baseline (comparison base)',
    generated: 'Generated', byKind: '## Objects by kind', kind: 'Kind', count: 'Count', total: 'Total',
    subsH: '## Subsystems: objects by kind (via Content)', sub: 'Subsystem', subCount: 'Objects in Content', subKinds: 'Object kinds',
    outsideH: '## Objects outside subsystems', all: 'Total', objects: 'Objects',
    changedH: '## New and modified objects against the baseline (by kind)',
    rule: (langs) => 'Normalization rule. An object is modified (`changed = "modified"`) when at least one of its files differs from the baseline ' +
      (langs.length
        ? `**after removing translation noise**: in XML every \`<v8:item><v8:lang>${langs.join('|')}</v8:lang>…</v8:item>\` is cut out of all multilingual properties and an emptied element becomes \`<Tag/>\`; in BSL string literals that consist entirely of NStr language segments lose the \`${langs.join('/')}\` segment(s)`
        : '(no translation normalization configured)') +
      '; line endings, BOM, trailing whitespace and blank lines are normalized everywhere. Other text files are compared after line-ending normalization, binaries byte by byte. ' +
      'An added or deleted file of the object always makes it modified; an added main XML means `new`. `changed_raw` is the flag on the raw git diff; `changed_files` is the number of really changed files; `changed_vs_<ref>` uses the same normalization.',
    newCol: 'New', modCol: 'Modified', rawCol: 'Modified (raw diff)',
    newListH: '## All new objects (against the baseline)', none: '_(none)_',
    noSecH: (l) => `## Objects without a "${l}" synonym`,
    noPrimH: (l, fb) => `## Objects without a "${l}" synonym${fb.length ? ` (fallbacks ${fb.join(', ')} empty too)` : ''}`,
    extH: '## Configuration extension', extName: 'Extension', extPurpose: 'Purpose', extPrefix: 'Name prefix',
    extRule: 'Belonging (`belonging`) comes from `ObjectBelonging` in the dump, not from git: `own` = object of the extension itself, `adopted` = object borrowed from the base configuration. The `changed` flags below only say what changed since the baseline.',
    ownCol: 'Own', adoptedCol: 'Adopted',
    adoptedListH: '## Adopted objects and what the extension adds to them', addsNone: 'nothing (reference to the base object only)',
  },
  ru: {
    title: '# Инвентаризация конфигурации 1С — сводка', source: 'Источник', head: 'Commit (HEAD ворктри)', baseline: 'База сравнения (baseline)',
    generated: 'Сгенерировано', byKind: '## Количество объектов по видам', kind: 'Вид', count: 'Количество', total: 'Итого',
    subsH: '## Подсистемы: количество объектов по видам (через Content)', sub: 'Подсистема', subCount: 'Кол-во объектов в Content', subKinds: 'Виды объектов',
    outsideH: '## Объекты вне подсистем', all: 'Всего', objects: 'Объекты',
    changedH: '## Новые и изменённые объекты относительно базы сравнения (по видам)',
    rule: (langs) => 'Правило нормализации. Объект считается изменённым (`changed = "modified"`), если хотя бы один его файл отличается от базы сравнения ' +
      (langs.length
        ? `**после удаления переводного шума**: в XML вырезаются все элементы \`<v8:item><v8:lang>${langs.join('|')}</v8:lang>…</v8:item>\` в любых многоязычных свойствах, опустевший элемент приводится к \`<Tag/>\`; в BSL у строковых литералов, целиком состоящих из языковых сегментов NStr, выбрасываются сегменты \`${langs.join('/')}\``
        : '(нормализация переводов не настроена)') +
      '; везде нормализуются переводы строк, BOM, хвостовые пробелы и пустые строки. Прочие текстовые файлы сравниваются после нормализации переводов строк, бинарные — побайтно. ' +
      'Добавленный или удалённый файл объекта всегда делает объект изменённым; добавленный главный XML — `new`. `changed_raw` — флаг по сырому git diff; `changed_files` — число реально изменённых файлов; `changed_vs_<ref>` считается по той же нормализации.',
    newCol: 'Новые', modCol: 'Изменённые', rawCol: 'Изменённые (сырой diff)',
    newListH: '## Список всех новых объектов (относительно базы сравнения)', none: '_(нет)_',
    noSecH: (l) => `## Объекты без синонима «${l}»`,
    noPrimH: (l, fb) => `## Объекты без синонима «${l}»${fb.length ? ` (запасные ${fb.join(', ')} тоже пусты)` : ''}`,
    extH: '## Расширение конфигурации', extName: 'Расширение', extPurpose: 'Назначение', extPrefix: 'Префикс имён',
    extRule: 'Принадлежность (`belonging`) берётся из `ObjectBelonging` выгрузки, а не из git: `own` — собственный объект расширения, `adopted` — заимствованный из основной конфигурации. Флаги `changed` ниже говорят только о том, что изменилось с базы сравнения.',
    ownCol: 'Собственные', adoptedCol: 'Заимствованные',
    adoptedListH: '## Заимствованные объекты и что к ним добавляет расширение', addsNone: 'ничего (только ссылка на объект основной конфигурации)',
  },
};

function buildMarkdownSummary(S, header, countsByKind, objects, subsystems) {
  const lines = [];
  lines.push(S.title, '');
  lines.push(`- ${S.source}: \`${header.sourceRoot}\``);
  lines.push(`- ${S.head}: \`${header.headCommit}\``);
  lines.push(`- ${S.baseline}: \`${header.baselineCommit}\` — ${header.baselineDate} — ${header.baselineSubject}`);
  lines.push(`- ${S.generated}: ${header.generatedAt}`, '');

  if (header.extension) {
    const X = header.extension;
    lines.push(S.extH, '', `- ${S.extName}: \`${X.name}\``, `- ${S.extPurpose}: \`${X.purpose}\``, `- ${S.extPrefix}: ${X.namePrefix ? `\`${X.namePrefix}\`` : '—'}`, '', S.extRule, '');
    lines.push(`| ${S.kind} | ${S.ownCol} | ${S.adoptedCol} |`, '|---|---:|---:|');
    const kinds = [...new Set(objects.map((o) => o.kind))].sort();
    let to = 0; let ta = 0;
    for (const k of kinds) {
      const a = objects.filter((o) => o.kind === k && o.belonging === 'own').length;
      const b = objects.filter((o) => o.kind === k && o.belonging === 'adopted').length;
      to += a; ta += b;
      lines.push(`| ${k} | ${a} | ${b} |`);
    }
    lines.push(`| **${S.total}** | **${to}** | **${ta}** |`, '');
    lines.push(S.adoptedListH, '');
    const adopted = objects.filter((o) => o.belonging === 'adopted');
    for (const o of adopted) {
      const adds = Object.entries(o.extensionAdds || {}).map(([k, v]) => `${k}: ${v.map((x) => `\`${x}\``).join(', ')}`).join('; ');
      lines.push(`- ${o.kind}.${o.kind === 'Subsystem' ? o.fullPath : o.name} — ${adds || S.addsNone}`);
    }
    if (!adopted.length) lines.push(S.none);
    lines.push('');
  }

  lines.push(S.byKind, '', `| ${S.kind} | ${S.count} |`, '|---|---:|');
  for (const [k, v] of Object.entries(countsByKind).sort()) lines.push(`| ${k} | ${v} |`);
  lines.push(`| **${S.total}** | **${objects.length}** |`, '');

  lines.push(S.subsH, '', `| ${S.sub} | ${S.subCount} | ${S.subKinds} |`, '|---|---:|---|');
  for (const s of subsystems.slice().sort((a, b) => (a.fullPath < b.fullPath ? -1 : 1))) {
    const kindsCount = new Map();
    for (const fullName of s.content) { const kind = fullName.split('.')[0]; kindsCount.set(kind, (kindsCount.get(kind) || 0) + 1); }
    const kindsStr = Array.from(kindsCount.entries()).sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([k, v]) => `${k}:${v}`).join(', ');
    lines.push(`| ${s.fullPath} | ${s.content.length} | ${kindsStr || '—'} |`);
  }
  lines.push('');

  const noSubsystem = objects.filter((o) => o.kind !== 'Subsystem' && (!o.subsystems || o.subsystems.length === 0));
  lines.push(S.outsideH, '', `${S.all}: ${noSubsystem.length}`, '', `| ${S.kind} | ${S.count} | ${S.objects} |`, '|---|---:|---|');
  const noSubByKind = new Map();
  for (const o of noSubsystem) { if (!noSubByKind.has(o.kind)) noSubByKind.set(o.kind, []); noSubByKind.get(o.kind).push(o.name); }
  for (const [k, n] of Array.from(noSubByKind.entries()).sort()) lines.push(`| ${k} | ${n.length} | ${n.sort().join(', ')} |`);
  lines.push('');

  lines.push(S.changedH, '', S.rule(NORM_LANGS), '');
  const newByKind = new Map(); const modByKind = new Map(); const modRawByKind = new Map();
  for (const o of objects) {
    if (o.changed === 'new') newByKind.set(o.kind, (newByKind.get(o.kind) || 0) + 1);
    if (o.changed === 'modified') modByKind.set(o.kind, (modByKind.get(o.kind) || 0) + 1);
    if (o.changed_raw === 'modified') modRawByKind.set(o.kind, (modRawByKind.get(o.kind) || 0) + 1);
  }
  lines.push(`| ${S.kind} | ${S.newCol} | ${S.modCol} | ${S.rawCol} |`, '|---|---:|---:|---:|');
  let totNew = 0; let totMod = 0; let totRaw = 0;
  for (const k of Array.from(new Set([...newByKind.keys(), ...modByKind.keys(), ...modRawByKind.keys()])).sort()) {
    const a = newByKind.get(k) || 0; const b = modByKind.get(k) || 0; const c = modRawByKind.get(k) || 0;
    totNew += a; totMod += b; totRaw += c;
    lines.push(`| ${k} | ${a} | ${b} | ${c} |`);
  }
  lines.push(`| **${S.total}** | **${totNew}** | **${totMod}** | **${totRaw}** |`, '');

  lines.push(S.newListH, '');
  const newObjs = objects.filter((o) => o.changed === 'new');
  for (const o of newObjs) lines.push(`- ${o.kind}.${o.kind === 'Subsystem' ? o.fullPath : o.name}`);
  if (!newObjs.length) lines.push(S.none);
  lines.push('');

  const countTable = (list) => {
    const byKind = new Map();
    for (const o of list) byKind.set(o.kind, (byKind.get(o.kind) || 0) + 1);
    lines.push(`${S.all}: ${list.length}`, '', `| ${S.kind} | ${S.count} |`, '|---|---:|');
    for (const [k, v] of Array.from(byKind.entries()).sort()) lines.push(`| ${k} | ${v} |`);
    lines.push('');
  };
  if (LANG_S) {
    lines.push(S.noSecH(LANG_S), '');
    countTable(objects.filter((o) => !o[`name_${LANG_S}`]));
  }
  lines.push(S.noPrimH(LANG_P, FALLBACK_P), '');
  countTable(objects.filter((o) => !o.syn[LANG_P] && !FALLBACK_P.some((l) => o.syn[l])));
  return lines.join('\n');
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  const t0 = Date.now();
  const args = parseArgs(process.argv.slice(2), { config: 'string', out: 'string', srcRoot: 'string', baseline: 'string' });
  if (args.help) {
    console.log('usage: node inventory.mjs --config <docset.config.json> [--out <factsDir>] [--src-root <dir>] [--baseline <ref>]');
    return 0;
  }
  if (args._.length) throw new UsageError(`unexpected argument ${args._[0]}`);
  const cfg = loadConfig(args.config);
  const summaryLang = (cfg.raw.inventory && cfg.raw.inventory.summaryLanguage) || 'en';
  if (!SUMMARY[summaryLang]) throw new ConfigError(`inventory.summaryLanguage "${summaryLang}" is not supported (built-in: ${Object.keys(SUMMARY).join(', ')})`);

  LANG_P = cfg.languages.primary.code;
  FALLBACK_P = cfg.languages.primary.synonymFallback;
  LANG_S = cfg.languages.secondary ? cfg.languages.secondary.code : null;
  FALLBACK_S = cfg.languages.secondary ? cfg.languages.secondary.synonymFallback : [];
  NORM_LANGS = cfg.normalizeTranslations.map((l) => l.toLowerCase());
  LANG_ITEM_RE = NORM_LANGS.length
    ? new RegExp(`<v8:item>\\s*<v8:lang>(?:${NORM_LANGS.join('|')})<\\/v8:lang>\\s*(?:<v8:content>[^<]*<\\/v8:content>|<v8:content\\s*\\/>)\\s*<\\/v8:item>`, 'g')
    : null;

  WORKTREE_ROOT = cfg.source.worktree;
  if (!WORKTREE_ROOT) throw new ConfigError('source.worktree (or source.repo) is required for the inventory');
  SOURCE_ROOT = args.srcRoot ? path.resolve(args.srcRoot) : cfg.source.srcRoot;
  SRC_REL = path.relative(WORKTREE_ROOT, SOURCE_ROOT).split(path.sep).join('/');
  if (!SRC_REL || SRC_REL.startsWith('..')) throw new ConfigError(`source root ${SOURCE_ROOT} is not inside the worktree ${WORKTREE_ROOT}`);
  if (!fs.existsSync(SOURCE_ROOT) || !fs.statSync(SOURCE_ROOT).isDirectory()) throw new ConfigError(`source root not found: ${SOURCE_ROOT}`);
  const outDir = args.out ? path.resolve(args.out) : cfg.factsDir;
  EXT = detectExtension(SOURCE_ROOT);

  const warnings = [];
  const findings = [];
  // Change status (new / modified vs baseline) comes from git history; without it the statuses
  // would be invented. Say what to do instead of git's bare "not a git repository".
  try { git(['rev-parse', '--verify', 'HEAD']); } catch (e) {
    throw new ConfigError(`${WORKTREE_ROOT} is not a git repository with commits — the inventory reads change status from git history. `
      + 'For a dump without history: git init; git add -A; git commit -m "dump" in it (every object is then "core"). '
      + `(${e.message.split('\n')[0]})`);
  }
  const head = git(['rev-parse', 'HEAD']).trim();
  if (cfg.source.ref) {
    let refHash = null;
    try { refHash = git(['rev-parse', '--verify', `${cfg.source.ref}^{commit}`]).trim(); } catch (e) { warnings.push(`source.ref ${cfg.source.ref} cannot be resolved in the worktree: ${e.message.split('\n')[0]}`); }
    if (refHash && refHash !== head) warnings.push(`worktree HEAD ${head.slice(0, 8)} differs from source.ref ${cfg.source.ref} (${refHash.slice(0, 8)}); the inventory describes HEAD`);
  }
  const dirty = git(['status', '--porcelain', '--', SRC_REL]).trim();
  if (dirty) warnings.push(`the worktree has uncommitted changes under ${SRC_REL}: objects are read from disk, change flags from commits`);

  const baseline = resolveBaseline(args.baseline || cfg.source.baseline);
  const idx = {};
  const changedVsBaseline = markRealChanges(baseline.hash, head, diffAddedModified(baseline.hash, head));
  idx.base = buildChangedIndex(changedVsBaseline);
  idx.subBase = buildSubsystemChangedIndex(changedVsBaseline);
  const compares = cfg.source.compareAlso.map((ref) => {
    const hash = git(['rev-parse', '--verify', `${ref}^{commit}`]).trim();
    const files = markRealChanges(baseline.hash, hash, diffAddedModified(baseline.hash, hash));
    return { ref, key: compareKey(ref), idx: buildChangedIndex(files), subIdx: buildSubsystemChangedIndex(files) };
  });

  const objects = [];
  const countsByKind = {};
  for (const [kind, folder] of Object.entries(KIND_FOLDERS)) {
    const dirPath = path.join(SOURCE_ROOT, folder);
    const extractor = EXTRACTORS[kind];
    let count = 0;
    for (const f of listXmlFiles(dirPath)) {
      const name = f.replace(/\.xml$/, '');
      const xmlPath = path.join(dirPath, f);
      const xml = readIfExists(xmlPath);
      if (!xml) continue;
      const tree = mdRoot(parseXml(xml));
      let rec;
      try { rec = extractor(tree, objFolder(folder, name), name); } catch (e) {
        findings.push(`failed to extract ${kind}/${name}: ${e.message}`);
        continue;
      }
      if (!rec || !rec.name) { findings.push(`empty/failed parse for ${kind}/${name} (file ${xmlPath})`); continue; }
      if (EXT) {
        const kindNode = child(tree, kind);
        rec.belonging = isAdopted(child(kindNode, 'Properties')) ? 'adopted' : 'own';
        if (rec.belonging === 'adopted') rec.extensionAdds = extensionAdds(rec, kindNode, objFolder(folder, name));
      }
      Object.assign(rec, changedStatusFor(idx.base, folder, name));
      for (const c of compares) rec[c.key] = changedStatusFor(c.idx, folder, name).changed;
      objects.push(rec);
      count++;
    }
    countsByKind[kind] = count;
  }

  // Nothing parsed is not an empty configuration: wrong root, or not a Designer XML dump.
  if (!objects.length) {
    throw new ConfigError(`no metadata objects found under ${SOURCE_ROOT} — expected a Designer XML dump (Configuration.xml + Catalogs/, Documents/, …); EDT projects (.mdo) are not supported`);
  }
  // Kind folders this inventory does not read: say so instead of skipping them silently.
  const known = new Set([...Object.values(KIND_FOLDERS), 'Subsystems', 'Ext']);
  const skipped = fs.readdirSync(SOURCE_ROOT, { withFileTypes: true })
    .filter((d) => d.isDirectory() && !known.has(d.name))
    .map((d) => `${d.name} (${listXmlFiles(path.join(SOURCE_ROOT, d.name)).length})`);
  if (skipped.length) warnings.push(`kind folders not inventoried (not in the object reference): ${skipped.join(', ')}`);

  const subsystems = walkSubsystems();
  for (const s of subsystems) {
    Object.assign(s, statusFromEntry(idx.subBase.get(s._xmlRelNoExt)));
    for (const c of compares) s[c.key] = statusFromEntry(c.subIdx.get(s._xmlRelNoExt)).changed;
    delete s._xmlRelNoExt;
    objects.push(s);
  }
  countsByKind.Subsystem = subsystems.length;

  // `subsystems` membership of every non-subsystem object
  const membership = new Map();
  for (const s of subsystems) {
    for (const fullName of s.content) {
      if (!membership.has(fullName)) membership.set(fullName, []);
      membership.get(fullName).push(s.fullPath);
    }
  }
  for (const obj of objects) {
    if (obj.kind === 'Subsystem') continue;
    obj.subsystems = (membership.get(`${obj.kind}.${obj.name}`) || []).slice().sort();
  }

  objects.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind < b.kind ? -1 : 1;
    if (a.kind === 'Subsystem') return a.fullPath < b.fullPath ? -1 : a.fullPath > b.fullPath ? 1 : 0;
    return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
  });

  const header = {
    generatedAt: new Date().toISOString(),
    sourceRoot: SOURCE_ROOT,
    headCommit: head,
    baselineCommit: baseline.hash,
    baselineSubject: baseline.subject,
    baselineDate: baseline.date,
    ...(EXT ? { extension: EXT } : {}),
  };
  const belongingCounts = EXT ? {
    own: objects.filter((o) => o.belonging === 'own').length,
    adopted: objects.filter((o) => o.belonging === 'adopted').length,
    adoptedByKind: objects.filter((o) => o.belonging === 'adopted').reduce((m, o) => ({ ...m, [o.kind]: (m[o.kind] || 0) + 1 }), {}),
  } : null;
  const outJson = path.join(outDir, 'inventory.json');
  const outMd = path.join(outDir, 'inventory-summary.md');
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(outJson, JSON.stringify({ header, countsByKind, objects }, null, 2), 'utf8');
  fs.writeFileSync(outMd, buildMarkdownSummary(SUMMARY[summaryLang], header, countsByKind, objects, subsystems), 'utf8');

  // independent re-read
  const back = JSON.parse(fs.readFileSync(outJson, 'utf8'));
  if (back.objects.length !== objects.length) throw new Error(`re-read mismatch: ${back.objects.length} != ${objects.length} objects`);

  const exitCode = findings.length ? 1 : 0;
  writeJsonReport(path.join(outDir, 'inventory-report.json'), {
    tool: 'inventory.mjs', config: cfg.file, generatedAt: header.generatedAt, exitCode, sourceRoot: SOURCE_ROOT,
    headCommit: head, baseline, compareAlso: cfg.source.compareAlso, languages: cfg.langs, normalizeTranslations: NORM_LANGS,
    objects: objects.length, countsByKind, ...(EXT ? { extension: EXT, belonging: belongingCounts } : {}),
    warnings, findings, outputs: [outJson, outMd], ms: Date.now() - t0,
  });

  console.log(`Elapsed: ${Date.now() - t0}ms`);
  console.log(`Objects: ${objects.length}`);
  if (EXT) {
    console.log(`Extension: ${EXT.name} (purpose ${EXT.purpose}, name prefix ${EXT.namePrefix || '-'}): own ${belongingCounts.own}, adopted ${belongingCounts.adopted}`
      + ` (${Object.entries(belongingCounts.adoptedByKind).sort().map(([k, v]) => `${k}: ${v}`).join(', ')})`);
  }
  console.log('Counts by kind:');
  for (const [k, v] of Object.entries(countsByKind).sort()) console.log(`  ${k}: ${v}`);
  for (const w of warnings) console.log(`warning: ${w}`);
  for (const f of findings) console.log(`FINDING: ${f}`);
  console.log(`Wrote ${outJson}`);
  console.log(`Wrote ${outMd}`);
  console.log(`exit ${exitCode}`);
  return exitCode;
}

runMain('inventory', main);
