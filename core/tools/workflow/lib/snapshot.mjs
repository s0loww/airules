import { createHash } from 'node:crypto'
import { lstat, open, readdir, realpath } from 'node:fs/promises'
import { isAbsolute, relative, resolve, sep } from 'node:path'
import { digest } from './contracts.mjs'

export function fail(code) { throw Object.assign(new Error(code), { code }) }
export const hashBytes = bytes => createHash('sha256').update(bytes).digest('hex')
export const within = (root, target) => {
  const rel = relative(root, target)
  return !isAbsolute(rel) && rel !== '..' && !rel.startsWith(`..${sep}`)
}

export async function projectPath(root, rel) {
  if (typeof rel !== 'string' || !rel || isAbsolute(rel) || rel.includes('\0') || rel.split(/[\\/]/u).includes('..')) fail('INVALID_PROJECT_PATH')
  const target = resolve(root, rel)
  if (!within(root, target)) fail('PATH_ESCAPE')
  let cursor = root
  for (const part of relative(root, target).split(sep).filter(Boolean)) {
    cursor = resolve(cursor, part)
    if ((await lstat(cursor)).isSymbolicLink()) fail('SYMLINK_INPUT')
  }
  if (!within(root, await realpath(target))) fail('PATH_ESCAPE')
  return target
}

export async function safeRead(root, path, limit) {
  if (!within(root, await realpath(path))) fail('PATH_ESCAPE')
  const before = await lstat(path)
  if (!before.isFile() || before.isSymbolicLink() || before.size > limit) fail('UNSAFE_INPUT_FILE')
  const handle = await open(path, 'r')
  try {
    const opened = await handle.stat()
    if (opened.dev !== before.dev || opened.ino !== before.ino) fail('INPUT_CHANGED_DURING_READ')
    const chunks = []; let size = 0
    while (true) {
      const buffer = Buffer.alloc(65536)
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, null)
      if (!bytesRead) break
      size += bytesRead
      if (size > limit) fail('INPUT_LIMIT')
      chunks.push(buffer.subarray(0, bytesRead))
    }
    const after = await handle.stat()
    const current = await lstat(path)
    if (current.isSymbolicLink() || current.dev !== after.dev || current.ino !== after.ino
      || before.size !== after.size || before.mtimeMs !== after.mtimeMs
      || !within(root, await realpath(path))) fail('INPUT_CHANGED_DURING_READ')
    return Buffer.concat(chunks)
  } finally { await handle.close() }
}

export async function snapshot(root, paths, stateDir) {
  const entries = new Map()
  let bytes = 0, visited = 0
  async function visit(path, depth = 0) {
    if (++visited > 40000 || depth > 64) fail('INPUT_LIMIT')
    const stat = await lstat(path)
    if (stat.isSymbolicLink()) fail('SYMLINK_INPUT')
    if (within(path, stateDir)) fail('STATE_INSIDE_INPUT_SCOPE')
    if (stat.isDirectory()) {
      for (const child of (await readdir(path)).sort()) await visit(resolve(path, child), depth + 1)
    } else if (stat.isFile()) {
      const rel = relative(root, path).split(sep).join('/')
      if (entries.has(rel)) return
      if (stat.size > 16 * 1024 * 1024 || entries.size >= 20000) fail('INPUT_LIMIT')
      const value = await safeRead(root, path, 16 * 1024 * 1024)
      bytes += value.length
      if (bytes > 128 * 1024 * 1024) fail('INPUT_LIMIT')
      entries.set(rel, { path: rel, bytes: value.length, digest: hashBytes(value) })
    } else fail('UNSUPPORTED_INPUT')
  }
  for (const rel of paths) await visit(await projectPath(root, rel))
  const manifest = [...entries.values()].sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0)
  return { digest: digest(manifest), files: manifest.length, bytes }
}
