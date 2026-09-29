#!/usr/bin/env node
// export-png.mjs — clean PNG export of archify diagrams for embedding in Word.
//
// Usage:
//   node export-png.mjs --config <cfg.json> [--dir <dir>]... [--only <name>] [--force]
//                       [--out <dir>] [--scale <n|native>] [--min-width <px>] [--chrome <exe>]
//
// Defaults:
//   --dir   every set of the config: <outputRoot>/<set.dir>, files <set.diagramPrefix>*.html;
//           a --dir given on the command line takes every *.html in it (non-recursive).
//           *.visual-check.* files are always ignored.
//   --out   <outputRoot>/<pngDir>
//   --scale 2        output = SVG viewBox * scale (fractional bump to reach --min-width)
//   --min-width 2000
//   output  <out>/<html-basename-without-.html>.png, report <out>/export-report.json
//
// Method (in order):
//   1. "viewer-export": drives the viewer's own PNG export
//      (Archify.exportMenu.run('png')) in headless Chrome, light theme, classic
//      preset, motion still. The viewer serializes only the diagram SVG, locks the
//      theme variables, paints the theme background and rasterizes at up to 4x.
//      The blob is captured in-page (no browser download), then resampled to the
//      target scale onto an opaque background.
//   2. "clip-screenshot" (fallback, only when the viewer API is missing or its
//      export fails): Page.captureScreenshot clipped to the diagram <svg>
//      bounding box at deviceScaleFactor = target scale.
//
// Chrome is located and driven exactly like archify's `visual-check`: ARCHIFY_CHROME
// env override, else the standard install paths (Chrome, Chromium, then Edge);
// DevTools protocol over --remote-debugging-pipe. No npm dependencies.
//
// Exit codes: 0 all ok (exported or up to date), 1 some diagrams failed,
//             2 execution error (bad args/config, no Chrome, browser crash).

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { loadConfig, ConfigError } from './lib/config.mjs';

// Filled from the config in main().
let OUT_DIR = null;
let REPORT = null;
let DEFAULT_DIRS = [];
const LOAD_VIEWPORT = { width: 1600, height: 1000 };
const EXIT = { ok: 0, failed: 1, error: 2 };
const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

class UsageError extends Error {}

// ---------------------------------------------------------------- args

function parseArgs(argv) {
  const opts = { config: null, out: null, dirs: [], only: [], force: false, scale: 2, minWidth: 2000, chrome: null, help: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const value = () => {
      const v = argv[++i];
      if (v === undefined) throw new UsageError(`${arg} requires a value`);
      return v;
    };
    switch (arg) {
      case '--config': opts.config = value(); break;
      case '--out': opts.out = path.resolve(value()); break;
      case '--dir': opts.dirs.push(path.resolve(value())); break;
      case '--only': opts.only.push(value()); break;
      case '--force': opts.force = true; break;
      case '--scale': {
        const v = value();
        if (v === 'native') opts.scale = 'native';
        else {
          const n = Number(v);
          if (!Number.isFinite(n) || n <= 0 || n > 4) throw new UsageError('--scale must be a number in (0,4] or "native"');
          opts.scale = n;
        }
        break;
      }
      case '--min-width': {
        const n = Number(value());
        if (!Number.isFinite(n) || n < 0) throw new UsageError('--min-width must be a non-negative number');
        opts.minWidth = n;
        break;
      }
      case '--chrome': opts.chrome = path.resolve(value()); break;
      case '-h': case '--help': opts.help = true; break;
      default: throw new UsageError(`unknown argument: ${arg}`);
    }
  }
  return opts;
}

function collectFiles(opts) {
  const sources = opts.dirs.length
    ? opts.dirs.map((dir) => ({ dir, pattern: /\.html?$/i }))
    : DEFAULT_DIRS;
  const files = [];
  for (const { dir, pattern } of sources) {
    if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) {
      throw new UsageError(`directory not found: ${dir}`);
    }
    for (const name of fs.readdirSync(dir).sort()) {
      if (!pattern.test(name) || /\.visual-check\./i.test(name)) continue;
      const full = path.join(dir, name);
      if (fs.statSync(full).isFile()) files.push(full);
    }
  }
  if (!opts.only.length) return files;
  return files.filter((file) => {
    const base = path.basename(file);
    const stem = base.replace(/\.html?$/i, '');
    return opts.only.some((o) => o === base || o === stem || stem.startsWith(o));
  });
}

// ---------------------------------------------------------------- Chrome (as archify visual-check)

function executable(file) {
  if (!file) return null;
  try {
    fs.accessSync(file, process.platform === 'win32' ? fs.constants.F_OK : fs.constants.X_OK);
    return path.resolve(file);
  } catch {
    return null;
  }
}

function findOnPath(command) {
  const dirs = String(process.env.PATH || '').split(path.delimiter).filter(Boolean);
  const exts = process.platform === 'win32'
    ? String(process.env.PATHEXT || '.EXE;.CMD;.BAT;.COM').split(';').filter(Boolean)
    : [''];
  for (const d of dirs) for (const e of exts) {
    const hit = executable(path.join(d, `${command}${e}`));
    if (hit) return hit;
  }
  return null;
}

function findChrome(explicit) {
  if (explicit) return executable(explicit);
  const env = process.env;
  if (Object.prototype.hasOwnProperty.call(env, 'ARCHIFY_CHROME')) return executable(env.ARCHIFY_CHROME);
  const fixed = [];
  const commands = [];
  if (process.platform === 'darwin') {
    fixed.push('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Chromium.app/Contents/MacOS/Chromium');
  } else if (process.platform === 'win32') {
    const roots = [env.PROGRAMFILES, env['PROGRAMFILES(X86)'], env.LOCALAPPDATA].filter(Boolean);
    for (const root of roots) {
      fixed.push(path.join(root, 'Google', 'Chrome', 'Application', 'chrome.exe'),
        path.join(root, 'Chromium', 'Application', 'chrome.exe'));
    }
    // Last resort beyond visual-check's list: Edge is Chromium and speaks the same protocol.
    for (const root of roots) fixed.push(path.join(root, 'Microsoft', 'Edge', 'Application', 'msedge.exe'));
  } else {
    commands.push('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser');
  }
  for (const c of fixed) { const hit = executable(c); if (hit) return hit; }
  for (const c of commands) { const hit = findOnPath(c); if (hit) return hit; }
  return null;
}

class PipeCdp {
  constructor(child, details) {
    this.child = child;
    this.details = details;
    this.nextId = 1;
    this.buffer = '';
    this.pending = new Map();
    this.waiters = [];
    this.dead = null;
    this.writePipe = child.stdio[3];
    this.readPipe = child.stdio[4];
    this.readPipe.setEncoding('utf8');
    this.readPipe.on('data', (chunk) => this.consume(chunk));
    this.writePipe.on('error', (e) => this.failAll(this.failure('write pipe', e)));
    this.readPipe.on('error', (e) => this.failAll(this.failure('read pipe', e)));
    child.once('error', (e) => this.failAll(this.failure('process launch', e)));
    child.once('close', (code, signal) => {
      this.failAll(this.failure('process exit', new Error(`Chrome closed with ${signal ? `signal ${signal}` : `exit code ${code}`}`)));
    });
  }

  failure(stage, error) {
    const err = new Error([`Chrome DevTools ${stage} failed: ${error?.message || error}`, this.details()].filter(Boolean).join('\n'));
    err.fatal = true;
    return err;
  }

  consume(chunk) {
    this.buffer += chunk;
    let boundary;
    while ((boundary = this.buffer.indexOf('\0')) >= 0) {
      const raw = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 1);
      if (!raw) continue;
      let msg;
      try { msg = JSON.parse(raw); } catch (e) { this.failAll(new Error(`invalid DevTools JSON: ${e.message}`)); continue; }
      if (msg.id) {
        const p = this.pending.get(msg.id);
        if (!p) continue;
        clearTimeout(p.timer);
        this.pending.delete(msg.id);
        if (msg.error) p.reject(new Error(`${p.method}: ${msg.error.message}`));
        else p.resolve(msg.result || {});
        continue;
      }
      for (const w of [...this.waiters]) {
        if (w.method !== msg.method || (w.sessionId && w.sessionId !== msg.sessionId)) continue;
        clearTimeout(w.timer);
        this.waiters.splice(this.waiters.indexOf(w), 1);
        w.resolve(msg.params || {});
      }
    }
  }

  send(method, params = {}, sessionId, timeoutMs = 15000) {
    if (this.dead) return Promise.reject(this.dead);
    const id = this.nextId++;
    const message = { id, method, params };
    if (sessionId) message.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`${method}: timed out after ${timeoutMs}ms`)); }, timeoutMs);
      this.pending.set(id, { method, resolve, reject, timer });
      this.writePipe.write(`${JSON.stringify(message)}\0`, (e) => { if (e) this.failAll(this.failure('write pipe', e)); });
    });
  }

  waitFor(method, sessionId, timeoutMs = 20000) {
    return new Promise((resolve, reject) => {
      const w = { method, sessionId, resolve, reject, timer: null };
      w.timer = setTimeout(() => { this.waiters.splice(this.waiters.indexOf(w), 1); reject(new Error(`${method}: event timed out after ${timeoutMs}ms`)); }, timeoutMs);
      this.waiters.push(w);
    });
  }

  failAll(error) {
    if (error?.fatal && !this.dead) this.dead = error;
    for (const p of this.pending.values()) { clearTimeout(p.timer); p.reject(error); }
    for (const w of this.waiters) { clearTimeout(w.timer); w.reject(error); }
    this.pending.clear();
    this.waiters = [];
  }
}

class Browser {
  constructor(chromePath) {
    this.profileRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'archify-export-png-profile-'));
    this.stderr = '';
    const args = [
      '--headless=new', '--remote-debugging-pipe', '--disable-gpu', '--hide-scrollbars',
      '--disable-background-networking', '--disable-component-update', '--disable-default-apps',
      '--disable-sync', '--metrics-recording-only', '--no-first-run', '--no-default-browser-check',
      '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows',
      '--disable-renderer-backgrounding', '--force-device-scale-factor=1',
      `--user-data-dir=${this.profileRoot}`, 'about:blank',
    ];
    if (process.env.ARCHIFY_CHROME_NO_SANDBOX === '1') args.unshift('--no-sandbox');
    this.child = spawn(chromePath, args, { stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe'] });
    this.child.stderr.setEncoding('utf8');
    this.child.stderr.on('data', (c) => { this.stderr = `${this.stderr}${c}`.slice(-4000); });
    this.cdp = new PipeCdp(this.child, () => (this.stderr.trim() ? `Chrome stderr:\n${this.stderr.trim()}` : ''));
    this.sessionPromise = this.attach();
  }

  async attach() {
    const targets = await this.cdp.send('Target.getTargets');
    let target = targets.targetInfos?.find((t) => t.type === 'page');
    if (!target) target = { targetId: (await this.cdp.send('Target.createTarget', { url: 'about:blank' })).targetId };
    const { sessionId } = await this.cdp.send('Target.attachToTarget', { targetId: target.targetId, flatten: true });
    await this.cdp.send('Page.enable', {}, sessionId);
    await this.cdp.send('Runtime.enable', {}, sessionId);
    // A native alert() would block the page; answer any dialog immediately.
    this.dialogs = [];
    const onDialog = () => this.cdp.waitFor('Page.javascriptDialogOpening', sessionId, 2 ** 31 - 1)
      .then((p) => {
        this.dialogs.push(p.message);
        return this.cdp.send('Page.handleJavaScriptDialog', { accept: true }, sessionId).catch(() => {});
      })
      .then(onDialog, () => {});
    onDialog();
    return sessionId;
  }

  async evaluate(expression, { awaitPromise = false, timeoutMs = 30000 } = {}) {
    const sessionId = await this.sessionPromise;
    const r = await this.cdp.send('Runtime.evaluate', { expression, awaitPromise, returnByValue: true }, sessionId, timeoutMs);
    if (r.exceptionDetails) {
      throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text || 'Runtime.evaluate failed');
    }
    return r.result?.value;
  }

  async load(file, deviceScaleFactor = 1) {
    const sessionId = await this.sessionPromise;
    await this.cdp.send('Emulation.setDeviceMetricsOverride', {
      ...LOAD_VIEWPORT, deviceScaleFactor, mobile: false,
    }, sessionId);
    await this.cdp.send('Emulation.setEmulatedMedia', {
      features: [{ name: 'prefers-color-scheme', value: 'light' }, { name: 'prefers-reduced-motion', value: 'reduce' }],
    }, sessionId);
    const url = new URL(pathToFileURL(file).href);
    url.searchParams.set('theme', 'light');
    const loaded = this.cdp.waitFor('Page.loadEventFired', sessionId);
    const nav = await this.cdp.send('Page.navigate', { url: url.href }, sessionId);
    if (nav.errorText) throw new Error(`navigation failed: ${nav.errorText}`);
    await loaded;
    return this.evaluate(PREPARE_JS, { awaitPromise: true });
  }

  async close() {
    this.cdp.failAll(new Error('export finished'));
    if (this.child.exitCode === null && this.child.signalCode === null) {
      this.child.kill('SIGTERM');
      await new Promise((resolve) => {
        const t = setTimeout(() => { try { this.child.kill('SIGKILL'); } catch {} resolve(); }, 1500);
        this.child.once('exit', () => { clearTimeout(t); resolve(); });
      });
    }
    try { fs.rmSync(this.profileRoot, { recursive: true, force: true }); } catch {}
  }
}

// ---------------------------------------------------------------- in-page scripts

// Same settle sequence visual-check uses, plus: force light theme + classic preset,
// neutralize alert(), and report the resolved state.
const PREPARE_JS = `(function () {
  var root = document.documentElement;
  root.setAttribute('data-motion', 'still');
  if (root.getAttribute('data-theme') !== 'light') root.setAttribute('data-theme', 'light');
  if (root.getAttribute('data-preset') !== 'classic') root.setAttribute('data-preset', 'classic');
  window.__exportAlerts = [];
  window.alert = function (m) { window.__exportAlerts.push(String(m)); };
  var panel = document.querySelector('.diagram-container');
  if (panel) panel.setAttribute('data-detail-level', 'read');
  var A = window.Archify || {};
  function stable(k) {
    return function () {
      if (A[k] && typeof A[k].whenStable === 'function') return A[k].whenStable();
    };
  }
  var fonts = document.fonts && document.fonts.ready ? document.fonts.ready.catch(function () {}) : Promise.resolve();
  return fonts.then(stable('readerLayout')).then(stable('viewerChromeLayout'))
    .then(stable('readerLayout')).then(stable('viewerChromeLayout'))
    .then(function () { return new Promise(function (r) { requestAnimationFrame(function () { requestAnimationFrame(r); }); }); })
    .then(function () {
      var svg = document.querySelector('.diagram-container svg');
      var vb = svg && svg.viewBox && svg.viewBox.baseVal;
      return {
        theme: root.getAttribute('data-theme'),
        preset: root.getAttribute('data-preset'),
        hasViewerExport: !!(A.exportMenu && typeof A.exportMenu.run === 'function'),
        hasSvg: !!svg,
        viewBox: vb ? { width: vb.width, height: vb.height } : null,
        bg: getComputedStyle(root).getPropertyValue('--bg').trim() || getComputedStyle(document.body).backgroundColor
      };
    });
})()`;

// Trigger the viewer's own PNG export, intercept the blob it hands to its
// download() helper, then resample to targetWidth on an opaque background.
function viewerExportJs({ targetWidth, bg }) {
  return `(function () {
  var targetWidth = ${JSON.stringify(targetWidth)};
  var bg = ${JSON.stringify(bg)};
  var captured = null;
  var origCreate = URL.createObjectURL;
  var origClick = HTMLAnchorElement.prototype.click;
  var blobs = new Map();
  URL.createObjectURL = function (obj) {
    var url = origCreate.call(URL, obj);
    if (obj instanceof Blob) blobs.set(url, obj);
    return url;
  };
  HTMLAnchorElement.prototype.click = function () {
    if (this.download && blobs.has(this.href)) { captured = { blob: blobs.get(this.href), name: this.download }; return; }
    return origClick.call(this);
  };
  function restore() { URL.createObjectURL = origCreate; HTMLAnchorElement.prototype.click = origClick; }
  window.__exportAlerts = [];
  document.documentElement.removeAttribute('data-last-export-error');
  return Promise.resolve(Archify.exportMenu.run('png')).then(function () {
    restore();
    var err = document.documentElement.getAttribute('data-last-export-error');
    if (!captured) throw new Error('viewer export produced no PNG' + (err ? ': ' + err : '') +
      (window.__exportAlerts.length ? ' | alert: ' + window.__exportAlerts.join(' / ') : ''));
    if (captured.blob.type && captured.blob.type !== 'image/png') throw new Error('viewer export blob type ' + captured.blob.type);
    return createImageBitmap(captured.blob);
  }, function (e) { restore(); throw e; }).then(function (bitmap) {
    var nativeW = bitmap.width, nativeH = bitmap.height;
    var w = targetWidth ? Math.round(targetWidth) : nativeW;
    if (w > nativeW) w = nativeW; // never upscale the viewer's raster
    var h = Math.round(nativeH * w / nativeW);
    var canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    var ctx = canvas.getContext('2d', { alpha: false });
    ctx.fillStyle = bg || '#ffffff';
    ctx.fillRect(0, 0, w, h);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(bitmap, 0, 0, w, h);
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (out) {
        if (!out) return reject(new Error('canvas.toBlob returned null'));
        var fr = new FileReader();
        fr.onload = function () {
          resolve({ dataUrl: fr.result, width: w, height: h, nativeWidth: nativeW, nativeHeight: nativeH, viewerFilename: captured.name });
        };
        fr.onerror = function () { reject(new Error('FileReader failed')); };
        fr.readAsDataURL(out);
      }, 'image/png');
    });
  });
})()`;
}

// Fallback: hide everything but the diagram svg, paint an opaque background,
// return its CSS-pixel bounding box for a clipped screenshot.
function clipPrepareJs({ cssWidth, bg }) {
  return `(function () {
  var svg = document.querySelector('.diagram-container svg') || document.querySelector('svg[viewBox]');
  if (!svg) throw new Error('no diagram <svg> found');
  var vb = svg.viewBox.baseVal;
  var host = document.createElement('div');
  host.id = '__export_host';
  host.style.cssText = 'position:absolute;left:0;top:0;margin:0;padding:0;z-index:2147483647;background:' + ${JSON.stringify(bg)} + ';';
  var clone = svg.cloneNode(true);
  clone.removeAttribute('style');
  clone.setAttribute('width', ${JSON.stringify(cssWidth)});
  clone.setAttribute('height', ${JSON.stringify(cssWidth)} * vb.height / vb.width);
  clone.style.display = 'block';
  host.appendChild(clone);
  Array.prototype.forEach.call(document.body.children, function (el) { el.style.visibility = 'hidden'; });
  document.body.appendChild(host);
  host.style.visibility = 'visible';
  document.body.style.background = ${JSON.stringify(bg)};
  var r = clone.getBoundingClientRect();
  return { x: r.left + window.scrollX, y: r.top + window.scrollY, width: r.width, height: r.height };
})()`;
}

// ---------------------------------------------------------------- PNG helpers

function pngInfo(buf) {
  const sig = '89504e470d0a1a0a';
  if (buf.length < 33 || buf.subarray(0, 8).toString('hex') !== sig || buf.subarray(12, 16).toString('ascii') !== 'IHDR') {
    throw new Error('output is not a PNG');
  }
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20), colorType: buf[25] };
}

function writeAtomic(file, data) {
  const tmp = `${file}.tmp-${process.pid}`;
  try {
    fs.writeFileSync(tmp, data);
    fs.renameSync(tmp, file);
  } finally {
    try { fs.rmSync(tmp, { force: true }); } catch {}
  }
}

function targetScale(opts, vbWidth) {
  if (opts.scale === 'native') return null;
  return Math.max(opts.scale, opts.minWidth / vbWidth);
}

// ---------------------------------------------------------------- export one

async function exportOne(browser, file, png, opts) {
  const state = await browser.load(file);
  if (!state.hasSvg || !state.viewBox) throw new Error('no diagram <svg> with a viewBox in .diagram-container');
  if (state.theme !== 'light') throw new Error(`theme resolved to "${state.theme}", expected light`);
  const bg = state.bg || '#ffffff';
  const scale = targetScale(opts, state.viewBox.width);
  const notes = [];

  if (state.hasViewerExport) {
    try {
      const targetWidth = scale ? state.viewBox.width * scale : null;
      const r = await browser.evaluate(viewerExportJs({ targetWidth, bg }), { awaitPromise: true, timeoutMs: 90000 });
      const buf = Buffer.from(r.dataUrl.replace(/^data:image\/png;base64,/, ''), 'base64');
      return {
        buf, method: 'viewer-export', theme: state.theme, preset: state.preset, background: bg,
        viewBox: state.viewBox, nativeWidth: r.nativeWidth, nativeHeight: r.nativeHeight,
        scale: r.width / state.viewBox.width, notes,
      };
    } catch (error) {
      if (error.fatal) throw error;
      notes.push(`viewer-export failed, fell back to clip-screenshot: ${error.message}`);
      await browser.load(file); // reset page state before the fallback
    }
  } else {
    notes.push('viewer export API (Archify.exportMenu.run) not present; using clip-screenshot');
  }

  const s = scale || 2;
  const cssWidth = Math.round(state.viewBox.width);
  const sessionId = await browser.sessionPromise;
  const clip = await browser.evaluate(clipPrepareJs({ cssWidth, bg }));
  await browser.cdp.send('Emulation.setDeviceMetricsOverride', {
    width: Math.max(LOAD_VIEWPORT.width, Math.ceil(clip.x + clip.width)),
    height: Math.max(LOAD_VIEWPORT.height, Math.ceil(clip.y + clip.height)),
    deviceScaleFactor: 1, mobile: false,
  }, sessionId);
  const shot = await browser.cdp.send('Page.captureScreenshot', {
    format: 'png', fromSurface: true, captureBeyondViewport: true,
    clip: { x: clip.x, y: clip.y, width: clip.width, height: clip.height, scale: s },
  }, sessionId, 60000);
  if (!shot.data) throw new Error('empty screenshot');
  return {
    buf: Buffer.from(shot.data, 'base64'), method: 'clip-screenshot', theme: state.theme, preset: state.preset,
    background: bg, viewBox: state.viewBox, nativeWidth: null, nativeHeight: null, scale: s, notes,
  };
}

// ---------------------------------------------------------------- main

async function main() {
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (e) {
    console.error(`export-png: ${e.message}`);
    return EXIT.error;
  }
  if (opts.help) {
    console.log(fs.readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').slice(1, 27).map((l) => l.replace(/^\/\/ ?/, '')).join('\n'));
    return EXIT.ok;
  }

  let cfg;
  try {
    if (!opts.config) throw new UsageError('--config <path> is required');
    cfg = loadConfig(opts.config);
  } catch (e) {
    console.error(`export-png: ${e instanceof ConfigError ? 'config error' : 'usage error'}: ${e.message}`);
    return EXIT.error;
  }
  OUT_DIR = opts.out || cfg.pngDir;
  REPORT = path.join(OUT_DIR, 'export-report.json');
  DEFAULT_DIRS = cfg.sets.map((s) => ({ dir: s.dir, pattern: new RegExp(`^${escRe(s.diagramPrefix)}.*\\.html$`, 'i') }));

  let files;
  try {
    files = collectFiles(opts);
  } catch (e) {
    console.error(`export-png: ${e.message}`);
    return EXIT.error;
  }
  if (!files.length) {
    console.error('export-png: no diagram HTML files matched');
    return opts.only.length ? EXIT.failed : EXIT.error;
  }
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const report = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    tool: fileURLToPath(import.meta.url),
    config: cfg.file,
    options: { out: OUT_DIR, scale: opts.scale, minWidth: opts.minWidth, force: opts.force, only: opts.only, dirs: opts.dirs.length ? opts.dirs : DEFAULT_DIRS.map((d) => d.dir) },
    chrome: null,
    summary: { total: files.length, exported: 0, upToDate: 0, failed: 0 },
    items: [],
  };
  const writeReport = () => writeAtomic(REPORT, `${JSON.stringify(report, null, 2)}\n`);

  // Plan: stale check and name collisions before launching Chrome.
  const seen = new Map();
  const todo = [];
  for (const file of files) {
    const stem = path.basename(file).replace(/\.html?$/i, '');
    const png = path.join(OUT_DIR, `${stem}.png`);
    if (seen.has(stem)) {
      report.items.push({ file, png, status: 'failed', error: `output name collides with ${seen.get(stem)}` });
      report.summary.failed++;
      continue;
    }
    seen.set(stem, file);
    if (!opts.force && fs.existsSync(png) && fs.statSync(png).mtimeMs > fs.statSync(file).mtimeMs) {
      const buf = fs.readFileSync(png);
      let info = {};
      try { info = pngInfo(buf); } catch {}
      report.items.push({ file, png, status: 'up-to-date', width: info.width ?? null, height: info.height ?? null, bytes: buf.length, method: 'skipped' });
      report.summary.upToDate++;
      continue;
    }
    todo.push({ file, png });
  }

  if (todo.length) {
    const chromePath = findChrome(opts.chrome);
    if (!chromePath) {
      report.chrome = { status: 'unavailable' };
      report.error = 'Chrome/Chromium not found. Set ARCHIFY_CHROME or pass --chrome <exe>.';
      writeReport();
      console.error(`export-png: ${report.error}`);
      return EXIT.error;
    }
    report.chrome = { status: 'available', executable: chromePath };
    const browser = new Browser(chromePath);
    let fatal = null;
    try {
      await browser.sessionPromise;
      for (const { file, png } of todo) {
        const t0 = Date.now();
        try {
          const r = await exportOne(browser, file, png, opts);
          const info = pngInfo(r.buf);
          if (info.width < opts.minWidth && opts.scale !== 'native') {
            throw new Error(`PNG width ${info.width} < --min-width ${opts.minWidth}`);
          }
          writeAtomic(png, r.buf);
          const item = {
            file, png, status: 'exported', width: info.width, height: info.height, bytes: r.buf.length,
            method: r.method, theme: r.theme, preset: r.preset, background: r.background,
            viewBox: r.viewBox, scale: Number(r.scale.toFixed(4)),
            viewerRaster: r.nativeWidth ? { width: r.nativeWidth, height: r.nativeHeight } : null,
            ms: Date.now() - t0,
          };
          if (r.notes.length) item.notes = r.notes;
          report.items.push(item);
          report.summary.exported++;
          console.log(`ok    ${path.basename(png)}  ${info.width}x${info.height}  ${(r.buf.length / 1024).toFixed(0)} KB  ${r.method}`);
        } catch (error) {
          report.items.push({ file, png, status: 'failed', error: error.message, ms: Date.now() - t0 });
          report.summary.failed++;
          console.error(`FAIL  ${path.basename(file)}: ${error.message.split('\n')[0]}`);
          if (error.fatal) { fatal = error; break; }
        }
      }
    } catch (error) {
      fatal = error;
    } finally {
      await browser.close();
    }
    if (fatal) {
      report.error = fatal.message;
      writeReport();
      console.error(`export-png: browser failure: ${fatal.message.split('\n')[0]}`);
      return EXIT.error;
    }
  }

  writeReport();
  const s = report.summary;
  console.log(`export-png: ${s.exported} exported, ${s.upToDate} up to date, ${s.failed} failed -> ${OUT_DIR}`);
  return s.failed ? EXIT.failed : EXIT.ok;
}

main().then((code) => { process.exitCode = code; }, (error) => {
  console.error(`export-png: ${error.stack || error.message}`);
  process.exitCode = EXIT.error;
});
