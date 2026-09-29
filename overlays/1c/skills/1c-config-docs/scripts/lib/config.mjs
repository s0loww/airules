// Shared config loader for the 1c-config-docs scripts.
//
// One JSON file (see ../../assets/docset.config.example.json) drives every script.
// Relative paths: `outputRoot` is resolved against the config file's directory;
// `factsDir`, `pngDir`, `contentDir`, `reportDir` and every `sets[].dir` against
// `outputRoot`; `source.srcRoot` against `source.worktree` (or `source.repo`).
//
// Errors in the config are ConfigError -> the scripts exit with code 2.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

export class ConfigError extends Error {}
export class UsageError extends Error {}

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const LANG_RE = /^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$/;
const TOP_KEYS = ['project', 'source', 'languages', 'normalizeTranslations', 'inventory', 'outputRoot', 'factsDir', 'buildDir', 'pngDir',
  'contentDir', 'reportDir', 'sets', 'reference', 'nav', 'docgen', 'uiStrings', 'archify', 'clearCopy', 'date'];
const SET_KEYS = ['id', 'dir', 'diagramPrefix', 'title', 'lead', 'navTitle', 'about', 'internalDocs', 'readmeIntro', 'staleWhen'];
const SUFFIX_RE = /^[A-Za-z0-9]+$/;

// ---------------------------------------------------------------- file names
// One rule for every file base name / file-name prefix the scripts produce (config
// `reference.base`, `sets[].diagramPrefix`, content `base`, make-nav expectations):
// Unicode letters and digits (any script, combining marks allowed) plus `_ . -`; first
// character a letter or digit. On top of that, full names must not end with "." and must
// not be a Windows reserved device name (CON, PRN, AUX, NUL, COM1-9, LPT1-9 — also with an
// extension, "CON.docx"). Spaces and every character Windows forbids (<>:"/\|?* and
// control characters) are excluded by construction.
const FILE_CHARS_RE = /^[\p{L}\p{N}][\p{L}\p{N}\p{M}_.-]*$/u;
const WIN_RESERVED_RE = /^(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])$/i;
export const FILE_NAME_RULE = 'Unicode letters/digits plus _ . - (first a letter or digit; no spaces, no <>:"/\\|?*, no trailing ".", not a Windows reserved name)';

/** null when `name` is a valid file base (or, with prefix: true, a file-name prefix); else the reason. */
export function fileBaseError(name, { prefix = false } = {}) {
  if (typeof name !== 'string' || !name) return 'required non-empty string';
  if (name.length > 150) return 'longer than 150 characters';
  if (!FILE_CHARS_RE.test(name)) return `must consist of ${FILE_NAME_RULE}`;
  if (!prefix) {
    if (name.endsWith('.')) return 'must not end with "."';
    if (WIN_RESERVED_RE.test(name.split('.')[0])) return `"${name.split('.')[0]}" is a reserved Windows device name`;
  }
  return null;
}

/** Minimal argv parser. spec: { name: 'string' | 'bool' | 'list' }. Positional args -> _ */
export function parseArgs(argv, spec) {
  const out = { _: [] };
  for (const [k, t] of Object.entries(spec)) if (t === 'list') out[k] = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') { out.help = true; continue; }
    if (!a.startsWith('--')) { out._.push(a); continue; }
    const name = a.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    const t = spec[name];
    if (!t) throw new UsageError(`unknown option ${a}`);
    if (t === 'bool') { out[name] = true; continue; }
    const v = argv[++i];
    if (v === undefined || v.startsWith('--')) throw new UsageError(`${a} requires a value`);
    if (t === 'list') out[name].push(v); else out[name] = v;
  }
  return out;
}

export function readJsonFile(file, what = 'JSON') {
  let text;
  try { text = fs.readFileSync(file, 'utf8'); } catch (e) { throw new ConfigError(`cannot read ${what} ${file}: ${e.message}`); }
  try { return JSON.parse(text.replace(/^﻿/, '')); } catch (e) { throw new ConfigError(`${what} ${file} is not valid JSON: ${e.message}`); }
}

export function today() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export const samePath = (a, b) => {
  const na = path.resolve(a); const nb = path.resolve(b);
  return process.platform === 'win32' ? na.toLowerCase() === nb.toLowerCase() : na === nb;
};

/**
 * Text value accessor for config / content bilingual values.
 * string -> itself; { <code>: string } -> that language; missing -> undefined.
 */
export function textIn(v, code) {
  if (v === undefined || v === null) return undefined;
  if (typeof v === 'string' || typeof v === 'number') return String(v);
  if (isObj(v) && typeof v[code] === 'string') return v[code];
  return undefined;
}

function checkLangText(v, p, langs, errors, optional = true) {
  if (v === undefined || v === null) { if (!optional) errors.push(`${p}: required`); return; }
  if (typeof v === 'string') return;
  if (!isObj(v)) { errors.push(`${p}: must be a string or an object keyed by language code`); return; }
  for (const l of langs) if (typeof v[l] !== 'string') errors.push(`${p}.${l}: missing (every configured language is required)`);
}

/**
 * Load and normalize a docset config. Throws ConfigError on any problem.
 * Returns a plain object; `raw` keeps the file as read.
 */
export function loadConfig(file) {
  if (!file) throw new UsageError('--config <path> is required');
  const abs = path.resolve(file);
  const raw = readJsonFile(abs, 'config');
  if (!isObj(raw)) throw new ConfigError(`config ${abs}: top level must be an object`);
  const errors = [];
  const base = path.dirname(abs);
  const unknownKeys = (o, allowed, p) => {
    if (!isObj(o)) return;
    for (const k of Object.keys(o)) if (!allowed.includes(k) && !k.startsWith('$') && !k.startsWith('_')) errors.push(`${p}${k}: unknown key (typo?)`);
  };
  unknownKeys(raw, TOP_KEYS, '');
  unknownKeys(raw.source, ['repo', 'ref', 'worktree', 'srcRoot', 'baseline', 'compareAlso', 'commit'], 'source.');
  unknownKeys(raw.reference, ['base', 'id', 'contentFile', 'set', 'legacyNamePattern', 'kindDetails'], 'reference.');
  unknownKeys(raw.nav, ['readmeLanguage', 'toolLabel', 'rootDocPattern', 'rootDiagramPattern'], 'nav.');
  unknownKeys(raw.inventory, ['summaryLanguage'], 'inventory.');
  unknownKeys(raw.docgen, ['creator'], 'docgen.');
  unknownKeys(raw.languages, ['primary', 'secondary'], 'languages.');
  if (isObj(raw.languages)) for (const k of ['primary', 'secondary']) unknownKeys(raw.languages[k], ['code', 'suffix', 'synonymFallback'], `languages.${k}.`);
  if (Array.isArray(raw.sets)) raw.sets.forEach((s, i) => unknownKeys(s, SET_KEYS, `sets[${i}].`));

  // ---- languages ----
  const L = raw.languages;
  const lang = (o, p, required) => {
    if (o === undefined || o === null) { if (required) errors.push(`${p}: required`); return null; }
    if (!isObj(o)) { errors.push(`${p}: must be an object {code, suffix?, synonymFallback?}`); return null; }
    if (typeof o.code !== 'string' || !LANG_RE.test(o.code)) { errors.push(`${p}.code: required language code like "es"`); return null; }
    const suffix = o.suffix === undefined ? o.code : o.suffix;
    if (typeof suffix !== 'string' || !SUFFIX_RE.test(suffix)) errors.push(`${p}.suffix: must match [A-Za-z0-9]+`);
    const fb = o.synonymFallback === undefined ? [] : o.synonymFallback;
    if (!Array.isArray(fb) || fb.some((x) => typeof x !== 'string')) errors.push(`${p}.synonymFallback: must be an array of language codes`);
    return { code: o.code, suffix, synonymFallback: Array.isArray(fb) ? fb : [] };
  };
  if (!isObj(L)) errors.push('languages: required object {primary, secondary?}');
  const primary = isObj(L) ? lang(L.primary, 'languages.primary', true) : null;
  const secondary = isObj(L) ? lang(L.secondary, 'languages.secondary', false) : null;
  if (primary && secondary) {
    if (primary.code === secondary.code) errors.push('languages: primary and secondary codes must differ');
    if (primary.suffix === secondary.suffix) errors.push('languages: primary and secondary suffixes must differ');
  }
  const langs = [primary, secondary].filter(Boolean).map((x) => x.code);

  // ---- source ----
  const S = isObj(raw.source) ? raw.source : {};
  if (raw.source !== undefined && !isObj(raw.source)) errors.push('source: must be an object');
  const worktree = S.worktree ? path.resolve(base, S.worktree) : (S.repo ? path.resolve(base, S.repo) : null);
  const srcRootRel = S.srcRoot === undefined ? 'src/main' : S.srcRoot;
  if (typeof srcRootRel !== 'string' || !srcRootRel) errors.push('source.srcRoot: must be a non-empty relative path');
  const compareAlso = S.compareAlso === undefined ? [] : S.compareAlso;
  if (!Array.isArray(compareAlso) || compareAlso.some((x) => typeof x !== 'string' || !x)) errors.push('source.compareAlso: must be an array of git refs');
  for (const k of ['repo', 'ref', 'worktree', 'baseline', 'commit']) {
    if (S[k] !== undefined && (typeof S[k] !== 'string' || !S[k])) errors.push(`source.${k}: must be a non-empty string`);
  }
  const normalizeTranslations = raw.normalizeTranslations === undefined ? [] : raw.normalizeTranslations;
  if (!Array.isArray(normalizeTranslations) || normalizeTranslations.some((x) => typeof x !== 'string' || !LANG_RE.test(x))) {
    errors.push('normalizeTranslations: must be an array of language codes');
  }

  // ---- output layout ----
  if (typeof raw.outputRoot !== 'string' || !raw.outputRoot) errors.push('outputRoot: required path');
  const outputRoot = typeof raw.outputRoot === 'string' ? path.resolve(base, raw.outputRoot) : base;
  const sub = (k, def) => {
    const v = raw[k] === undefined ? def : raw[k];
    if (typeof v !== 'string' || !v) { errors.push(`${k}: must be a non-empty path`); return path.join(outputRoot, def); }
    return path.resolve(outputRoot, v);
  };
  const factsDirLabel = typeof raw.factsDir === 'string' ? raw.factsDir.replace(/\\/g, '/') : '_facts';
  const factsDir = sub('factsDir', '_facts');
  const pngDir = sub('pngDir', '_png');
  const contentDir = sub('contentDir', '_build/docgen/content');
  const reportDir = sub('reportDir', raw.buildDir ? path.join(raw.buildDir, 'reports') : '_reports');
  const buildDir = raw.buildDir === undefined ? null : raw.buildDir;
  if (buildDir !== null && (typeof buildDir !== 'string' || !buildDir)) errors.push('buildDir: must be a non-empty string');

  // ---- sets ----
  const sets = [];
  if (!Array.isArray(raw.sets) || !raw.sets.length) errors.push('sets: required non-empty array');
  else raw.sets.forEach((s, i) => {
    const p = `sets[${i}]`;
    if (!isObj(s)) { errors.push(`${p}: must be an object`); return; }
    if (typeof s.id !== 'string' || !/^[A-Za-z0-9_.-]+$/.test(s.id)) errors.push(`${p}.id: required [A-Za-z0-9_.-]+`);
    if (typeof s.dir !== 'string' || !s.dir) errors.push(`${p}.dir: required path (relative to outputRoot)`);
    const dpErr = fileBaseError(s.diagramPrefix, { prefix: true });
    if (dpErr) errors.push(`${p}.diagramPrefix: required file-name prefix, e.g. "bl-" (${dpErr})`);
    checkLangText(s.title, `${p}.title`, langs, errors, false);
    checkLangText(s.lead, `${p}.lead`, langs, errors);
    checkLangText(s.navTitle, `${p}.navTitle`, langs, errors);
    checkLangText(s.about, `${p}.about`, langs, errors);
    const internalDocs = s.internalDocs === undefined ? [] : s.internalDocs;
    if (!Array.isArray(internalDocs) || internalDocs.some((x) => typeof x !== 'string')) errors.push(`${p}.internalDocs: must be an array of document base names`);
    const staleWhen = s.staleWhen === undefined ? [] : s.staleWhen;
    if (!Array.isArray(staleWhen)) errors.push(`${p}.staleWhen: must be an array of texts`);
    sets.push({
      id: s.id, dirRel: typeof s.dir === 'string' ? s.dir : '.', dir: path.resolve(outputRoot, typeof s.dir === 'string' ? s.dir : '.'),
      diagramPrefix: s.diagramPrefix, title: s.title, lead: s.lead, navTitle: s.navTitle, about: s.about,
      internalDocs: Array.isArray(internalDocs) ? internalDocs : [], readmeIntro: s.readmeIntro, staleWhen: Array.isArray(staleWhen) ? staleWhen : [],
    });
  });
  const dup = (key) => { const seen = new Set(); for (const s of sets) { const v = key(s); if (seen.has(v)) return v; seen.add(v); } return null; };
  if (dup((s) => s.id)) errors.push(`sets: duplicate id "${dup((s) => s.id)}"`);
  if (dup((s) => (process.platform === 'win32' ? s.dir.toLowerCase() : s.dir))) errors.push('sets: two sets share one dir');
  if (dup((s) => s.diagramPrefix)) errors.push(`sets: duplicate diagramPrefix "${dup((s) => s.diagramPrefix)}"`);

  // ---- reference ----
  const R = isObj(raw.reference) ? raw.reference : {};
  if (raw.reference !== undefined && !isObj(raw.reference)) errors.push('reference: must be an object');
  const refBase = R.base === undefined ? '90_Object_reference' : R.base;
  const refBaseErr = fileBaseError(refBase);
  if (refBaseErr) errors.push(`reference.base: not a safe file base name: ${refBaseErr}`);
  const refSet = R.set === undefined ? (sets[0] && sets[0].id) : R.set;
  if (sets.length && !sets.some((s) => s.id === refSet)) errors.push(`reference.set: unknown set id "${refSet}"`);
  if (R.kindDetails !== undefined && typeof R.kindDetails !== 'boolean') errors.push('reference.kindDetails: must be true or false');
  if (R.legacyNamePattern !== undefined) {
    try { new RegExp(R.legacyNamePattern); } catch (e) { errors.push(`reference.legacyNamePattern: invalid regex: ${e.message}`); }
  }

  // ---- nav ----
  const N = isObj(raw.nav) ? raw.nav : {};
  for (const k of ['rootDocPattern', 'rootDiagramPattern']) {
    if (N[k] !== undefined) { try { new RegExp(N[k]); } catch (e) { errors.push(`nav.${k}: invalid regex: ${e.message}`); } }
  }
  const readmeLanguage = N.readmeLanguage === undefined ? (primary && primary.code) : N.readmeLanguage;

  // ---- misc ----
  if (raw.date !== undefined && (typeof raw.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(raw.date))) errors.push('date: must be YYYY-MM-DD');
  if (raw.uiStrings !== undefined && !isObj(raw.uiStrings)) errors.push('uiStrings: must be an object keyed by language code');
  checkLangText(raw.project, 'project', langs, errors);

  if (errors.length) throw new ConfigError(`invalid config ${abs}:\n  - ${errors.join('\n  - ')}`);

  const cfg = {
    file: abs, dir: base, raw,
    project: raw.project,
    languages: { primary, secondary },
    langs, bilingual: !!secondary,
    suffix: Object.fromEntries([primary, secondary].filter(Boolean).map((x) => [x.code, x.suffix])),
    source: {
      repo: S.repo ? path.resolve(base, S.repo) : null, ref: S.ref || null, worktree, srcRootRel: srcRootRel.replace(/\\/g, '/').replace(/\/+$/, ''),
      srcRoot: worktree ? path.resolve(worktree, srcRootRel) : null, baseline: S.baseline || null,
      compareAlso, commit: S.commit || null,
    },
    normalizeTranslations,
    outputRoot, factsDir, factsDirLabel, pngDir, contentDir, reportDir, buildDir,
    sets,
    reference: {
      base: refBase, id: typeof R.id === 'string' && R.id ? R.id : 'object-reference',
      contentFile: path.resolve(contentDir, typeof R.contentFile === 'string' && R.contentFile ? R.contentFile : `generated/${refBase}.json`),
      set: refSet, legacyNamePattern: R.legacyNamePattern || null,
      kindDetails: R.kindDetails !== false,
    },
    nav: {
      toolLabel: typeof N.toolLabel === 'string' ? N.toolLabel : (buildDir ? `${buildDir}/make-nav.mjs` : 'make-nav.mjs'),
      rootDocPattern: N.rootDocPattern || '^00_',
      rootDiagramPattern: N.rootDiagramPattern || null, // default: ^<prefix>00-
      readmeLanguage,
    },
    docgen: { creator: isObj(raw.docgen) && typeof raw.docgen.creator === 'string' ? raw.docgen.creator : '1c-config-docs docgen' },
    uiStrings: raw.uiStrings || {},
    archify: raw.archify || null,
    clearCopy: raw.clearCopy || null,
    date: raw.date || null,
  };
  return cfg;
}

export const setById = (cfg, id) => cfg.sets.find((s) => s.id === id) || null;

/** Display label of a tool script in generated texts ("_build/inventory.mjs"). */
export const toolLabel = (cfg, name) => (cfg.buildDir ? `${cfg.buildDir.replace(/\\/g, '/')}/${name}` : name);

// ---------------------------------------------------------------- git

export function git(cwd, args, opts = {}) {
  try {
    return execFileSync('git', args, { cwd, encoding: 'utf8', maxBuffer: 1024 * 1024 * 256, stdio: ['pipe', 'pipe', 'pipe'], ...opts });
  } catch (e) {
    const msg = (e.stderr && String(e.stderr).trim()) || e.message;
    throw new ConfigError(`git ${args.join(' ')} failed in ${cwd}: ${msg}`);
  }
}

/** Short commit printed on title pages / nav: config source.commit, else HEAD of the worktree (8 chars). */
export function sourceCommit(cfg) {
  if (cfg.source.commit) return cfg.source.commit;
  if (!cfg.source.worktree) throw new ConfigError('source.commit is not set and there is no source.worktree/repo to read HEAD from');
  return git(cfg.source.worktree, ['rev-parse', '--short=8', 'HEAD']).trim();
}

// ---------------------------------------------------------------- content files

/** All content files: top level of contentDir + its generated/ folder (+ the reference file's folder). "_"-prefixed skipped. */
export function listContentFiles(cfg, { includeGenerated = true } = {}) {
  const dirs = [cfg.contentDir];
  if (includeGenerated) {
    dirs.push(path.join(cfg.contentDir, 'generated'));
    const rd = path.dirname(cfg.reference.contentFile);
    if (!dirs.some((d) => samePath(d, rd))) dirs.push(rd);
  }
  const files = [];
  for (const d of dirs) {
    if (!fs.existsSync(d) || !fs.statSync(d).isDirectory()) continue;
    for (const f of fs.readdirSync(d).sort()) {
      if (!f.endsWith('.json') || f.startsWith('_')) continue;
      const full = path.join(d, f);
      if (fs.statSync(full).isFile()) files.push(full);
    }
  }
  return files;
}

/**
 * Output directory of one content object (no --out): explicit outDir (relative to the
 * content file) > set id > the first set. Returns { dir, error? }.
 */
export function resolveOutDir(cfg, c, contentFile) {
  const baseDir = path.dirname(path.resolve(contentFile));
  if (isObj(c) && typeof c.outDir === 'string') {
    // A content file must not steer the build outside the documentation tree.
    const dir = path.resolve(baseDir, c.outDir);
    const rel = path.relative(cfg.outputRoot, dir);
    if (rel.startsWith('..') || path.isAbsolute(rel)) return { dir: null, error: `outDir ${JSON.stringify(c.outDir)} resolves to ${dir}, outside outputRoot ${cfg.outputRoot}` };
    return { dir, via: 'outDir' };
  }
  if (isObj(c) && c.set !== undefined) {
    const s = setById(cfg, c.set);
    if (!s) return { dir: null, error: `unknown set id ${JSON.stringify(c.set)} (configured: ${cfg.sets.map((x) => x.id).join(', ')})` };
    return { dir: s.dir, via: 'set', set: s };
  }
  return { dir: cfg.sets[0].dir, via: 'default', set: cfg.sets[0] };
}

export function writeJsonReport(file, obj) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(obj, null, 2) + '\n', 'utf8');
}

/** Wrap a script main: ConfigError/UsageError -> exit 2 with a clean message. */
export function runMain(name, fn) {
  const done = (code) => { process.exitCode = code; };
  const fail = (e) => {
    if (e instanceof ConfigError || e instanceof UsageError) console.error(`${name}: ${e instanceof UsageError ? 'usage error' : 'config error'}: ${e.message}`);
    else console.error(`${name}: execution error: ${e && e.stack ? e.stack : e}`);
    process.exitCode = 2;
  };
  try {
    const r = fn();
    if (r && typeof r.then === 'function') r.then(done, fail); else done(r);
  } catch (e) { fail(e); }
}
