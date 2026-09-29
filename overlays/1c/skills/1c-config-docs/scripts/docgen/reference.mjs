#!/usr/bin/env node
// Object reference generator: <facts>/inventory.json -> <contentDir>/<reference.contentFile>
// -> (same builder, same validation) <reference.base>_<suffix>.docx per language.
//
//   node docgen/reference.mjs --config <cfg.json> [--inventory <inventory.json>] [--purposes <purposes.json>]
//                             [--out <dir>] [--content <file>] [--content-only] [--report <file>]
// Content: --content > <out>/<basename of reference.contentFile> when --out is given (a scratch
// build never overwrites the shared content) > <contentDir>/<reference.contentFile>.
// Report: --report > <out>/last-reference.json with --out > <reportDir>/last-reference.json.
// Enrichment: reference.kindDetails (default true) adds a properties table per kind for event
// subscriptions (sources, event, handler), scheduled jobs (method, use, predefined), constants
// (type) and common modules (execution context, line count). A purposes supplement
// (--purposes, else <factsDir>/purposes.json when present: { "<Kind>.<Name>": "text" |
// { "<lang>": "text" } }) adds a "Purpose" column to the chapter tables; objects without a
// purpose get "⚠" and are counted in the introduction and on stdout/stderr.
// Exit codes: 0 = built, 1 = validation failure / unmapped object kind, 2 = execution/config error.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { loadConfig, parseArgs, runMain, toolLabel, UsageError, ConfigError } from '../lib/config.mjs';
import { requireUi } from '../lib/i18n.mjs';
import { loadDocgen } from './lib/load-docgen.mjs';

const { createDocgen, writeReport, printEntry } = await loadDocgen('reference');

// Chapter order of kinds (and the set of kinds the reference knows).
const KIND_ORDER = [
  'Document', 'DocumentJournal', 'Catalog', 'ChartOfAccounts', 'ChartOfCharacteristicTypes', 'ChartOfCalculationTypes',
  'InformationRegister', 'AccumulationRegister', 'AccountingRegister', 'CalculationRegister', 'Enum', 'Constant',
  'Report', 'DataProcessor', 'BusinessProcess', 'Task', 'ExchangePlan', 'Sequence', 'FilterCriterion',
  'CommonModule', 'CommonForm', 'CommonCommand', 'CommonTemplate', 'CommonAttribute', 'CommonPicture', 'StyleItem',
  'Role', 'FunctionalOption', 'SessionParameter', 'EventSubscription', 'ScheduledJob', 'HTTPService', 'WebService',
  'WSReference', 'XDTOPackage', 'Language',
  'DefinedType', 'DocumentNumerator', 'SettingsStorage', 'Style', 'CommandGroup', 'Interface', 'ExternalDataSource', 'IntegrationService', 'Bot',
  'Subsystem',
];
// kinds that get a per-object detail section (members / values / records)
const DETAIL_KINDS = new Set(['Document', 'Catalog', 'ChartOfAccounts', 'ChartOfCharacteristicTypes', 'ChartOfCalculationTypes',
  'InformationRegister', 'AccumulationRegister', 'AccountingRegister', 'CalculationRegister', 'Enum', 'ExchangePlan', 'BusinessProcess', 'Task']);

const DASH = '—';
// inventory `extensionAdds` keys of an adopted object -> UI string of the part (extension mode)
const EXT_ADDS = [
  ['attributes', 'extAddAttributes'], ['tabularSections', 'extAddTabularSections'], ['dimensions', 'extAddDimensions'],
  ['resources', 'extAddResources'], ['accountingFlags', 'extAddAccountingFlags'], ['values', 'extAddValues'],
  ['forms', 'extAddForms'], ['templates', 'extAddTemplates'], ['commands', 'extAddCommands'], ['modules', 'extAddModules'],
];
const GUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const esc = (s) => String(s).replace(/([`*[\]\\])/g, '\\$1');
const code = (s) => '`' + String(s).replace(/`/g, "'") + '`';
const fmtType = (t) => (Array.isArray(t) && t.length ? t.map((x) => String(x).replace(/^(cfg|xs):/, '')).join(', ') : DASH);
const fullName = (o) => `${o.kind}.${o.name}`;

// ---- anchors ----
// Content anchors must match ANCHOR_OK (docgen); docgen turns each into a Word bookmark
// (bookmarkId: "a_" + [A-Za-z0-9_] slug cut to 30 chars + "_" + 8 hex of sha1(anchor) —
// at most 39 chars, letter first, unique per distinct anchor). safeAnchor() is the ONE
// function that builds an anchor from a metadata name, used for the heading and every link:
//   - ASCII 1C name ("Ventas")  -> "<prefix><name>" verbatim (stable across versions; length
//     does not matter, the bookmark is cut + hashed);
//   - anything else (Cyrillic, "ñ", a reserved chapter id) -> "<prefix><ascii slug>-h<8 hex of
//     sha1(prefix+name)>": readable transliteration + hash that keeps it unique. 1C names
//     never contain "-", so a hashed anchor can never equal a verbatim one.
const ANCHOR_OK = /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/;
const RESERVED_ANCHORS = new Set(['ch-intro', 'ch-subsystems', 'ch-outside', 'ch-broken']);
const TRANSLIT = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm',
  н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'kh', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'shch',
  ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya', і: 'i', ї: 'yi', є: 'ye', ґ: 'g', ў: 'u',
};
const asciiSlug = (name, max = 24) => {
  let s = '';
  for (const ch of String(name).normalize('NFD').replace(/\p{M}/gu, '')) {
    if (/[A-Za-z0-9_.]/.test(ch)) { s += ch; continue; }
    const lo = ch.toLowerCase();
    if (TRANSLIT[lo] !== undefined) { const t = TRANSLIT[lo]; s += ch !== lo && t ? t[0].toUpperCase() + t.slice(1) : t; } else s += '_';
  }
  s = s.replace(/_+/g, '_').replace(/^[_.]+|[_.]+$/g, '').slice(0, max).replace(/[_.]+$/, '');
  return s || 'x';
};
export function safeAnchor(prefix, name) {
  const verbatim = `${prefix}${name}`;
  if (ANCHOR_OK.test(verbatim) && !RESERVED_ANCHORS.has(verbatim)) return verbatim;
  return `${prefix}${asciiSlug(name)}-h${crypto.createHash('sha1').update(verbatim).digest('hex').slice(0, 8)}`;
}
const anchorOf = (o) => safeAnchor(`obj-${o.kind}-`, o.name);
const top = (fp) => fp.split('.')[0];

// kinds with a properties table (reference.kindDetails)
const PROP_KINDS = ['EventSubscription', 'ScheduledJob', 'Constant', 'CommonModule'];
const CTX_FLAGS = [['global', 'kdCtxGlobal'], ['server', 'kdCtxServer'], ['serverCall', 'kdCtxServerCall'], ['clientManagedApplication', 'kdCtxClient'],
  ['clientOrdinaryApplication', 'kdCtxOrdinary'], ['externalConnection', 'kdCtxExternal'], ['privileged', 'kdCtxPrivileged']];

function generate(cfg, inv, U, { purposes = null, purposesLabel = null } = {}) {
  const LANGS = cfg.langs;
  const P = LANGS[0];
  const S = LANGS[1] || null;
  const bi = !!S;
  const otherOf = (l) => LANGS.find((x) => x !== l);
  const L = (fn) => Object.fromEntries(LANGS.map((l) => [l, fn(l)]));
  const t = (l, key, args) => U[l].t(key, args);
  const T = (key, args) => L((l) => t(l, key, typeof args === 'function' ? args(l) : args));
  const forms = (l) => ({
    here: U[l].lang(l),
    other: bi ? U[l].lang(otherOf(l)) : undefined,
    sec: bi ? U[l].lang(S) : undefined,
  });
  const normForms = (l) => {
    const fs_ = cfg.normalizeTranslations.map((n) => U[l].lang(n));
    return new Proxy({}, { get: (_, k) => (fs_.every((f) => typeof f[k] === 'string') ? fs_.map((f) => f[k]).join(', ') : undefined) });
  };

  const H = inv.header;
  const objs = inv.objects;
  const unmapped = [...new Set(objs.map((o) => o.kind).filter((k) => !KIND_ORDER.includes(k)))];
  if (unmapped.length) return { unmapped };

  const legacyRe = cfg.reference.legacyNamePattern ? new RegExp(cfg.reference.legacyNamePattern) : null;
  // Extension mode (inventory header.extension): the status is the belonging read from the
  // dump — own -> "new" label, adopted -> "adopted" — independent of git; the git-based
  // `changed` becomes a secondary "since baseline" column (added / changed / —).
  const EXT = H.extension || null;
  const STATUSES = EXT
    ? ['new', 'adopted', ...(legacyRe ? ['legacy'] : [])]
    : ['new', 'modified', 'core', ...(legacyRe ? ['legacy'] : [])];
  const STATUS_KEY = { new: 'statusNew', modified: 'statusModified', core: 'statusCore', legacy: 'statusLegacy', adopted: 'statusAdopted' };
  const statusKey = (o) => {
    if (EXT) {
      if (o.belonging === 'adopted') return 'adopted';
      return legacyRe && legacyRe.test(o.name) ? 'legacy' : 'new';
    }
    if (o.changed === 'new') return 'new';
    if (legacyRe && legacyRe.test(o.name)) return 'legacy';
    return o.changed === 'modified' ? 'modified' : 'core';
  };
  const STATUS = Object.fromEntries(STATUSES.map((s) => [s, T(STATUS_KEY[s])]));
  const statusIn = (s, l) => U[l].raw(STATUS_KEY[s]);
  const SINCE_KEY = { new: 'extSinceNew', modified: 'extSinceModified' };
  const sinceCell = (o) => (SINCE_KEY[o.changed] ? T(SINCE_KEY[o.changed]) : DASH);
  const sinceCells = (o) => (EXT ? [sinceCell(o)] : []);
  const adoptedMeta = (o) => EXT && o.belonging === 'adopted';

  // names: primary always resolved (falls back to the 1C name), secondary may be missing
  const nameIn = (o, l) => (l === P ? (o[`name_${P}`] || o.name) : (o[`name_${l}`] || null));
  const nameOrPrimary = (o, l) => nameIn(o, l) || nameIn(o, P);
  const nameHere = (o) => L((l) => (nameIn(o, l) ? esc(nameIn(o, l)) : DASH));
  const nameOther = (o) => L((l) => (nameIn(o, otherOf(l)) ? esc(nameIn(o, otherOf(l))) : DASH));
  const nameCells = (o) => (bi ? [nameHere(o), nameOther(o)] : [nameHere(o)]);
  const nameHeaders = () => (bi
    ? [T('refColNameHere', (l) => forms(l)), T('refColNameOther', (l) => forms(l))]
    : [T('refColNameMono')]);
  // widths: two name columns (a, b) collapse into one in monolingual mode
  const W = (before, a, b, after) => (bi ? [...before, a, b, ...after] : [...before, a + b, ...after]);
  const shift = (idx, firstAfter) => idx.map((i) => (!bi && i >= firstAfter ? i - 1 : i));

  // ---- purposes supplement (one line per object, written by the analysts) ----
  const PUR = purposes; // Map "<Kind>.<Name>" -> string | { <lang>: string }
  const purposeOf = (o, l) => {
    const p = PUR && PUR.get(fullName(o));
    const v = typeof p === 'string' ? p : p && p[l];
    return typeof v === 'string' && v.trim() ? v.trim() : null;
  };
  const hasPurpose = (o) => LANGS.every((l) => purposeOf(o, l));
  const purHeaders = () => (PUR ? [T('purColPurpose')] : []);
  const purText = (s) => s.replace(/([[\]\\])/g, '\\$1'); // keep `code` / **bold**, no links
  const purCells = (o) => (PUR ? [L((l) => (purposeOf(o, l) ? purText(purposeOf(o, l)) : t(l, 'purMissingCell')))] : []);
  // the purpose column goes right after the name column(s)
  const withPur = (widths, w = 4200) => (PUR ? [...widths.slice(0, bi ? 3 : 2), w, ...widths.slice(bi ? 3 : 2)] : widths);
  const KD = cfg.reference.kindDetails;

  const subs = objs.filter((o) => o.kind === 'Subsystem');
  const members = objs.filter((o) => o.kind !== 'Subsystem');
  const byFull = new Map(members.map((o) => [fullName(o), o]));
  const tops = subs.filter((s) => !s.fullPath.includes('.'));
  const subByPath = new Map(subs.map((s) => [s.fullPath, s]));

  // chapter numbering: 1 intro, 2 subsystem structure, 3.. top-level subsystems, then "outside", then appendix
  const chapters = tops.map((s, i) => ({ key: s.fullPath, n: i + 3, sub: s, anchor: safeAnchor('ch-', s.fullPath) }));
  const outside = { key: null, n: tops.length + 3, anchor: 'ch-outside' };
  const chapterOf = new Map(chapters.map((c) => [c.key, c]));
  const home = (o) => (o.subsystems && o.subsystems.length ? chapterOf.get(top(o.subsystems[0])) : outside);
  const detailed = (o) => DETAIL_KINDS.has(o.kind);
  const chapterTitle = (c) => L((l) => (c.sub
    ? `${c.n}. ${esc(nameOrPrimary(c.sub, l))} (${code(c.sub.name)})`
    : `${c.n}. ${t(l, 'refOutsideTitle')}`));
  const chapterRef = (c) => L((l) => (c.sub
    ? `${t(l, 'refChapAbbr')} ${c.n} ${esc(nameOrPrimary(c.sub, l))}`
    : `${t(l, 'refChapAbbr')} ${c.n} ${t(l, 'refOutsideTitle')}`));
  const linkName = (o) => (detailed(o) ? `[${code(o.name)}](#${anchorOf(o)})` : esc(o.name));

  // ---- statistics ----
  const noSecObjs = bi ? objs.filter((o) => !o[`name_${S}`]) : [];
  let memberCount = 0; let memberNoSec = 0;
  const countMembers = (arr) => { for (const x of arr || []) { memberCount++; if (bi && !x[`name_${S}`]) memberNoSec++; } };
  for (const o of objs) {
    countMembers(o.attributes); countMembers(o.dimensions); countMembers(o.resources); countMembers(o.values);
    for (const ts of o.tabularSections || []) { countMembers([ts]); countMembers(ts.attributes); }
  }
  const dangling = [];
  for (const s of subs) {
    for (const c of s.content || []) {
      if (byFull.has(c) || subByPath.has(c)) continue;
      const subRef = c.startsWith('Subsystem.') ? c.slice('Subsystem.'.length) : null;
      if (subRef && subByPath.has(subRef)) {
        if (subRef === s.fullPath) dangling.push({ sub: s.fullPath, entry: c, self: true });
        continue;
      }
      dangling.push({ sub: s.fullPath, entry: c, guid: GUID_RE.test(c) });
    }
  }
  const multi = members.filter((o) => new Set((o.subsystems || []).map(top)).size > 1);

  const B = [];
  const commit = String(H.headCommit).slice(0, 8);
  const baseline = String(H.baselineCommit).slice(0, 8);

  // ================= 1. Intro =================
  B.push({ type: 'toc', levels: '1-2' });
  B.push({ type: 'h1', text: L((l) => `1. ${t(l, 'refIntroH')}`), anchor: 'ch-intro' });
  B.push({ type: 'p', text: T('refIntro', { n: objs.length, subs: subs.length, inv: code(`${cfg.factsDirLabel}/inventory.json`), tool: code(toolLabel(cfg, 'inventory.mjs')) }) });
  B.push({ type: 'table', headers: [T('refColItem'), T('refColValue')], widths: ['30%', '70%'], mono: [], rows: [
    [T('refRowHead'), code(H.headCommit)],
    ...(EXT ? [[T('extRowExtension'), T('extRowExtensionVal', { name: code(EXT.name), purpose: code(EXT.purpose), prefix: EXT.namePrefix ? code(EXT.namePrefix) : DASH })]] : []),
    [T(EXT ? 'extRowBaseline' : 'refRowBaseline'), `${code(H.baselineCommit)} · ${esc(H.baselineSubject)} · ${H.baselineDate}`],
    [T('refRowGenerated'), String(H.generatedAt)],
    [T('refRowObjects'), T('refRowObjectsVal', { n: objs.length, m: memberCount })],
    ...(EXT ? [[T('extRowBelonging'), T('extRowBelongingVal', {
      own: objs.filter((o) => o.belonging !== 'adopted').length, adopted: objs.filter((o) => o.belonging === 'adopted').length,
    })]] : []),
    ...(PUR ? [[T('purRow'), T('purRowVal', { n: members.filter(hasPurpose).length, m: members.length, k: members.filter((o) => !hasPurpose(o)).length, file: code(purposesLabel) })]] : []),
  ] });

  let sec = 0;
  const h2 = (key, args) => { const no = `1.${++sec}`; return { type: 'h2', text: L((l) => `${no} ${t(l, key, typeof args === 'function' ? args(l) : args)}`) }; };
  B.push(h2('refLegendH'));
  const sinceLabel = (key) => L((l) => `${t(l, 'extColSince')}: ${t(l, key)}`);
  B.push({ type: 'table', headers: [T('refColStatus'), T('refColMeaning')], widths: ['20%', '80%'], rows: EXT ? [
    [STATUS.new, T('extLegendOwn')],
    [STATUS.adopted, T('extLegendAdopted')],
    ...(legacyRe ? [[STATUS.legacy, T('refLegendLegacy')]] : []),
    [sinceLabel('extSinceNew'), T('extLegendSinceNew')],
    [sinceLabel('extSinceModified'), T('extLegendSinceModified')],
  ] : [
    [STATUS.new, T('refLegendNew')],
    [STATUS.modified, T('refLegendModified')],
    [STATUS.core, T('refLegendCore')],
    ...(legacyRe ? [[STATUS.legacy, T('refLegendLegacy')]] : []),
  ] });
  const diffArgs = (l) => ({
    diff: code(`git diff ${baseline}..${commit}`), src: code(cfg.source.srcRootRel), nstr: code('NStr'),
    modified: EXT ? t(l, 'extSinceModified') : statusIn('modified', l), norm: normForms(l),
    own: statusIn('new', l), adopted: EXT ? statusIn('adopted', l) : undefined,
    since: EXT ? t(l, 'extColSince') : undefined, sinceNew: EXT ? t(l, 'extSinceNew') : undefined, sinceModified: EXT ? t(l, 'extSinceModified') : undefined,
  });
  B.push({ type: 'note', kind: 'info', title: T('refStatusHowH'), lines: [
    T(EXT ? 'extStatusHow' : cfg.normalizeTranslations.length ? 'refStatusHow' : 'refStatusHowNoNorm', diffArgs),
  ] });

  B.push(h2('refKindsH'));
  const kindsPresent = KIND_ORDER.filter((k) => objs.some((o) => o.kind === k));
  const kindRows = kindsPresent.map((k) => {
    const ks = objs.filter((o) => o.kind === k);
    const c = (s) => String(ks.filter((o) => statusKey(o) === s).length);
    const cs = (ch) => String(ks.filter((o) => o.changed === ch).length);
    return [code(k), L((l) => U[l].kind(k)), ...(bi ? [L((l) => U[otherOf(l)].kind(k))] : []), String(ks.length), ...STATUSES.map(c), ...(EXT ? ['new', 'modified'].map(cs) : [])];
  });
  const tot = (s) => String(objs.filter((o) => statusKey(o) === s).length);
  const totSince = (ch) => String(objs.filter((o) => o.changed === ch).length);
  kindRows.push([T('refTotalBold'), '', ...(bi ? [''] : []), `**${objs.length}**`, ...STATUSES.map(tot), ...(EXT ? ['new', 'modified'].map(totSince) : [])]);
  B.push({ type: 'table',
    headers: [T('refColKind1C'), L((l) => U[l].lang(l).Name), ...(bi ? [L((l) => U[l].lang(otherOf(l)).Name)] : []), 'Total', ...STATUSES.map((s) => STATUS[s]),
      ...(EXT ? [sinceLabel('extSinceNew'), sinceLabel('extSinceModified')] : [])],
    widths: EXT
      ? [...W([3000], 2600, 2600, [1100, 1100, 1300]), ...(legacyRe ? [1100] : []), 1500, 1500]
      : [...W([3200], 3100, 3100, [1200, 1200, 1300, 1200]), ...(legacyRe ? [1200] : [])],
    rows: kindRows });

  if (bi) {
    B.push(h2('refMissingH', (l) => forms(l)));
    B.push({ type: 'p', text: T('refMissing', (l) => ({ ...forms(l), nObj: noSecObjs.length, nMem: memberNoSec, mem: memberCount, dash: DASH })) });
    if (noSecObjs.length) B.push({ type: 'bullets', items: noSecObjs.map((o) => `${code(fullName(o))} — ${esc(nameIn(o, P))}`) });
  }

  B.push(h2('refHowReadH'));
  B.push({ type: 'bullets', items: [
    T('refHowRead1'), T('refHowRead2'), T('refHowRead3', { multi: multi.length }), T('refHowRead4', { outside: outside.n }),
  ] });

  // ================= 2. Subsystem tree =================
  B.push({ type: 'h1', text: L((l) => `2. ${t(l, 'refSubsH')}`), anchor: 'ch-subsystems' });
  B.push({ type: 'p', text: T('refSubsCount', { subs: subs.length, tops: tops.length }) });
  B.push({ type: 'table', headers: [T('refColPath'), ...nameHeaders(), T('refColStatus'), ...(EXT ? [T('extColSince')] : []), T('refColObjects')],
    widths: EXT ? W([4200], 3100, 3100, [1400, 1500, 1270]) : W([4600], 3600, 3600, [1400, 1370]), mono: [0],
    rows: subs.map((s) => {
      const depth = s.fullPath.split('.').length - 1;
      const ch = chapterOf.get(top(s.fullPath));
      const label = depth === 0 && ch ? `[${code(s.fullPath)}](#${ch.anchor})` : esc(`${'· '.repeat(depth)}${s.fullPath}`);
      return [label, ...nameCells(s), STATUS[statusKey(s)], ...sinceCells(s), String((s.content || []).length)];
    }) });

  // ================= chapters =================
  const inChapter = (c) => members.filter((o) => (c.sub ? (o.subsystems || []).some((p) => top(p) === c.key) : !(o.subsystems || []).length));
  for (const c of [...chapters, outside]) {
    const list = inChapter(c);
    B.push({ type: 'h1', text: chapterTitle(c), anchor: c.anchor });
    if (c.sub) {
      const nested = subs.filter((s) => s.fullPath.startsWith(`${c.key}.`)).map((s) => code(s.fullPath));
      B.push({ type: 'p', text: L((l) => t(l, 'refChapPara', {
        n: list.length, status: statusIn(statusKey(c.sub), l),
        nested: nested.length ? t(l, 'refNested', { list: nested.join(', ') }) : '',
      })) });
    } else {
      B.push({ type: 'p', text: T('refOutsidePara', { n: list.length }) });
    }
    if (!list.length) continue;
    let k = 0;
    for (const kind of KIND_ORDER) {
      const ks = list.filter((o) => o.kind === kind).sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
      if (!ks.length) continue;
      k++;
      B.push({ type: 'h2', text: L((l) => `${c.n}.${k} ${U[l].kind(kind, true)} (${ks.length})`), anchor: `${c.anchor}-${kind}` });
      const headers = [T('refColName1C'), ...nameHeaders(), ...purHeaders(), T('refColStatus'), ...(EXT ? [T('extColSince')] : []), T('refColSubsystems')];
      B.push({ type: 'table',
        headers,
        widths: withPur(EXT ? W([3700], 3100, 3100, [1270, 1400, 2000]) : W([3700], 3500, 3500, [1170, 2700])),
        mono: PUR ? [0, headers.length - 1] : EXT ? shift([0, 5], 2) : shift([0, 4], 2),
        rows: ks.map((o) => [linkName(o), ...nameCells(o), ...purCells(o), STATUS[statusKey(o)], ...sinceCells(o), (o.subsystems || []).length ? esc(o.subsystems.join(', ')) : DASH]) });
      if (KD && PROP_KINDS.includes(kind)) B.push(...propsTable(kind, ks));
      if (!DETAIL_KINDS.has(kind)) continue;
      const elsewhere = ks.filter((o) => home(o) !== c);
      for (const o of ks.filter((x) => home(x) === c)) B.push(...detail(o));
      if (elsewhere.length) {
        const groups = new Map();
        for (const o of elsewhere) { const h = home(o); if (!groups.has(h)) groups.set(h, []); groups.get(h).push(o); }
        for (const [h, os] of groups) {
          const lst = os.map((o) => `[${code(o.name)}](#${anchorOf(o)})`).join(', ');
          const ref = chapterRef(h);
          B.push({ type: 'p', italic: true, text: L((l) => t(l, 'refCardIn', { ref: ref[l], anchor: h.anchor, list: lst })) });
        }
      }
    }
  }

  // ================= Appendix A: broken references =================
  B.push({ type: 'h1', text: T('refBrokenH'), anchor: 'ch-broken' });
  const guids = dangling.filter((d) => d.guid);
  const selfRefs = dangling.filter((d) => d.self);
  const other = dangling.filter((d) => !d.guid && !d.self);
  B.push({ type: 'p', text: L((l) => {
    const extra = [other.length ? t(l, 'refBrokenOther', { n: other.length }) : '', selfRefs.length ? t(l, 'refBrokenSelf', { n: selfRefs.length }) : ''].filter(Boolean);
    return t(l, 'refBroken', { guids: guids.length, extra: extra.length ? t(l, 'refBrokenExtra', { list: extra.join(t(l, 'refAnd')) }) : '' });
  }) });
  if (dangling.length) {
    B.push({ type: 'table', headers: [T('refColSubsystem'), T('refColEntry'), T('refColProblem')], widths: [4200, 5000, 5370], mono: [0, 1],
      rows: dangling.map((d) => [esc(d.sub), esc(d.entry), d.guid
        ? T('refProbGuid')
        : d.self ? T('refProbSelf') : T('refProbKind', { kind: code(d.entry.split('.')[0]) })]) });
  }

  // ---- kind properties table (reference.kindDetails) ----
  function propsTable(kind, ks) {
    // an adopted object's properties are defined by the base configuration: not printed
    const P_ = (o, fn) => (adoptedMeta(o) ? DASH : fn(o));
    const yesNo = (v) => T(v ? 'kdYes' : 'kdNo');
    const codes = (arr) => (Array.isArray(arr) && arr.length ? arr.map((x) => code(String(x).replace(/^cfg:/, ''))).join(', ') : DASH);
    const one = (v) => (v === undefined || v === null || v === '' ? DASH : code(v));
    let headers; let widths; let rows;
    if (kind === 'EventSubscription') {
      headers = [T('refColName1C'), T('kdColSources'), T('kdColEvent'), T('kdColHandler')];
      widths = [3600, 5400, 1800, 3770];
      rows = ks.map((o) => [code(o.name), P_(o, (x) => codes(x.sourceTypes)), P_(o, (x) => one(x.event)), P_(o, (x) => one(x.handler))]);
    } else if (kind === 'ScheduledJob') {
      headers = [T('refColName1C'), T('kdColMethod'), T('kdColUse'), T('kdColPredefined')];
      widths = [4200, 6770, 1800, 1800];
      rows = ks.map((o) => [code(o.name), P_(o, (x) => one(x.methodName)), P_(o, (x) => yesNo(x.use)), P_(o, (x) => yesNo(x.predefined))]);
    } else if (kind === 'Constant') {
      headers = [T('refColName1C'), T('kdColType')];
      widths = [6000, 8570];
      rows = ks.map((o) => [code(o.name), P_(o, (x) => esc(fmtType(x.type)))]);
    } else {
      headers = [T('refColName1C'), T('kdColContext'), T('kdColLines')];
      widths = [4200, 8870, 1500];
      rows = ks.map((o) => [code(o.name), P_(o, (x) => L((l) => {
        const f = CTX_FLAGS.filter(([k]) => x[k]).map(([, key]) => t(l, key));
        if (x.returnValuesReuse && x.returnValuesReuse !== 'DontUse') f.push(t(l, 'kdCtxReuse', { v: x.returnValuesReuse }));
        return f.length ? f.join(', ') : DASH;
      })), P_(o, (x) => (typeof x.moduleLineCount === 'number' ? String(x.moduleLineCount) : DASH))]);
    }
    return [
      { type: 'p', text: L((l) => t(l, 'kdPropsTitle', { kind: U[l].kind(kind, true) })) },
      { type: 'table', headers, widths, mono: [0], rows },
    ];
  }

  // ---- object detail card ----
  function detail(o) {
    const out = [];
    out.push({ type: 'h3', text: L((l) => (nameIn(o, l) ? `${code(o.name)} — ${esc(nameIn(o, l))}` : code(o.name))), anchor: anchorOf(o) });
    const meta = L((l) => [`**${U[l].kind(o.kind)}** · ${statusIn(statusKey(o), l)}`
      + (EXT && SINCE_KEY[o.changed] ? ` · ${t(l, 'extColSince')}: ${t(l, SINCE_KEY[o.changed])}` : '')]);
    const add = (key, v) => {
      if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) return;
      const s = Array.isArray(v) ? v.map(code).join(', ') : code(v);
      for (const l of LANGS) meta[l].push(`${U[l].raw(key)}: ${s}`);
    };
    add('lblSubsystems', o.subsystems);
    // an adopted object's properties are defined by the base configuration: the extension dump
    // does not carry them, so the property lines are not printed (they would read as defaults)
    const K = adoptedMeta(o) ? null : o.kind;
    if (K === 'Document') { add('lblPosting', o.posting); add('lblRealTimePosting', o.realTimePosting); add('lblNumerator', o.numerator); add('lblBasedOn', o.basedOn); }
    if (K === 'Catalog') { add('lblHierarchical', o.hierarchical ? 'true' : undefined); add('lblOwners', o.owners); add('lblCodeLength', o.codeLength); add('lblDescriptionLength', o.descriptionLength); add('lblPredefined', o.predefinedCount || undefined); }
    if (K === 'InformationRegister') { add('lblPeriodicity', o.periodicity); add('lblWriteMode', o.writeMode); }
    if (K === 'AccumulationRegister') add('lblRegisterType', o.registerType);
    if (K === 'AccountingRegister') { add('lblChartOfAccounts', o.chartOfAccounts); add('lblCorrespondence', o.correspondence === undefined ? undefined : String(o.correspondence)); }
    if (K === 'CalculationRegister') { add('lblActionPeriod', o.actionPeriod === undefined ? undefined : String(o.actionPeriod)); add('lblSchedule', o.schedule); }
    if (K === 'ChartOfCharacteristicTypes') add('lblValueType', o.valueType ? fmtType(o.valueType) : undefined);
    if (K === 'ChartOfAccounts') add('lblMaxExtDimensions', o.maxExtDimensionCount);
    out.push({ type: 'p', text: L((l) => meta[l].join(' · ')) });
    if (o.comment) out.push({ type: 'p', italic: true, text: `${esc(o.comment)}` });
    const adopted = adoptedMeta(o);
    if (adopted) {
      const A = o.extensionAdds || {};
      const present = EXT_ADDS.filter(([k]) => (A[k] || []).length);
      out.push({ type: 'p', text: present.length
        ? L((l) => t(l, 'extAdds', { list: present.map(([k, key]) => `${t(l, key)} ${A[k].map(code).join(', ')}`).join('; ') }))
        : T('extAddsNone') });
    }
    // member borrowed from the base configuration: "Attribute · adopted"
    const mark = (label, x) => (EXT && x.belonging === 'adopted' ? L((l) => `${label[l]} · ${statusIn('adopted', l)}`) : label);
    if (o.kind === 'Document' && (o.registerRecords || []).length) {
      const recs = o.registerRecords.map((r) => (byFull.has(r) && detailed(byFull.get(r)) ? `[${code(r)}](#${anchorOf(byFull.get(r))})` : code(r))).join(', ');
      out.push({ type: 'p', text: T('refMovements', { list: recs }) });
    }
    if (o.kind === 'Enum') {
      if ((o.values || []).length) {
        const valName = (v) => (EXT && v.belonging === 'adopted' ? L((l) => `${esc(v.name)} · ${statusIn('adopted', l)}`) : esc(v.name));
        out.push({ type: 'table', headers: [T('refColValue1C'), ...nameHeaders()],
          widths: W([4600], 5000, 4970, []), mono: [0], rows: o.values.map((v) => [valName(v), ...nameCells(v)]) });
      } else if (!adopted) out.push({ type: 'p', text: T('refNoValues') });
      return out;
    }
    const rows = [];
    const part = { dim: T('partDimension'), res: T('partResource'), att: T('partAttribute') };
    const same = (s) => L(() => s);
    for (const x of o.dimensions || []) rows.push([mark(part.dim, x), esc(x.name), ...nameCells(x), esc(fmtType(x.type))]);
    for (const x of o.resources || []) rows.push([mark(part.res, x), esc(x.name), ...nameCells(x), esc(fmtType(x.type))]);
    for (const x of o.attributes || []) rows.push([mark(part.att, x), esc(x.name), ...nameCells(x), esc(fmtType(x.type))]);
    for (const ts of o.tabularSections || []) {
      rows.push([mark(L((l) => `**${t(l, 'partTabular')}**`), ts), `**${esc(ts.name)}**`, ...nameCells(ts), DASH]);
      for (const x of ts.attributes || []) {
        const lbl = `↳ ${esc(ts.name)}`;
        rows.push([EXT && x.belonging === 'adopted' ? mark(same(lbl), x) : lbl, esc(x.name), ...nameCells(x), esc(fmtType(x.type))]);
      }
    }
    if (rows.length) {
      out.push({ type: 'table', headers: [T('refColPart'), T('refColName1C'), ...nameHeaders(), T('refColType')],
        widths: W([2000, 3000], 3000, 3000, [3570]), mono: shift([1, 4], 3), rows });
    } else if (!adopted) out.push({ type: 'p', text: T('refNoAttributes') });
    return out;
  }

  const defaultSet = cfg.sets[0].id;
  const content = {
    _comment: `GENERATED by reference.mjs from ${cfg.factsDirLabel}/inventory.json — do not edit by hand.`,
    id: cfg.reference.id,
    base: cfg.reference.base,
    ...(cfg.reference.set !== defaultSet ? { set: cfg.reference.set } : {}),
    orientation: 'landscape',
    title: T('refTitle'),
    subtitle: T('refSubtitle', { n: objs.length }),
    source: { commit, date: String(H.generatedAt).slice(0, 10) },
    blocks: B,
  };
  const stats = {
    objects: objs.length, subsystems: subs.length, topLevel: tops.length, outside: inChapter(outside).length,
    detailCards: members.filter(detailed).length, multiTopLevel: multi.length,
    missingSecondaryObjects: noSecObjs.length, members: memberCount, missingSecondaryMembers: memberNoSec,
    danglingGuid: guids.length, danglingOther: other.length, selfReferences: selfRefs.length, blocks: B.length,
    ...(EXT ? { extension: EXT.name, own: objs.filter((o) => o.belonging !== 'adopted').length, adopted: objs.filter((o) => o.belonging === 'adopted').length } : {}),
    kindDetails: KD ? PROP_KINDS.filter((k) => members.some((o) => o.kind === k)) : false,
    ...(PUR ? { purposes: members.filter(hasPurpose).length, purposesMissing: members.filter((o) => !hasPurpose(o)).length } : {}),
  };
  const missingPurposes = PUR ? members.filter((o) => !hasPurpose(o)).map(fullName) : [];
  return { content, stats, missingPurposes };
}

async function main() {
  const startedAt = new Date().toISOString();
  const args = parseArgs(process.argv.slice(2), { config: 'string', inventory: 'string', purposes: 'string', out: 'string', content: 'string', contentOnly: 'bool', report: 'string' });
  if (args.help) {
    console.log('usage: node docgen/reference.mjs --config <cfg.json> [--inventory <inventory.json>] [--purposes <purposes.json>] [--out <dir>] [--content <file>] [--content-only] [--report <file>]');
    return 0;
  }
  if (args._.length) throw new UsageError(`unexpected argument ${args._[0]}`);
  const cfg = loadConfig(args.config);
  const U = requireUi(cfg, cfg.langs, ['docx', 'status', 'reference']);
  const dg = createDocgen(cfg);
  const inventoryFile = args.inventory ? path.resolve(args.inventory) : path.join(cfg.factsDir, 'inventory.json');
  const reportFile = args.report ? path.resolve(args.report)
    : args.out ? path.join(path.resolve(args.out), 'last-reference.json')
      : path.join(cfg.reportDir, 'last-reference.json');
  const generated = args.content ? path.resolve(args.content)
    : args.out ? path.join(path.resolve(args.out), path.basename(cfg.reference.contentFile))
      : cfg.reference.contentFile;
  if (cfg.reference.kindDetails) Object.assign(U, requireUi(cfg, cfg.langs, ['docx', 'status', 'reference', 'kindDetails']));

  // purposes supplement: --purposes, else <factsDir>/purposes.json when present
  const purposesFile = args.purposes ? path.resolve(args.purposes) : path.join(cfg.factsDir, 'purposes.json');
  let purposes = null; const purposeWarnings = [];
  if (args.purposes || fs.existsSync(purposesFile)) {
    let pj;
    try { pj = JSON.parse(fs.readFileSync(purposesFile, 'utf8').replace(/^\uFEFF/, '')); } catch (e) { throw new ConfigError(`cannot read purposes ${purposesFile}: ${e.message}`); }
    if (!pj || typeof pj !== 'object' || Array.isArray(pj)) throw new ConfigError(`${purposesFile}: must be an object { "<Kind>.<Name>": "text" | { "<lang>": "text" } }`);
    purposes = new Map();
    for (const [k, v] of Object.entries(pj)) {
      if (k.startsWith('$') || k.startsWith('_')) continue;
      const okV = typeof v === 'string' || (v && typeof v === 'object' && !Array.isArray(v) && Object.values(v).every((x) => typeof x === 'string'));
      if (!okV) throw new ConfigError(`${purposesFile}: "${k}" must be a string or an object of strings keyed by language`);
      purposes.set(k, v);
    }
    Object.assign(U, requireUi(cfg, cfg.langs, ['docx', 'status', 'reference', 'purposes']));
  }

  let inv;
  try { inv = JSON.parse(fs.readFileSync(inventoryFile, 'utf8')); } catch (e) { throw new ConfigError(`cannot read inventory ${inventoryFile}: ${e.message}`); }
  if (!inv || !inv.header || !Array.isArray(inv.objects)) throw new ConfigError(`${inventoryFile} is not an inventory.json (no header/objects)`);
  if (inv.header.extension) {
    Object.assign(U, requireUi(cfg, cfg.langs, ['docx', 'status', 'reference', 'extension']));
    if (inv.objects.some((o) => o.belonging === undefined)) throw new ConfigError(`${inventoryFile}: header.extension is set but some objects have no "belonging" — rebuild it with the current inventory.mjs`);
  }
  if (purposes) {
    const known = new Set(inv.objects.filter((o) => o.kind !== 'Subsystem').map(fullName));
    for (const k of purposes.keys()) if (!known.has(k)) purposeWarnings.push(`purposes: "${k}" is not an object of the inventory (Subsystem entries are not shown)`);
  }
  const g = generate(cfg, inv, U, { purposes, purposesLabel: purposes ? (args.purposes ? path.basename(purposesFile) : `${cfg.factsDirLabel}/purposes.json`) : null });
  if (g.unmapped) {
    console.error(`FAIL  unmapped object kinds (add them to KIND_ORDER in reference.mjs and to uiStrings.<lang>.kinds): ${g.unmapped.join(', ')}`);
    writeReport(reportFile, { tool: 'reference.mjs', config: cfg.file, startedAt, finishedAt: new Date().toISOString(), exitCode: 1, unmappedKinds: g.unmapped, files: [] });
    return 1;
  }
  fs.mkdirSync(path.dirname(generated), { recursive: true });
  fs.writeFileSync(generated, JSON.stringify(g.content, null, 1) + '\n', 'utf8');
  console.log(`content -> ${generated}  ${fs.statSync(generated).size} bytes`);
  console.log(`stats   ${JSON.stringify(g.stats)}`);
  if (purposes) {
    console.log(`purposes ${purposesFile}: ${g.stats.purposes} described, ${g.stats.purposesMissing} without purpose (⚠)`);
    if (g.missingPurposes.length) console.error(`⚠ no purpose: ${g.missingPurposes.slice(0, 40).join(', ')}${g.missingPurposes.length > 40 ? ` … +${g.missingPurposes.length - 40}` : ''}`);
    for (const w of purposeWarnings) console.error(`warning: ${w}`);
  }
  const purposeReport = purposes ? { purposes: { file: purposesFile, missing: g.missingPurposes, warnings: purposeWarnings } } : {};
  if (args.contentOnly) {
    writeReport(reportFile, { tool: 'reference.mjs', config: cfg.file, startedAt, finishedAt: new Date().toISOString(), exitCode: 0, contentOnly: true, inventory: inventoryFile, content: generated, stats: g.stats, ...purposeReport, files: [] });
    return 0;
  }
  let e;
  const t0 = Date.now();
  try { e = await dg.buildFile(generated, { out: args.out }); } catch (err) {
    e = { content: generated, status: 'error', error: err && err.stack ? err.stack.split('\n').slice(0, 3).join(' | ') : String(err), errors: [], warnings: [], outputs: [] };
  }
  printEntry(e);
  const exitCode = e.status === 'error' ? 2 : e.status === 'invalid' ? 1 : 0;
  writeReport(reportFile, { tool: 'reference.mjs', config: cfg.file, startedAt, finishedAt: new Date().toISOString(), seconds: (Date.now() - t0) / 1000, exitCode, inventory: inventoryFile, content: generated, stats: g.stats, ...purposeReport, files: [e] });
  console.log(`exit ${exitCode} (${((Date.now() - t0) / 1000).toFixed(1)} s) · report ${reportFile}`);
  return exitCode;
}

runMain('reference', main);
