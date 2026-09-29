// docgen core: validation + rendering of one content JSON into one .docx per
// configured language (<base>_<suffix>.docx). Mono- or bilingual, driven by the
// docset config. Content format: see ../CONTENT_FORMAT.md
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, TableLayoutType,
  PageOrientation, TableOfContents, PageBreak, Header, Footer, PageNumber,
  ImageRun, ExternalHyperlink, InternalHyperlink, Bookmark, LevelFormat,
} from 'docx';
import { resolveOutDir, sourceCommit, today, writeJsonReport, fileBaseError, ConfigError } from '../../lib/config.mjs';
import { requireUi } from '../../lib/i18n.mjs';

// ---- visual conventions ----
const BODY = 'Calibri';
const MONO = 'Consolas';
const BODY_SIZE = 20;          // half-points -> 10pt
const CELL_SIZE = 17;          // 8.5pt in tables
const HEAD_FILL = 'E8EEF4';
const ZEBRA = 'F6F8FA';
const NOTE_FILL = { warn: 'FDF3E7', info: 'EEF4FA' };
const NOTE_BAR = { warn: 'E0A040', info: '5B8DB8' };
const ACCENT = '1F3A5F';
const GREY = '666666';
const PAGE_W = 11906, PAGE_H = 16838, MARGIN = 1134; // A4, 2 cm
const CONTENT_W = { portrait: PAGE_W - 2 * MARGIN, landscape: PAGE_H - 2 * MARGIN };
const CONTENT_H = { portrait: PAGE_H - 2 * MARGIN, landscape: PAGE_W - 2 * MARGIN };

const TOP_KEYS = ['id', 'base', 'outDir', 'set', 'orientation', 'title', 'subtitle', 'source', 'blocks'];
const BLOCK_KEYS = {
  h1: ['text', 'anchor'], h2: ['text', 'anchor'], h3: ['text', 'anchor'],
  p: ['text', 'italic'],
  bullets: ['items'], numbered: ['items'],
  table: ['headers', 'rows', 'widths', 'mono'],
  note: ['kind', 'title', 'lines'],
  diagram: ['href', 'png', 'caption'],
  pagebreak: [], toc: ['levels'],
  glossary: ['rows'],
};
export const BLOCK_TYPES = Object.keys(BLOCK_KEYS);
const COMMON_BLOCK_KEYS = ['type', 'landscape'];
const isComment = (k) => k.startsWith('_') || k.startsWith('$');
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const ANCHOR_RE = /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/;
const PNG_SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

// ===========================================================================
// Inline markup: `code`, **bold**, [text](href | #anchor), \-escapes, \n
// ===========================================================================

const INLINE_RE = /\\([`*[\]\\])|`([^`\n]+)`|\*\*([^*\n]+?)\*\*|\[([^\]\n]+)\]\(([^)\s]+)\)/g;

export function parseInline(str) {
  const out = [];
  let last = 0; let buf = '';
  for (const m of str.matchAll(INLINE_RE)) {
    buf += str.slice(last, m.index);
    last = m.index + m[0].length;
    if (m[1] !== undefined) { buf += m[1]; continue; }
    if (buf) { out.push({ t: 'text', text: buf }); buf = ''; }
    if (m[2] !== undefined) out.push({ t: 'code', text: m[2] });
    else if (m[3] !== undefined) out.push({ t: 'bold', text: m[3] });
    else out.push({ t: 'link', text: m[4], href: m[5] });
  }
  buf += str.slice(last);
  if (buf) out.push({ t: 'text', text: buf });
  return out;
}

/** Word bookmark names: <= 40 chars, letter first, [A-Za-z0-9_] only. Deterministic. */
export function bookmarkId(anchor) {
  const s = anchor.replace(/[^A-Za-z0-9_]/g, '_');
  const h = crypto.createHash('sha1').update(anchor).digest('hex').slice(0, 8);
  return `a_${s}`.slice(0, 30) + '_' + h;
}

/**
 * Relationship target of an external hyperlink (docx `Target`, xsd:anyURI = IRI). Checked in
 * Word (COM Hyperlink.Address): a raw Unicode target ("90_Справочник_ru.docx") resolves to the
 * file, while a UTF-8 percent-encoded one ("90_%D0%A1…") is taken literally and breaks; "%20"
 * is decoded. So: non-ASCII stays as is, only ASCII characters that are not allowed in a URI
 * (space, control characters, "<>\"^`{|}") are percent-encoded. Everything else — existing
 * %XX escapes, "#", "?", "/" — is kept, so ordinary ASCII links are written unchanged.
 */
export function hrefTarget(href) {
  return String(href).replace(/[\x00-\x20\x7f"<>^`{|}]/g, (ch) => encodeURIComponent(ch));
}
const safeDecode = (s) => { try { return decodeURIComponent(s); } catch { return s; } };

function textRuns(text, st) {
  return String(text).split('\n').map((line, i) => new TextRun({
    text: line, break: i ? 1 : undefined, font: st.font, size: st.size,
    bold: st.bold || undefined, italics: st.italics || undefined, color: st.color, style: st.style,
  }));
}

function inlineRuns(str, st = {}, allowLinks = true) {
  const res = [];
  const size = st.size || BODY_SIZE;
  for (const tk of parseInline(String(str))) {
    if (tk.t === 'text') res.push(...textRuns(tk.text, st));
    else if (tk.t === 'code') res.push(...textRuns(tk.text, { ...st, font: MONO, size: size - 1 }));
    else if (tk.t === 'bold') res.push(...textRuns(tk.text, { ...st, bold: true }));
    else if (!allowLinks) res.push(...textRuns(tk.text, st));
    else {
      const kids = inlineRuns(tk.text, { ...st, style: 'Hyperlink', color: '0563C1' }, false);
      res.push(tk.href.startsWith('#')
        ? new InternalHyperlink({ anchor: bookmarkId(tk.href.slice(1)), children: kids })
        : new ExternalHyperlink({ link: hrefTarget(tk.href), children: kids }));
    }
  }
  return res;
}

// ===========================================================================
// Rendering helpers
// ===========================================================================

const tr = (v, lang) => (v === undefined || v === null ? '' : typeof v === 'object' ? v[lang] : String(v));

function para(children, opts = {}) {
  return new Paragraph({
    alignment: opts.align, heading: opts.heading, keepNext: opts.keepNext,
    spacing: { before: opts.before || 0, after: opts.after === undefined ? 100 : opts.after },
    bullet: opts.bullet, numbering: opts.numbering, children,
  });
}

function colWidths(spec, n, cw) {
  if (!spec) return Array(n).fill(Math.floor(cw / n));
  const tw = spec.map((w) => (typeof w === 'string' ? Math.round((parseFloat(w) / 100) * cw) : w));
  const sum = tw.reduce((a, b) => a + b, 0);
  return sum > cw ? tw.map((w) => Math.floor((w * cw) / sum)) : tw;
}

const TABLE_BORDERS = {
  top: { style: BorderStyle.SINGLE, size: 4, color: 'B8C4D0' }, bottom: { style: BorderStyle.SINGLE, size: 4, color: 'B8C4D0' },
  left: { style: BorderStyle.SINGLE, size: 4, color: 'B8C4D0' }, right: { style: BorderStyle.SINGLE, size: 4, color: 'B8C4D0' },
  insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: 'D5DDE5' }, insideVertical: { style: BorderStyle.SINGLE, size: 2, color: 'D5DDE5' },
};

function cell(str, width, o = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: o.fill ? { type: ShadingType.CLEAR, fill: o.fill, color: 'auto' } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ spacing: { after: 0 }, children: inlineRuns(str, { size: o.mono ? CELL_SIZE - 1 : CELL_SIZE, font: o.mono ? MONO : BODY, bold: o.bold }) })],
  });
}

function renderTable(headers, rows, { widths, mono = [], bold = [] }, ctx) {
  const n = headers.length;
  const ws = colWidths(widths, n, ctx.cw);
  const trs = [new TableRow({ tableHeader: true, cantSplit: true, children: headers.map((h, i) => cell(tr(h, ctx.lang), ws[i], { bold: true, fill: HEAD_FILL })) })];
  rows.forEach((r, ri) => {
    trs.push(new TableRow({
      cantSplit: true,
      children: r.map((v, i) => cell(tr(v, ctx.lang), ws[i], { fill: ri % 2 ? ZEBRA : undefined, mono: mono.includes(i), bold: bold.includes(i) })),
    }));
  });
  ctx.stats.tables++; ctx.stats.tableRows += rows.length;
  return [new Table({ columnWidths: ws, width: { size: ws.reduce((a, b) => a + b, 0), type: WidthType.DXA }, layout: TableLayoutType.FIXED, borders: TABLE_BORDERS, rows: trs }),
    para([], { after: 120 })];
}

function pngSize(buf) { return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) }; }

const HEADING = { h1: HeadingLevel.HEADING_1, h2: HeadingLevel.HEADING_2, h3: HeadingLevel.HEADING_3 };
const HEADING_SIZE = { h1: 32, h2: 26, h3: 22 };

function pageProps(orientation, extra = {}) {
  return {
    page: {
      size: { width: PAGE_W, height: PAGE_H, orientation: orientation === 'landscape' ? PageOrientation.LANDSCAPE : PageOrientation.PORTRAIT },
      margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN, header: 567, footer: 567 },
    },
    ...extra,
  };
}

function runningHeader(title) {
  return new Header({ children: [new Paragraph({
    alignment: AlignmentType.RIGHT, spacing: { after: 0 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: 'B8C4D0', space: 4 } },
    children: textRuns(title, { size: 16, color: GREY }),
  })] });
}
function pageFooter(I) {
  return new Footer({ children: [new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { after: 0 },
    children: [new TextRun({ font: BODY, size: 16, color: GREY, children: [`${I.page} `, PageNumber.CURRENT, ` ${I.of} `, PageNumber.TOTAL_PAGES] })],
  })] });
}

// ===========================================================================
// Factory bound to one docset config
// ===========================================================================

/**
 * createDocgen(cfg) -> { langs, validate, render, buildFile, writeReport, printEntry }
 * Throws ConfigError when UI strings for a configured language are missing.
 */
export function createDocgen(cfg) {
  const LANGS = cfg.langs;
  const P = LANGS[0];
  const uis = requireUi(cfg, LANGS, ['docx']);
  const I18N = {};
  for (const l of LANGS) {
    const U = uis[l];
    I18N[l] = Object.fromEntries(['langLabel', 'page', 'of', 'contents', 'figure', 'source', 'commit', 'document', 'note', 'warn', 'interactive', 'glossNote', 'tocHint'].map((k) => [k, U.raw(k)]));
    I18N[l].langName = (code) => U.lang(code).Name;
  }
  const langList = LANGS.map((l) => JSON.stringify(l)).join(',');
  let defaultSource = null;
  const getDefaultSource = () => {
    if (!defaultSource) {
      let commit = null; let err = null;
      try { commit = sourceCommit(cfg); } catch (e) { err = e.message; }
      defaultSource = { commit, date: cfg.date || today(), err };
    }
    return defaultSource;
  };

  // ------------------------------------------------------------ validation
  /**
   * Validate a parsed content object. Returns { errors: string[], warnings: string[] }.
   * Every error is "<json.path>: <message>".
   */
  function validate(c, { baseDir, outDir }) {
    const errors = new Set();
    const warnings = [];
    const texts = [];
    const anchors = new Map();
    const E = (p, m) => errors.add(`${p}: ${m}`);

    const checkBi = (v, p) => {
      for (const l of LANGS) {
        if (!(l in v) || v[l] === null || v[l] === undefined) E(`${p}.${l}`, 'missing');
        else if (typeof v[l] !== 'string') E(`${p}.${l}`, 'must be a string');
      }
      if (LANGS.every((l) => typeof v[l] === 'string')) {
        const anyFilled = LANGS.find((l) => v[l].trim());
        if (anyFilled) for (const l of LANGS) if (!v[l].trim()) E(`${p}.${l}`, `empty while "${anyFilled}" is not`);
      }
    };
    const checkText = (v, p, optional = false) => {
      if (v === undefined || v === null) { if (!optional) E(p, 'required text is missing'); return; }
      if (typeof v === 'string' || typeof v === 'number') { texts.push({ p, v: String(v) }); return; }
      if (!isObj(v)) { E(p, `text must be a string or {${langList}}`); return; }
      for (const k of Object.keys(v)) if (!LANGS.includes(k)) E(`${p}.${k}`, `unknown language key (allowed: ${LANGS.join(', ')})`);
      checkBi(v, p);
      for (const l of LANGS) if (typeof v[l] === 'string') texts.push({ p: `${p}.${l}`, v: v[l] });
    };
    const checkKeys = (o, allowed, p) => {
      for (const k of Object.keys(o)) if (!allowed.includes(k) && !isComment(k)) E(p ? `${p}.${k}` : k, 'unknown key');
    };
    const checkItems = (items, p) => {
      if (!Array.isArray(items) || !items.length) { E(p, 'must be a non-empty array'); return; }
      items.forEach((it, i) => {
        const ip = `${p}[${i}]`;
        if (isObj(it) && ('text' in it || 'children' in it)) {
          checkKeys(it, ['text', 'children'], ip);
          checkText(it.text, `${ip}.text`);
          if (it.children !== undefined) {
            if (!Array.isArray(it.children) || !it.children.length) E(`${ip}.children`, 'must be a non-empty array');
            else it.children.forEach((ch, j) => {
              if (isObj(ch) && ('text' in ch || 'children' in ch)) E(`${ip}.children[${j}]`, 'only one nesting level is allowed');
              else checkText(ch, `${ip}.children[${j}]`);
            });
          }
        } else checkText(it, ip);
      });
    };
    const finish = () => ({ errors: [...errors], warnings });

    if (!isObj(c)) { E('(root)', 'content must be a JSON object'); return finish(); }
    checkKeys(c, TOP_KEYS, '');
    if (typeof c.id !== 'string' || !c.id.trim()) E('id', 'required non-empty string');
    const baseErr = fileBaseError(c.base);
    if (baseErr) E('base', `required file base name: ${baseErr}`);
    if (c.outDir !== undefined && typeof c.outDir !== 'string') E('outDir', 'must be a string');
    if (c.set !== undefined) {
      if (typeof c.set !== 'string') E('set', 'must be a set id string');
      else if (!cfg.sets.some((s) => s.id === c.set)) E('set', `unknown set id "${c.set}" (configured: ${cfg.sets.map((s) => s.id).join(', ')})`);
      if (c.outDir !== undefined) E('set', 'use either "set" or "outDir", not both');
    }
    if (c.orientation !== undefined && !['portrait', 'landscape'].includes(c.orientation)) E('orientation', 'must be "portrait" or "landscape"');
    checkText(c.title, 'title');
    checkText(c.subtitle, 'subtitle', true);
    if (c.source !== undefined) {
      if (!isObj(c.source)) E('source', 'must be an object {"commit"?, "date"?} (missing fields default from the config)');
      else {
        checkKeys(c.source, ['commit', 'date'], 'source');
        for (const k of ['commit', 'date']) if (c.source[k] !== undefined && (typeof c.source[k] !== 'string' || !c.source[k].trim())) E(`source.${k}`, 'must be a non-empty string');
      }
    }
    if (!isObj(c.source) || c.source.commit === undefined) {
      const d = getDefaultSource();
      if (!d.commit) E('source.commit', `not given and no default from the config (${d.err})`);
    }
    if (!Array.isArray(c.blocks) || !c.blocks.length) { E('blocks', 'required non-empty array'); return finish(); }

    c.blocks.forEach((b, i) => {
      const p = `blocks[${i}]`;
      if (!isObj(b)) { E(p, 'block must be an object'); return; }
      if (!BLOCK_TYPES.includes(b.type)) { E(`${p}.type`, `unknown block type ${JSON.stringify(b.type)} (allowed: ${BLOCK_TYPES.join(', ')})`); return; }
      checkKeys(b, [...COMMON_BLOCK_KEYS, ...BLOCK_KEYS[b.type]], p);
      if (b.landscape !== undefined && typeof b.landscape !== 'boolean') E(`${p}.landscape`, 'must be boolean');
      switch (b.type) {
        case 'h1': case 'h2': case 'h3':
          checkText(b.text, `${p}.text`);
          if (b.anchor !== undefined) {
            if (typeof b.anchor !== 'string' || !ANCHOR_RE.test(b.anchor)) E(`${p}.anchor`, 'must match [A-Za-z0-9][A-Za-z0-9_.:-]*');
            else if (anchors.has(b.anchor)) E(`${p}.anchor`, `duplicate anchor "${b.anchor}" (first at ${anchors.get(b.anchor)})`);
            else anchors.set(b.anchor, p);
          }
          break;
        case 'p':
          checkText(b.text, `${p}.text`);
          if (b.italic !== undefined && typeof b.italic !== 'boolean') E(`${p}.italic`, 'must be boolean');
          break;
        case 'bullets': case 'numbered':
          checkItems(b.items, `${p}.items`);
          break;
        case 'table': {
          if (!Array.isArray(b.headers) || !b.headers.length) { E(`${p}.headers`, 'required non-empty array'); break; }
          const n = b.headers.length;
          b.headers.forEach((h, j) => checkText(h, `${p}.headers[${j}]`));
          if (!Array.isArray(b.rows)) E(`${p}.rows`, 'required array');
          else b.rows.forEach((r, ri) => {
            if (!Array.isArray(r)) { E(`${p}.rows[${ri}]`, 'row must be an array'); return; }
            if (r.length !== n) E(`${p}.rows[${ri}]`, `has ${r.length} cells, headers have ${n}`);
            r.forEach((cl, ci) => checkText(cl, `${p}.rows[${ri}][${ci}]`));
          });
          if (b.widths !== undefined) {
            if (!Array.isArray(b.widths) || b.widths.length !== n) E(`${p}.widths`, `must be an array of ${n} widths`);
            else b.widths.forEach((w, j) => {
              const ok = (typeof w === 'number' && w > 0) || (typeof w === 'string' && /^\d+(\.\d+)?%$/.test(w));
              if (!ok) E(`${p}.widths[${j}]`, 'must be twips (number > 0) or a percentage string like "25%"');
            });
          }
          if (b.mono !== undefined) {
            if (!Array.isArray(b.mono)) E(`${p}.mono`, 'must be an array of column indexes');
            else b.mono.forEach((m, j) => { if (!Number.isInteger(m) || m < 0 || m >= n) E(`${p}.mono[${j}]`, `column index out of range 0..${n - 1}`); });
          }
          break;
        }
        case 'note':
          if (!['info', 'warn'].includes(b.kind)) E(`${p}.kind`, 'must be "info" or "warn"');
          checkText(b.title, `${p}.title`, true);
          if (!Array.isArray(b.lines) || !b.lines.length) E(`${p}.lines`, 'required non-empty array');
          else b.lines.forEach((l, j) => checkText(l, `${p}.lines[${j}]`));
          break;
        case 'diagram':
          if (typeof b.href !== 'string' || !b.href.trim()) E(`${p}.href`, 'required non-empty string');
          else if (!/^[a-z][a-z0-9+.-]*:/i.test(b.href) && outDir && !fs.existsSync(path.resolve(outDir, b.href.split('#')[0]))
            && !fs.existsSync(path.resolve(outDir, safeDecode(b.href.split('#')[0])))) {
            warnings.push(`${p}.href: target not found relative to the output dir (${path.resolve(outDir, b.href)})`);
          }
          checkText(b.caption, `${p}.caption`);
          if (b.png !== undefined) {
            if (typeof b.png !== 'string' || !b.png.trim()) E(`${p}.png`, 'must be a non-empty string');
            else {
              const abs = path.resolve(baseDir, b.png);
              if (!fs.existsSync(abs)) E(`${p}.png`, `file not found: ${abs}`);
              else {
                const head = Buffer.alloc(8);
                const fd = fs.openSync(abs, 'r'); fs.readSync(fd, head, 0, 8, 0); fs.closeSync(fd);
                if (!head.equals(PNG_SIG)) E(`${p}.png`, `not a PNG file: ${abs}`);
              }
            }
          }
          break;
        case 'toc':
          if (b.levels !== undefined && (typeof b.levels !== 'string' || !/^[1-3]-[1-3]$/.test(b.levels))) E(`${p}.levels`, 'must be like "1-3"');
          break;
        case 'glossary':
          if (!Array.isArray(b.rows) || !b.rows.length) { E(`${p}.rows`, 'required non-empty array'); break; }
          b.rows.forEach((r, j) => {
            const rp = `${p}.rows[${j}]`;
            if (!isObj(r)) { E(rp, `row must be an object {${LANGS.join(', ')}, note?}`); return; }
            checkKeys(r, [...LANGS, 'note'], rp);
            checkBi(r, rp);
            for (const l of LANGS) if (typeof r[l] === 'string' && !r[l].trim()) E(`${rp}.${l}`, 'empty term');
            for (const l of LANGS) if (typeof r[l] === 'string') texts.push({ p: `${rp}.${l}`, v: r[l] });
            checkText(r.note, `${rp}.note`, true);
          });
          break;
        default: break;
      }
    });

    // distinct anchors must stay distinct as Word bookmark names (truncated + hashed)
    const marks = new Map();
    for (const [a, p] of anchors) {
      const id = bookmarkId(a);
      if (marks.has(id)) E(`${p}.anchor`, `anchor "${a}" maps to the same Word bookmark ${id} as "${marks.get(id)}"`);
      else marks.set(id, a);
    }
    // internal links must resolve to a declared heading anchor
    for (const { p, v } of texts) {
      for (const tk of parseInline(v)) {
        if (tk.t === 'link' && tk.href.startsWith('#') && !anchors.has(tk.href.slice(1))) E(p, `link to unknown anchor "${tk.href}"`);
      }
    }
    // generic sweep: any object (below the root) carrying one language key must carry all of them
    const sweep = (v, p) => {
      if (Array.isArray(v)) { v.forEach((x, i) => sweep(x, `${p}[${i}]`)); return; }
      if (!isObj(v)) return;
      if (p && LANGS.some((l) => l in v)) checkBi(v, p);
      for (const [k, x] of Object.entries(v)) if (!LANGS.includes(k)) sweep(x, p ? `${p}.${k}` : k);
    };
    sweep(c, '');
    return finish();
  }

  // ------------------------------------------------------------ rendering
  function renderBlock(b, ctx) {
    const { lang, I } = ctx;
    switch (b.type) {
      case 'h1': case 'h2': case 'h3': {
        ctx.stats.headings++;
        const runs = inlineRuns(tr(b.text, lang), { size: HEADING_SIZE[b.type] }, false);
        return [new Paragraph({ heading: HEADING[b.type], keepNext: true, children: b.anchor ? [new Bookmark({ id: bookmarkId(b.anchor), children: runs })] : runs })];
      }
      case 'p':
        ctx.stats.paragraphs++;
        return [para(inlineRuns(tr(b.text, lang), { italics: b.italic }), { after: 120 })];
      case 'bullets': case 'numbered': {
        const out = [];
        const instance = ctx.numInstance++;
        const lvl = (level) => (b.type === 'bullets' ? { bullet: { level } } : { numbering: { reference: 'docgen-numbered', level, instance } });
        for (const it of b.items) {
          const isNode = isObj(it) && ('text' in it || 'children' in it);
          out.push(para(inlineRuns(tr(isNode ? it.text : it, lang)), { ...lvl(0), after: 60 }));
          if (isNode && it.children) for (const ch of it.children) out.push(para(inlineRuns(tr(ch, lang)), { ...lvl(1), after: 40 }));
        }
        ctx.stats.listItems += out.length;
        out.push(para([], { after: 60 }));
        return out;
      }
      case 'table':
        return renderTable(b.headers, b.rows || [], { widths: b.widths, mono: b.mono }, ctx);
      case 'note': {
        const kind = b.kind;
        const title = b.title !== undefined ? tr(b.title, lang) : (kind === 'warn' ? I.warn : I.note);
        const kids = [new Paragraph({ spacing: { after: 60 }, children: inlineRuns(title, { bold: true }) })];
        for (const l of b.lines) kids.push(new Paragraph({ spacing: { after: 40 }, children: inlineRuns(tr(l, lang)) }));
        ctx.stats.notes++;
        const none = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
        return [new Table({
          columnWidths: [ctx.cw], width: { size: ctx.cw, type: WidthType.DXA }, layout: TableLayoutType.FIXED,
          borders: { top: none, bottom: none, right: none, insideHorizontal: none, insideVertical: none, left: { style: BorderStyle.SINGLE, size: 24, color: NOTE_BAR[kind] } },
          rows: [new TableRow({ children: [new TableCell({
            width: { size: ctx.cw, type: WidthType.DXA }, shading: { type: ShadingType.CLEAR, fill: NOTE_FILL[kind], color: 'auto' },
            margins: { top: 100, bottom: 100, left: 160, right: 160 }, children: kids,
          })] })],
        }), para([], { after: 120 })];
      }
      case 'diagram': {
        const out = [];
        const n = ++ctx.figN;
        if (b.png) {
          const data = fs.readFileSync(path.resolve(ctx.baseDir, b.png));
          const { w, h } = pngSize(data);
          const maxW = Math.floor(ctx.cw / 15);            // twips -> px @96dpi
          const maxH = Math.floor((ctx.ch / 15) * 0.8);
          const k = Math.min(1, maxW / w, maxH / h);
          out.push(para([new ImageRun({ type: 'png', data, transformation: { width: Math.round(w * k), height: Math.round(h * k) } })], { align: AlignmentType.CENTER, after: 60, keepNext: true }));
          ctx.stats.images++;
        }
        out.push(para([
          ...textRuns(`${I.figure} ${n}. `, { bold: true, italics: true, size: 18 }),
          ...inlineRuns(tr(b.caption, lang), { italics: true, size: 18 }),
        ], { align: AlignmentType.CENTER, after: 20 }));
        out.push(para([
          ...textRuns(`${I.interactive}: `, { size: 16, color: GREY }),
          new ExternalHyperlink({ link: hrefTarget(b.href), children: textRuns(b.href, { size: 16, font: MONO, style: 'Hyperlink', color: '0563C1' }) }),
        ], { align: AlignmentType.CENTER, after: 200 }));
        return out;
      }
      case 'pagebreak':
        return [new Paragraph({ children: [new PageBreak()] })];
      case 'toc':
        ctx.hasToc = true;
        return [
          para(textRuns(I.contents, { bold: true, size: 32, color: ACCENT }), { before: 120, after: 200 }),
          new TableOfContents(I.contents, { hyperlink: true, headingStyleRange: b.levels || '1-3' }),
          para(textRuns(I.tocHint, { italics: true, size: 16, color: GREY }), { before: 120, after: 120 }),
          new Paragraph({ children: [new PageBreak()] }),
        ];
      case 'glossary': {
        const other = LANGS.find((l) => l !== lang) || null;
        const esc = (s) => s.replace(/([`*[\]\\])/g, '\\$1');
        const withNote = b.rows.some((r) => r.note !== undefined);
        const headers = [I.langName(lang), ...(other ? [I.langName(other)] : []), ...(withNote ? [I.glossNote] : [])];
        const rows = b.rows.map((r) => [esc(r[lang]), ...(other ? [esc(r[other])] : []), ...(withNote ? [r.note === undefined ? '' : tr(r.note, lang)] : [])]);
        const widths = other ? (withNote ? ['30%', '30%', '40%'] : ['50%', '50%']) : (withNote ? ['40%', '60%'] : ['100%']);
        return renderTable(headers, rows, { widths, bold: [0] }, ctx);
      }
      default:
        throw new Error(`renderer: unhandled block type ${b.type}`);
    }
  }

  /** Render one language of a validated content object into a docx Document. */
  function render(c, lang, { baseDir }) {
    const I = I18N[lang];
    const docOrient = c.orientation || 'portrait';
    const stats = { headings: 0, paragraphs: 0, listItems: 0, tables: 0, tableRows: 0, notes: 0, images: 0 };
    const ctx = { lang, I, baseDir, figN: 0, numInstance: 0, stats, hasToc: false };
    const title = tr(c.title, lang);
    const src = { ...getDefaultSourceIfNeeded(c), ...(isObj(c.source) ? c.source : {}) };

    const titleChildren = [
      para([], { before: 2400, after: 0 }),
      para(textRuns(title, { size: 52, bold: true, color: ACCENT }), { after: 200 }),
    ];
    if (c.subtitle !== undefined) titleChildren.push(para(inlineRuns(tr(c.subtitle, lang), { size: 28 }), { after: 400 }));
    titleChildren.push(
      para(textRuns(I.langLabel, { size: 24, italics: true, color: GREY }), { after: 600 }),
      para([...textRuns(`${I.source}: ${I.commit} `, { color: GREY }), ...textRuns(src.commit, { font: MONO, size: BODY_SIZE - 1, color: GREY }), ...textRuns(` · ${src.date}`, { color: GREY })], { after: 60 }),
      para([...textRuns(`${I.document}: `, { color: GREY }), ...textRuns(c.base, { font: MONO, size: BODY_SIZE - 1, color: GREY })], { after: 60 }),
    );
    const sections = [{ properties: pageProps(docOrient), children: titleChildren }];

    // group consecutive blocks by orientation -> one section per group
    let cur = null;
    for (const b of c.blocks) {
      const o = b.landscape === true ? 'landscape' : b.landscape === false ? 'portrait' : docOrient;
      if (!cur || cur.o !== o) { cur = { o, blocks: [] }; sections.push(cur); }
      cur.blocks.push(b);
    }
    for (let s = 1; s < sections.length; s++) {
      const g = sections[s];
      ctx.cw = CONTENT_W[g.o]; ctx.ch = CONTENT_H[g.o];
      const children = [];
      for (const b of g.blocks) children.push(...renderBlock(b, ctx));
      sections[s] = { properties: pageProps(g.o), headers: { default: runningHeader(title) }, footers: { default: pageFooter(I) }, children };
    }

    const heading = (size, before, after) => ({ run: { font: BODY, size, bold: true, color: ACCENT }, paragraph: { spacing: { before, after }, keepNext: true } });
    const doc = new Document({
      creator: cfg.docgen.creator, title, description: `${c.id} (${lang})`,
      features: ctx.hasToc ? { updateFields: true } : undefined,
      styles: {
        default: {
          document: { run: { font: BODY, size: BODY_SIZE } },
          heading1: heading(HEADING_SIZE.h1, 360, 160), heading2: heading(HEADING_SIZE.h2, 280, 120), heading3: heading(HEADING_SIZE.h3, 220, 100),
        },
      },
      numbering: {
        config: [{
          reference: 'docgen-numbered',
          levels: [
            { level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.START, style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
            { level: 1, format: LevelFormat.LOWER_LETTER, text: '%2)', alignment: AlignmentType.START, style: { paragraph: { indent: { left: 1440, hanging: 360 } } } },
          ],
        }],
      },
      sections,
    });
    return { doc, stats };
  }
  function getDefaultSourceIfNeeded(c) {
    if (isObj(c.source) && c.source.commit !== undefined && c.source.date !== undefined) return {};
    const d = getDefaultSource();
    return { commit: d.commit, date: d.date };
  }

  // ------------------------------------------------------------ build one file
  /**
   * Build <base>_<suffix>.docx for every configured language from one content file.
   * Returns { content, status: "ok"|"invalid", errors, warnings, outputs, outDir }.
   * Throws on execution errors (I/O, renderer bugs) — the CLI maps those to exit 2.
   */
  async function buildFile(contentPath, { out } = {}) {
    const abs = path.resolve(contentPath);
    const baseDir = path.dirname(abs);
    const entry = { content: abs, status: 'ok', errors: [], warnings: [], outputs: [] };
    let c;
    try { c = JSON.parse(fs.readFileSync(abs, 'utf8').replace(/^﻿/, '')); } catch (e) {
      if (e.code) throw e; // I/O error -> execution error
      entry.status = 'invalid'; entry.errors.push(`(root): JSON parse error: ${e.message}`); return entry;
    }
    let outDir;
    if (out) outDir = path.resolve(out);
    else {
      const r = resolveOutDir(cfg, c, abs);
      if (r.error) { entry.status = 'invalid'; entry.errors.push(`(root): ${r.error}`); return entry; }
      outDir = r.dir;
    }
    entry.outDir = outDir;
    const v = validate(c, { baseDir, outDir });
    entry.errors = v.errors; entry.warnings = v.warnings;
    if (v.errors.length) { entry.status = 'invalid'; return entry; }
    fs.mkdirSync(outDir, { recursive: true });
    // render every language first, then write: a renderer failure never leaves a half-updated set
    const built = [];
    for (const lang of LANGS) {
      const { doc, stats } = render(c, lang, { baseDir });
      built.push({ lang, stats, buf: await Packer.toBuffer(doc), file: path.join(outDir, `${c.base}_${cfg.suffix[lang]}.docx`) });
    }
    for (const b of built) {
      fs.writeFileSync(b.file, b.buf);
      const back = fs.statSync(b.file).size;
      if (back !== b.buf.length) throw new Error(`re-read size mismatch for ${b.file}: ${back} != ${b.buf.length}`);
      entry.outputs.push({ lang: b.lang, path: b.file, bytes: b.buf.length, stats: b.stats });
    }
    return entry;
  }

  return { langs: LANGS, primary: P, validate, render, buildFile };
}

export function writeReport(file, report) {
  writeJsonReport(file, report);
}

export function printEntry(e, log = console.log) {
  const rel = path.relative(process.cwd(), e.content) || e.content;
  if (e.status === 'ok') {
    log(`OK    ${rel}`);
    for (const o of e.outputs) log(`  -> ${o.path}  ${o.bytes} bytes`);
  } else if (e.status === 'invalid') {
    log(`FAIL  ${rel}  (${e.errors.length} error${e.errors.length === 1 ? '' : 's'})`);
    for (const m of e.errors) log(`  x ${m}`);
  } else {
    log(`ERROR ${rel}: ${e.error}`);
  }
  for (const w of e.warnings || []) log(`  ! ${w}`);
}

export { ConfigError };
