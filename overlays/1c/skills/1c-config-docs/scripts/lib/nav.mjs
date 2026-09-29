// Navigation core shared by make-nav.mjs (index.html + README.md of every set) and
// make-clear.mjs (index.html of the export copy, optionally without internalDocs).
//
// buildNav(cfg, { genDate, excludeInternal }) gathers every set (documents from the content
// files, diagrams from the set dir / _REGISTRY.md), renders index.html and README.md in memory
// and returns them together with the validators. It writes nothing.

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import {
  today, textIn, listContentFiles, resolveOutDir, samePath, sourceCommit, fileBaseError,
} from './config.mjs';
import { requireUi } from './i18n.mjs';

// scripts/ (for the rebuild commands printed in README.md)
const scriptsDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
// ---------------------------------------------------------------------------
// Helpers

export const readJson = (f) => JSON.parse(fs.readFileSync(f, 'utf8').replace(/^﻿/, ''));
export const exists = (f) => fs.existsSync(f) && fs.statSync(f).isFile();
const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export function fileInfo(f) {
  if (!exists(f)) return null;
  const buf = fs.readFileSync(f);
  return { bytes: buf.length, sha256: crypto.createHash('sha256').update(buf).digest('hex') };
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// docgen inline markup -> HTML (`code`, **bold**, [text](url) -> text)
function inlineHtml(s) {
  let out = esc(s);
  out = out.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  return out;
}

// docgen inline markup -> markdown table cell
function mdCell(s) {
  return String(s).replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/\|/g, '\\|').replace(/\n/g, ' ');
}

// hrefs: every path segment percent-encoded (Cyrillic file names work in any browser / Markdown
// viewer); the visible text stays the decoded name. Link checks decode back before resolving.
export const hrefOf = (name) => name.split('/').map((s) => (s === '..' || s === '.' ? s : encodeURIComponent(s))).join('/');
export const safeDecode = (s) => { try { return decodeURIComponent(s); } catch { return s; } };
const fmtBytes = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
export const relHref = (from, to) => (path.relative(from, to) || '.').split(path.sep).join('/');

/**
 * Gather and render the navigation of every set. opts: { genDate?: "YYYY-MM-DD", excludeInternal?: bool }.
 * excludeInternal drops the documents listed in sets[].internalDocs (export copy).
 */
export function buildNav(cfg, { genDate: genDateOpt, excludeInternal = false } = {}) {
  const LANGS = cfg.langs;
  const P = LANGS[0];
  const S = LANGS[1] || null;
  const RM = cfg.nav.readmeLanguage;
  const uis = requireUi(cfg, [...new Set([...LANGS, RM])], ['nav']);
  requireUi(cfg, [RM], ['readme']);
  const UP = uis[P]; const US = S ? uis[S] : null; const UR = uis[RM];
  const secCls = S || 'sec';
  const genDate = genDateOpt || today();
  const SOURCE ={ ref: cfg.source.ref, commit: sourceCommit(cfg), date: cfg.date || genDate };
  const TOOL = cfg.nav.toolLabel;

  // text value of a config/content field in one language; plain strings are language-neutral
  const tx = (v, l) => {
    const r = textIn(v, l);
    return r === undefined ? textIn(v, P) : r;
  };
  const bi = (v) => (v == null ? null : Object.fromEntries(LANGS.map((l) => [l, String(tx(v, l) ?? '')])));
  // "Primary · Secondary" -> { p, s }
  const splitBi = (s) => {
    const str = String(s);
    const i = str.indexOf(' · ');
    if (!S || i < 0) return Object.fromEntries(LANGS.map((l) => [l, str]));
    return { [P]: str.slice(0, i).trim(), [S]: str.slice(i + 3).trim() };
  };
  const rootDiagRe = (set) => new RegExp(cfg.nav.rootDiagramPattern || `^${escRe(set.diagramPrefix)}00-`);
  const rootDocRe = new RegExp(cfg.nav.rootDocPattern);

  // ------------------------------------------------------------- inputs
  const content = [];
  for (const full of listContentFiles(cfg)) {
    let j;
    try { j = readJson(full); } catch (e) { content.push({ file: full, error: e.message }); continue; }
    if (!j || typeof j.base !== 'string') continue;
    const r = resolveOutDir(cfg, j, full);
    content.push({ file: full, json: j, outDir: r.dir });
  }

  function readRegistry(dir, prefix) {
    const f = path.join(dir, '_REGISTRY.md');
    if (!exists(f)) return null;
    const names = [];
    const re = new RegExp('^\\|\\s*`(' + escRe(prefix) + '[^`]+)`\\s*\\|', 'gm');
    const text = fs.readFileSync(f, 'utf8');
    let m;
    while ((m = re.exec(text))) names.push(m[1]);
    return names;
  }

  function collectLinks(obj, out = []) {
    if (Array.isArray(obj)) obj.forEach((x) => collectLinks(x, out));
    else if (obj && typeof obj === 'object') {
      for (const [k, v] of Object.entries(obj)) {
        if (k === 'link' && v && typeof v === 'object' && typeof v.href === 'string') out.push(v.href);
        else collectLinks(v, out);
      }
    }
    return out;
  }

  function firstParagraph(blocks) {
    for (const b of blocks || []) if (b && b.type === 'p' && b.text) return bi(b.text);
    return null;
  }

  function gatherSet(set) {
    const issues = [];
    const warnings = [];
    if (!fs.existsSync(set.dir) || !fs.statSync(set.dir).isDirectory()) {
      issues.push(`set directory not found: ${set.dir}`);
      return { set, docs: [], diagrams: [], links: { total: 0, broken: [] }, issues, warnings, excluded: [] };
    }
    for (const c of content) if (c.error) warnings.push(`${c.file}: unreadable content JSON (${c.error})`);
    const mine = content.filter((c) => c.json && c.outDir && samePath(c.outDir, set.dir))
      .sort((a, b) => (a.json.base < b.json.base ? -1 : a.json.base > b.json.base ? 1 : 0));
    const seen = new Map();
    const docs = [];
    const excluded = []; // excludeInternal: internalDocs left out of this rendering
    for (const c of mine) {
      const base = c.json.base;
      const baseErr = fileBaseError(base);
      if (baseErr) { issues.push(`${path.relative(cfg.contentDir, c.file)}: base "${base}" is not a safe file base name: ${baseErr}`); continue; }
      if (seen.has(base)) { issues.push(`two content files produce ${base}: ${seen.get(base)} and ${c.file}`); continue; }
      seen.set(base, c.file);
      if (excludeInternal && set.internalDocs.includes(base)) { excluded.push({ base, contentFile: c.file }); continue; }
      if (c.json.source && c.json.source.commit && c.json.source.commit !== SOURCE.commit) {
        warnings.push(`${path.relative(cfg.contentDir, c.file)}: source.commit ${c.json.source.commit} != ${SOURCE.commit}`);
      }
      const langs = {};
      for (const l of LANGS) {
        const name = `${base}_${cfg.suffix[l]}.docx`;
        langs[l] = { name, info: fileInfo(path.join(set.dir, name)) };
        if (!langs[l].info) issues.push(`MISSING docx ${name}`);
      }
      docs.push({
        base, num: base.slice(0, 2), title: bi(c.json.title), covers: (c.json.subtitle !== undefined ? bi(c.json.subtitle) : null) || firstParagraph(c.json.blocks),
        langs, contentFile: c.file, internal: set.internalDocs.includes(base), root: rootDocRe.test(base),
      });
    }
    for (const b of set.internalDocs) if (!seen.has(b)) warnings.push(`internalDocs lists ${b}, but no content file of this set has that base`);

    // Diagrams: discovered files vs the registry (or every <prefix>*.json when there is no registry).
    const re = new RegExp('^' + escRe(set.diagramPrefix) + '.+\\.(json|html)$');
    const found = new Set();
    const foundJson = new Set();
    for (const f of fs.readdirSync(set.dir)) {
      if (f.startsWith('_') || f.includes('.visual-check.') || !re.test(f)) continue;
      if (!exists(path.join(set.dir, f))) continue;
      const stem = f.replace(/\.(json|html)$/, '');
      found.add(stem);
      if (f.endsWith('.json')) foundJson.add(stem);
    }
    const registry = readRegistry(set.dir, set.diagramPrefix);
    const expected = registry || [...foundJson];
    if (registry) for (const n of found) if (!expected.includes(n)) warnings.push(`diagram ${n} is not listed in _REGISTRY.md`);
    const names = [...new Set([...expected, ...found])].sort();

    const diagrams = names.map((stem) => {
      const type = stem.split('.')[1] || '?';
      const jsonName = `${stem}.json`;
      const htmlName = `${stem}.html`;
      const json = fileInfo(path.join(set.dir, jsonName));
      const html = fileInfo(path.join(set.dir, htmlName));
      if (!json) issues.push(`MISSING diagram spec ${jsonName}`);
      if (!html) issues.push(`MISSING diagram artifact ${htmlName}`);
      let title = Object.fromEntries(LANGS.map((l) => [l, stem]));
      let views = [];
      let links = [];
      if (json) {
        let j = null;
        try { j = readJson(path.join(set.dir, jsonName)); } catch (e) { issues.push(`${jsonName}: not valid JSON (${e.message})`); }
        if (j) {
          const meta = j.meta || {};
          if (meta.title) title = splitBi(meta.title);
          else warnings.push(`${jsonName}: meta.title missing`);
          views = (meta.views || []).map((v) => splitBi(v.label || v.id || ''));
          if (j.diagram_type && j.diagram_type !== type) warnings.push(`${jsonName}: diagram_type "${j.diagram_type}" != file name type "${type}"`);
          links = collectLinks(j);
        }
      }
      return { stem, type, jsonName, htmlName, json, html, title, views, links, root: rootDiagRe(set).test(stem) };
    });

    const links = { total: 0, broken: [] };
    for (const d of diagrams) {
      for (const href of d.links) {
        if (/^[a-z]+:/i.test(href) || href.startsWith('#')) continue;
        links.total++;
        const raw = href.split('#')[0];
        if (!exists(path.resolve(set.dir, safeDecode(raw))) && !exists(path.resolve(set.dir, raw))) links.broken.push(`${d.stem} -> ${href}`);
      }
    }
    for (const b of links.broken) issues.push(`broken diagram link ${b}`);
    return { set, docs, diagrams, links, issues, warnings, excluded };
  }

  // ------------------------------------------------------------- index.html
  const CSS = `
  :root {
    --bg: #f6f8fa; --panel: #ffffff; --border: #d8e0e8; --text: #17212b; --muted: #5c6b7a;
    --accent: #0f7a6c; --accent-soft: #e6f3f0; --root: #b45309; --root-soft: #fdf3e7;
    --missing: #a3342c; --missing-soft: #fbeceb;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "DejaVu Sans Mono", monospace;
    color-scheme: light dark;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0e1620; --panel: #16202c; --border: #26333f; --text: #e6edf3; --muted: #93a4b3;
      --accent: #3fbfa8; --accent-soft: #16302c; --root: #e0a45c; --root-soft: #2a2115;
      --missing: #f0877e; --missing-soft: #2e1a19;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 2.4rem 1.6rem 4rem; background: var(--bg); color: var(--text);
    font: 16px/1.55 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  }
  .wrap { max-width: 1080px; margin: 0 auto; }
  .${secCls} { display: block; color: var(--muted); font-size: .84em; font-weight: 400; line-height: 1.4; }
  h1 { margin: 0 0 .5rem; font-size: 2rem; letter-spacing: -.01em; line-height: 1.2; }
  h1 .${secCls} { font-size: .6em; margin-top: .15rem; }
  .lead { margin: 0 0 .5rem; font-size: 1.05rem; }
  .meta { margin: 0 0 1.6rem; color: var(--muted); font-size: .85rem; }
  code { font-family: var(--mono); font-size: .9em; }
  .warn {
    margin: 0 0 1.6rem; padding: .7rem .9rem; border-left: 3px solid var(--root); border-radius: .3rem;
    background: var(--root-soft); font-size: .9rem;
  }
  h2 { margin: 2.2rem 0 .9rem; padding-bottom: .4rem; border-bottom: 1px solid var(--border); font-size: 1.15rem; font-weight: 700; }
  h2 .${secCls} { display: inline; margin-left: .4rem; }
  .grid { display: grid; gap: .7rem; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); }
  .card {
    display: block; padding: .85rem .95rem; border: 1px solid var(--border); border-radius: .55rem;
    background: var(--panel); color: inherit; text-decoration: none; transition: border-color .12s, transform .12s;
  }
  a.card:hover, a.card:focus-visible { border-color: var(--accent); transform: translateY(-1px); }
  .card.root { border-color: var(--root); background: var(--root-soft); }
  .card.internal { border-style: dashed; border-color: var(--root); }
  .card.gone { border-style: dashed; border-color: var(--missing); }
  .card .name { font-weight: 700; font-size: .98rem; }
  .kind {
    display: inline-block; margin-left: .45rem; padding: .05rem .38rem; border-radius: .3rem;
    background: var(--accent-soft); color: var(--accent); font-family: var(--mono);
    font-size: .68rem; font-weight: 700; vertical-align: 1px;
  }
  .kind.start, .kind.int { background: transparent; color: var(--root); border: 1px solid var(--root); }
  .kind.miss { background: var(--missing-soft); color: var(--missing); }
  .card .about { margin-top: .35rem; color: var(--muted); font-size: .86rem; }
  .card .about .${secCls} { font-size: .95em; }
  .card .views { margin-top: .35rem; font-size: .78rem; color: var(--muted); }
  .card .file { margin-top: .4rem; font-family: var(--mono); font-size: .74rem; color: var(--muted); word-break: break-all; }
  .langs { margin-top: .55rem; display: flex; gap: .45rem; flex-wrap: wrap; }
  .lang {
    display: inline-block; padding: .15rem .6rem; border: 1px solid var(--accent); border-radius: .3rem;
    color: var(--accent); font-family: var(--mono); font-size: .8rem; font-weight: 700; text-decoration: none;
  }
  a.lang:hover, a.lang:focus-visible { background: var(--accent); color: var(--panel); }
  .lang.missing { border-color: var(--missing); color: var(--missing); border-style: dashed; font-weight: 400; }
  ul.plain { margin: 0; padding-left: 1.1rem; font-size: .92rem; }
  ul.plain li { margin-bottom: .55rem; }
  footer { margin-top: 2.6rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: .85rem; }
`;

  // primary text + optional secondary <span>
  const pair = (p, s) => (S ? `${p}<span class="${secCls}">${s}</span>` : p);
  const both = (key, args = {}, argsS = args) => pair(UP.t(key, args), S ? US.t(key, argsS) : '');
  const MISSING_TIP = S ? `${UP.t('navMissingTip')} · ${US.t('navMissingTip')}` : UP.t('navMissingTip');
  const biLine = (tag, cls, v, inline = false) => {
    const f = inline ? inlineHtml : esc;
    return `<${tag}${cls ? ` class="${cls}"` : ''}>${pair(f(v[P]), S ? f(v[S]) : '')}</${tag}>`;
  };

  function docCard(d) {
    const cls = ['card', d.root ? 'root' : '', d.internal ? 'internal' : ''].filter(Boolean).join(' ');
    const badges = [`<span class="kind">${esc(d.num)}</span>`];
    const secTail = [];
    if (d.root) { badges.push(`<span class="kind start">${esc(UP.t('navStartHere'))}</span>`); if (S) secTail.push(US.t('navStartHere')); }
    if (d.internal) { badges.push(`<span class="kind int">${esc(UP.t('navInternal'))}</span>`); if (S) secTail.push(US.t('navInternal')); }
    const tail = secTail.length ? ` · ${esc(secTail.join(' · '))}` : '';
    const missingWord = S ? `${UP.t('navMissing')} · ${US.t('navMissing')}` : UP.t('navMissing');
    const lang = (l) => {
      const f = d.langs[l];
      const codeU = l.toUpperCase();
      return f.info
        ? `<a class="lang" href="${hrefOf(f.name)}" title="${esc(f.name)}">${codeU}</a>`
        : `<span class="lang missing" title="${esc(MISSING_TIP)}">${codeU} — ${esc(missingWord)}</span>`;
    };
    const suffixes = LANGS.map((l) => cfg.suffix[l]);
    return [
      `    <div class="${cls}">`,
      `      <div class="name">${esc(d.title[P])}${badges.join('')}${S ? `<span class="${secCls}">${esc(d.title[S])}${tail}</span>` : ''}</div>`,
      d.covers ? `      ${biLine('div', 'about', d.covers, true)}` : '',
      `      <div class="langs">${LANGS.map(lang).join('')}</div>`,
      `      <div class="file">${esc(d.base)}_${suffixes.length > 1 ? `{${suffixes.join(',')}}` : suffixes[0]}.docx</div>`,
      '    </div>',
    ].filter(Boolean).join('\n');
  }

  function diagramCard(d) {
    const cls = ['card', d.root ? 'root' : '', d.html ? '' : 'gone'].filter(Boolean).join(' ');
    const tag = d.html ? 'a' : 'div';
    const href = d.html ? ` href="${hrefOf(d.htmlName)}"` : ` title="${esc(MISSING_TIP)}"`;
    const badges = [`<span class="kind">${esc(d.type)}</span>`];
    const secTail = [];
    if (d.root) { badges.push(`<span class="kind start">${esc(UP.t('navStartHere'))}</span>`); if (S) secTail.push(US.t('navStartHere')); }
    if (!d.html) { badges.push(`<span class="kind miss">${esc(UP.t('navNoFile'))}</span>`); if (S) secTail.push(US.t('navNoFile')); }
    const tail = secTail.length ? ` · ${esc(secTail.join(' · '))}` : '';
    const views = d.views.length
      ? `      <div class="views">${esc(d.views.map((v) => v[P]).join(' / '))}${S ? `<span class="${secCls}">${esc(d.views.map((v) => v[S]).join(' / '))}</span>` : ''}</div>`
      : '';
    return [
      `    <${tag} class="${cls}"${href}>`,
      `      <div class="name">${esc(d.title[P])}${badges.join('')}${S ? `<span class="${secCls}">${esc(d.title[S])}${tail}</span>` : ''}</div>`,
      views,
      `      <div class="file">${esc(d.htmlName)}</div>`,
      `    </${tag}>`,
    ].filter(Boolean).join('\n');
  }

  function otherCards(g, pending) {
    return cfg.sets.filter((o) => o !== g.set).map((o) => {
      const href = hrefOf(`${relHref(g.set.dir, o.dir)}/index.html`.replace(/^\.\//, ''));
      const target = path.join(o.dir, 'index.html');
      const ok = exists(target) || pending.has(target);
      const title = bi(o.navTitle || o.title);
      const about = o.about ? bi(o.about) : null;
      return [
        ok ? `    <a class="card" href="${href}">` : `    <div class="card gone" title="${esc(MISSING_TIP)}">`,
        `      <div class="name">${pair(esc(title[P]), S ? esc(title[S]) : '')}</div>`,
        about ? `      ${biLine('div', 'about', about)}` : '',
        `      <div class="file">${esc(safeDecode(href))}</div>`,
        ok ? '    </a>' : '    </div>',
      ].filter(Boolean).join('\n');
    });
  }

  function renderIndex(g, pending) {
    const { set, docs, diagrams } = g;
    const rootFirst = (a, b) => (b.root - a.root);
    const title = bi(set.title);
    const lead = set.lead ? bi(set.lead) : null;
    const srcArgs = (U) => ({ ref: SOURCE.ref, commit: SOURCE.commit, date: U.date(SOURCE.date) });
    const srcKey = SOURCE.ref ? 'navSource' : 'navSourceNoRef';
    const internalNote = docs.filter((d) => d.internal).map((d) => {
      const a = (l) => ({ num: esc(d.num), title: esc(d.title[l]) });
      const sKey = S && US.has('navInternalNote_sec') ? 'navInternalNote_sec' : 'navInternalNote';
      return `  <p class="warn">${pair(UP.t('navInternalNote', a(P)), S ? US.t(sKey, a(S)) : '')}</p>`;
    }).join('\n');
    const howto = ['navHowto1', 'navHowto2', 'navHowto3', S ? 'navHowto4' : 'navHowto4Mono', 'navHowto5', 'navHowto6'];
    const others = otherCards(g, pending);
    const footArgs = (U) => ({ date: U.date(genDate), tool: TOOL });

    return `<!doctype html>
<html lang="${P}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title[P])}${S ? ` · ${esc(title[S])}` : ''}</title>
<style>${CSS}</style>
</head>
<body>
<div class="wrap">

  ${biLine('h1', '', title)}
${lead ? `  ${biLine('p', 'lead', lead)}\n` : ''}  <p class="meta">${pair(UP.t(srcKey, srcArgs(UP)), S ? US.t(srcKey, srcArgs(US)) : '')}</p>
${internalNote}
  <h2>${both('navDocuments')}</h2>
  <div class="grid">
${[...docs].sort(rootFirst).map(docCard).join('\n\n')}
  </div>

  <h2>${both('navDiagrams')}</h2>
  <div class="grid">
${[...diagrams].sort(rootFirst).map(diagramCard).join('\n\n')}
  </div>
${others.length ? `
  <h2>${both(others.length > 1 ? 'navOtherSets' : 'navOtherSet')}</h2>
  <div class="grid">
${others.join('\n\n')}
  </div>
` : ''}
  <h2>${both('navHowTo')}</h2>
  <ul class="plain">
${howto.map((k) => `    <li>${both(k)}</li>`).join('\n')}
  </ul>

  <footer>${pair(UP.t('navFooter', footArgs(UP)), S ? US.t('navFooter', footArgs(US)) : '')}</footer>

</div>
</body>
</html>
`;
  }

  // ------------------------------------------------------------- README.md
  function mdLink(name, info, label = name) {
    return info ? `[${label}](${hrefOf(name)})` : `${label} — ${UR.t('rmNoFile')}`;
  }
  const cmdPath = (f) => path.join(scriptsDir, f).split(path.sep).join('/');
  const cfgPath = cfg.file.split(path.sep).join('/');

  function renderReadme(g) {
    const { set, docs, diagrams, links } = g;
    const t = (k, a) => UR.t(k, a);
    const other = RM === P ? S : P;
    const title = (v) => tx(v, RM);
    const L = [];
    L.push(`# ${t('rmTitle', { title: title(set.title) })}`, '');
    if (set.readmeIntro !== undefined && tx(set.readmeIntro, RM)) L.push(tx(set.readmeIntro, RM), '');
    const others = cfg.sets.filter((o) => o !== set);
    if (others.length) {
      L.push(t('rmOtherSets', { list: others.map((o) => `[${title(o.navTitle || o.title)}](${hrefOf(relHref(set.dir, path.join(o.dir, 'README.md')))})`).join(', ') }), '');
    }
    L.push(t(SOURCE.ref ? 'rmSource' : 'rmSourceNoRef', { ref: SOURCE.ref, commit: SOURCE.commit, date: UR.date(SOURCE.date) }), '');
    const l1 = UR.lang(P); const l2 = S ? UR.lang(S) : null;
    L.push(S ? t('rmLangsBi', { s1: cfg.suffix[P], s2: cfg.suffix[S], l1, l2 }) : t('rmLangsMono', { s1: cfg.suffix[P], l1 }), '');
    L.push(t('rmEntry', { tool: TOOL }), '');

    L.push(`## ${t('rmDocsH')}`, '');
    L.push(`| ${t('rmColFiles')} | ${t('rmColTitle')} | ${t('rmColAbout')} |`, '|---|---|---|');
    for (const d of docs) {
      const files = LANGS.map((l) => mdLink(d.langs[l].name, d.langs[l].info)).join('<br>');
      let ttl = mdCell(d.title[RM] ?? d.title[P]);
      if (other && d.title[other] !== undefined) ttl += `<br>*${mdCell(d.title[other])}*`;
      if (d.internal) ttl += `<br>${t('rmInternal')}`;
      const covers = d.covers ? mdCell(d.covers[RM] ?? d.covers[P]) : '—';
      L.push(`| ${files} | ${ttl} | ${covers} |`);
    }
    L.push('');
    L.push(t('rmDocsNote', {
      content: relHref(cfg.outputRoot, cfg.contentDir), refBase: cfg.reference.base,
      inv: `${cfg.factsDirLabel}/inventory.json`, refContent: relHref(cfg.outputRoot, cfg.reference.contentFile),
    }), '');

    L.push(`## ${t('rmDiagramsH')}`, '');
    L.push(`| ${t('rmColFile')} | ${t('rmColType')} | ${t('rmColTitle')} | ${t('rmColViews')} |`, '|---|---|---|---|');
    for (const d of diagrams) {
      const file = d.html ? `[${d.htmlName}](${hrefOf(d.htmlName)})` : `${d.htmlName} — ${t('rmNoFile')}`;
      const views = d.views.length ? d.views.map((v) => mdCell(v[RM] ?? v[P])).join('; ') : '—';
      const root = d.root ? `<br>${t('rmRootDiagram')}` : '';
      const ttl = mdCell(d.title[RM] ?? d.title[P]) + (other && d.title[other] !== undefined ? `<br>*${mdCell(d.title[other])}*` : '');
      L.push(`| ${file}${root} | ${d.type} | ${ttl} | ${views} |`);
    }
    L.push('');
    L.push(t('rmLinks', { total: links.total, broken: links.broken.length }));
    for (const b of links.broken) L.push(`- ${t('rmBrokenLink')}: \`${b}\``);
    L.push('');

    L.push(`## ${t('rmChecksumsH')}`, '', t('rmChecksums', { tool: TOOL }), '');
    L.push(`| ${t('rmColFile')} | ${t('rmColBytes')} | SHA-256 |`, '|---|--:|---|');
    const sumRow = (name, info) => L.push(info ? `| \`${name}\` | ${fmtBytes(info.bytes)} | \`${info.sha256}\` |` : `| \`${name}\` | — | ${t('rmNoFile')} |`);
    for (const d of diagrams) { sumRow(d.jsonName, d.json); sumRow(d.htmlName, d.html); }
    for (const d of docs) for (const l of LANGS) sumRow(d.langs[l].name, d.langs[l].info);
    L.push('');

    const ex = diagrams.find((d) => d.root) || diagrams[0];
    const exJson = ex ? path.join(set.dir, ex.jsonName).split(path.sep).join('/') : '<file>.json';
    const exHtml = ex ? path.join(set.dir, ex.htmlName).split(path.sep).join('/') : '<file>.html';
    const archify = cfg.archify ? `node ${cfg.archify.replace(/\\/g, '/')}` : 'archify';
    L.push(`## ${t('rmRebuildH')}`, '', t('rmRebuild', { config: cfgPath }), '');
    L.push(`1. ${t('rmStep1', { facts: cfg.factsDirLabel, src: cfg.source.srcRoot ? cfg.source.srcRoot.split(path.sep).join('/') : '?' })}`, '');
    L.push('```bash', `node ${cmdPath('inventory.mjs')} --config ${cfgPath}`, '```', '');
    L.push(`2. ${t('rmStep2')}`, '');
    L.push('```bash', `${archify} deliver ${ex ? ex.type : '<type>'} ${exJson} ${exHtml} --quality showcase --json`, `${archify} visual-check ${exHtml} --json`, '```', '');
    L.push(`3. ${t('rmStep3', { png: relHref(cfg.outputRoot, cfg.pngDir) + '/' })}`, '');
    L.push('```bash', `node ${cmdPath('export-png.mjs')} --config ${cfgPath}`, '```', '');
    L.push(`4. ${t('rmStep4')}`, '');
    L.push('```bash', `node ${cmdPath('docgen/build.mjs')} --config ${cfgPath} --all`, `node ${cmdPath('docgen/reference.mjs')} --config ${cfgPath}`, '```', '');
    L.push(`5. ${t('rmStep5')}`, '');
    L.push('```bash', `node ${cmdPath('make-nav.mjs')} --config ${cfgPath}`, '```', '');

    L.push(`## ${t('rmStaleH')}`, '', t('rmStale', { commit: SOURCE.commit }), '');
    if (SOURCE.ref) L.push(`- ${t('rmStaleCommit', { commit: SOURCE.commit, ref: SOURCE.ref, src: cfg.source.srcRootRel })}`);
    L.push(`- ${t('rmStaleMeta')}`);
    for (const w of set.staleWhen) { const s = tx(w, RM); if (s) L.push(`- ${s}`); }
    L.push(`- ${t('rmStaleRegistry', { tool: TOOL })}`, '');

    L.push(`## ${t('rmDeliverH')}`, '');
    L.push(`| ${t('rmColWho')} | ${t('rmColWhat')} | ${t('rmColWhy')} |`, '|---|---|---|');
    const copy = cfg.clearCopy ? ` (\`${cfg.clearCopy}/\`)` : '';
    const internal = set.internalDocs.length ? t('rmDeliverInternal', { list: set.internalDocs.map((b) => `\`${b}\``).join(', ') }) : '';
    L.push(`| ${t('rmDeliverOut')} | ${t('rmDeliverOutWhat', { copy })} | ${t('rmDeliverOutWhy', { internal })} |`);
    L.push(`| ${t('rmDeliverRepo')} | ${t('rmDeliverRepoWhat')} | ${t('rmDeliverRepoWhy')} |`);
    L.push(`| ${t('rmDeliverArchive')} | ${t('rmDeliverArchiveWhat')} | ${t('rmDeliverArchiveWhy')} |`, '');

    L.push(`## ${t('rmLimitsH')}`, '');
    const png = relHref(set.dir, cfg.pngDir) + '/';
    L.push(`- ${t('rmLimit1')}`, `- ${t('rmLimit2', { png })}`, `- ${t('rmLimit3')}`, `- ${t('rmLimit4')}`, '');
    L.push('---', '', t('rmGenerated', { date: UR.date(genDate), tool: TOOL }), '');
    return L.join('\n');
  }

  // ------------------------------------------------------------- validation
  const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);

  function checkHtml(html) {
    const errors = [];
    const stack = [];
    const hrefs = [];
    const tagRe = /<!--[\s\S]*?-->|<!doctype[^>]*>|<\/?([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^\s=>\/]+(?:\s*=\s*(?:"[^"]*"|'[^']*'))?)*)\s*(\/?)>/gi;
    let last = 0;
    let m;
    const text = [];
    while ((m = tagRe.exec(html))) {
      text.push(html.slice(last, m.index));
      last = tagRe.lastIndex;
      if (!m[1]) continue;
      const name = m[1].toLowerCase();
      if (m[0].startsWith('</')) {
        const topEl = stack.pop();
        if (topEl !== name) { errors.push(`unexpected </${name}> (open: <${topEl || 'none'}>)`); if (topEl) stack.push(topEl); }
        continue;
      }
      const attrs = m[2] || '';
      if (attrs.replace(/"[^"]*"|'[^']*'/g, '""').match(/=\s*[^\s"'>]/)) errors.push(`<${name}>: unquoted attribute value`);
      const hm = /\shref\s*=\s*"([^"]*)"/i.exec(attrs);
      if (hm) hrefs.push(hm[1]);
      if (name === 'style' || name === 'script') {
        const endIdx = html.toLowerCase().indexOf(`</${name}>`, last);
        if (endIdx < 0) { errors.push(`<${name}> not closed`); break; }
        last = endIdx + name.length + 3;
        tagRe.lastIndex = last;
        continue;
      }
      if (!VOID.has(name) && !m[3]) stack.push(name);
    }
    text.push(html.slice(last));
    const body = text.join('');
    if (body.includes('<')) errors.push('stray "<" or malformed tag in text');
    const badAmp = body.match(/&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)/g);
    if (badAmp) errors.push(`${badAmp.length} unescaped "&"`);
    if (stack.length) errors.push(`unclosed elements: ${stack.join(' > ')}`);
    if (!/^<!doctype html>/i.test(html)) errors.push('missing <!doctype html>');
    if (/(?:src|href)\s*=\s*"(?:https?:)?\/\//i.test(html) || /@import|url\(/i.test(html)) errors.push('external resource reference');
    return { errors, hrefs };
  }

  function checkTargets(dir, hrefs, pending) {
    const broken = [];
    for (const h of hrefs) {
      if (/^[a-z]+:/i.test(h) || h.startsWith('#')) continue;
      const target = path.resolve(dir, safeDecode(h.split('#')[0]));
      if (!exists(target) && !pending.has(target)) broken.push(h);
    }
    return broken;
  }

  const mdHrefs = (md) => [...md.matchAll(/\]\(([^)\s]+)\)/g)].map((m) => m[1]);

  // ------------------------------------------------------------- run
  const gathered = cfg.sets.map(gatherSet);
  const pending = new Set();
  for (const s of cfg.sets) { pending.add(path.join(s.dir, 'index.html')); pending.add(path.join(s.dir, 'README.md')); }
  const outputs = gathered.map((g) => ({ g, html: renderIndex(g, pending), md: renderReadme(g) }));

  return { LANGS, P, S, SOURCE, TOOL, genDate, gathered, pending, outputs, checkHtml, checkTargets, mdHrefs };
}
