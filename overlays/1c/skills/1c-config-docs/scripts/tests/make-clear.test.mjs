// make-clear.mjs: DryRun by default, --apply writes, only files from its own manifest are ever
// removed, a foreign file is left in place, a non-empty destination without a manifest is refused.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const SCRIPTS = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..');

function write(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text, 'utf8');
}

function setup() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'make-clear-test-'));
  const out = path.join(root, 'out');
  write(path.join(out, 'index.html'),
    '<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>T</title></head>'
    + '<body><a href="x-a.html">a</a></body></html>\n');
  write(path.join(out, 'x-a.html'), '<!doctype html><html><head><title>a</title></head><body>a</body></html>\n');
  const cfg = path.join(root, 'cfg.json');
  write(cfg, JSON.stringify({
    languages: { primary: { code: 'ru' } },
    outputRoot: out,
    source: { commit: 'test' },
    sets: [{ id: 'b', dir: '.', diagramPrefix: 'x-', title: 'T' }],
  }));
  const dest = path.join(root, 'copy');
  const run = (...extra) => spawnSync(process.execPath,
    [path.join(SCRIPTS, 'make-clear.mjs'), '--config', cfg, '--dest', dest, '--report', path.join(root, 'r.json'), ...extra],
    { encoding: 'utf8' });
  return { root, out, dest, manifest: `${dest}.make-clear-manifest.json`, run };
}

test('make-clear ownership: dry run, apply, foreign, stale, refusal', () => {
  const t = setup();
  try {
    // 1. default is a dry run: nothing written
    let r = t.run();
    assert.equal(r.status, 0, r.stdout + r.stderr);
    assert.ok(!fs.existsSync(t.dest), 'a dry run created the destination');

    // 2. --apply writes the copy and the manifest next to it
    r = t.run('--apply');
    assert.equal(r.status, 0, r.stdout + r.stderr);
    assert.ok(fs.existsSync(path.join(t.dest, 'index.html')) && fs.existsSync(path.join(t.dest, 'x-a.html')));
    assert.deepEqual(JSON.parse(fs.readFileSync(t.manifest, 'utf8')).files, ['index.html', 'x-a.html']);

    // 3. a file we did not write is left in place and reported
    write(path.join(t.dest, 'precious.txt'), 'keep me');
    r = t.run('--apply');
    assert.equal(r.status, 1, 'a foreign file must be a finding');
    assert.equal(fs.readFileSync(path.join(t.dest, 'precious.txt'), 'utf8'), 'keep me');

    // 4. a file of the previous copy that is no longer produced is removed
    fs.rmSync(path.join(t.dest, 'precious.txt'));
    fs.rmSync(path.join(t.out, 'x-a.html'));
    write(path.join(t.out, 'index.html'),
      '<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>T</title></head><body>no diagrams</body></html>\n');
    r = t.run('--apply');
    assert.equal(r.status, 0, r.stdout + r.stderr);
    assert.ok(!fs.existsSync(path.join(t.dest, 'x-a.html')), 'the stale diagram was not removed');

    // 5. no manifest and a file outside the plan: refused, nothing removed
    fs.rmSync(t.manifest);
    write(path.join(t.dest, 'extra.txt'), 'not ours');
    r = t.run('--apply');
    assert.equal(r.status, 2, 'a non-empty destination without a manifest must be refused');
    assert.ok(fs.existsSync(path.join(t.dest, 'extra.txt')));

    // 6. --apply and --dry-run together are a usage error
    assert.equal(t.run('--apply', '--dry-run').status, 2);
  } finally {
    fs.rmSync(t.root, { recursive: true, force: true });
  }
});
