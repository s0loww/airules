// Minimal read-only ZIP reader (no dependencies): enough for .docx parts.
// readZip(buf) -> Map<name, () => Buffer> (entries are inflated lazily).
// Supports stored (0) and deflated (8) entries; no ZIP64, no encryption (docx never uses them).
import zlib from 'node:zlib';

export function readZip(buf) {
  const EOCD = 0x06054b50; const CEN = 0x02014b50; const LOC = 0x04034b50;
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 22 - 0xffff); i--) {
    if (buf.readUInt32LE(i) === EOCD) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('not a ZIP file (no end of central directory)');
  const count = buf.readUInt16LE(eocd + 10);
  let p = buf.readUInt32LE(eocd + 16);
  const entries = new Map();
  for (let n = 0; n < count; n++) {
    if (buf.readUInt32LE(p) !== CEN) throw new Error(`bad central directory entry at ${p}`);
    const flags = buf.readUInt16LE(p + 8);
    const method = buf.readUInt16LE(p + 10);
    const csize = buf.readUInt32LE(p + 20);
    const nameLen = buf.readUInt16LE(p + 28);
    const extraLen = buf.readUInt16LE(p + 30);
    const commentLen = buf.readUInt16LE(p + 32);
    const local = buf.readUInt32LE(p + 42);
    const name = buf.subarray(p + 46, p + 46 + nameLen).toString(flags & 0x800 ? 'utf8' : 'latin1');
    p += 46 + nameLen + extraLen + commentLen;
    entries.set(name, () => {
      if (buf.readUInt32LE(local) !== LOC) throw new Error(`bad local header for ${name}`);
      const start = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28);
      const data = buf.subarray(start, start + csize);
      if (method === 0) return Buffer.from(data);
      if (method === 8) return zlib.inflateRawSync(data);
      throw new Error(`${name}: unsupported compression method ${method}`);
    });
  }
  return entries;
}

/** External relationship targets of every *.rels part of a docx: [{ part, id, target }]. */
export function docxExternalTargets(buf) {
  const zip = readZip(buf);
  const out = [];
  for (const [name, get] of zip) {
    if (!name.endsWith('.rels')) continue;
    const xml = get().toString('utf8');
    for (const m of xml.matchAll(/<Relationship\b[^>]*>/g)) {
      const tag = m[0];
      if (!/\bTargetMode\s*=\s*"External"/.test(tag)) continue;
      const t = /\bTarget\s*=\s*"([^"]*)"/.exec(tag);
      const id = /\bId\s*=\s*"([^"]*)"/.exec(tag);
      if (t) out.push({ part: name, id: id ? id[1] : null, target: decodeXml(t[1]) });
    }
  }
  return out;
}

export const decodeXml = (s) => s.replace(/&(lt|gt|amp|quot|apos|#\d+|#x[0-9a-fA-F]+);/g, (m, e) => {
  if (e[0] === '#') return String.fromCodePoint(e[1] === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
  return { lt: '<', gt: '>', amp: '&', quot: '"', apos: "'" }[e];
});
