#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

function parseArgs(argv) {
  const result = { files: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--module") result.module = argv[++index];
    else if (value === "--max-bytes") result.maxBytes = Number(argv[++index]);
    else if (value === "--warning-bytes") result.warningBytes = Number(argv[++index]);
    else if (value === "--file") result.files.push(argv[++index]);
    else throw new Error(`unknown argument: ${value}`);
  }
  if (!result.module || !Number.isFinite(result.maxBytes) || result.files.length === 0) {
    throw new Error("usage: dsh_probe.mjs --module FILE --max-bytes N [--warning-bytes N] --file DISPLAY=PATH ...");
  }
  return result;
}

const args = parseArgs(process.argv.slice(2));
const loaded = [];
for (const spec of args.files) {
  const separator = spec.indexOf("=");
  if (separator < 1) throw new Error(`invalid --file value: ${spec}`);
  const displayPath = spec.slice(0, separator);
  const absolutePath = spec.slice(separator + 1);
  loaded.push({
    displayPath,
    absolutePath,
    content: await readFile(absolutePath, "utf8"),
  });
}

const api = await import(pathToFileURL(args.module).href);
if (typeof api.renderAgentInstructions !== "function") {
  throw new Error("DSH module does not export renderAgentInstructions");
}
const rendered = api.renderAgentInstructions(loaded, { maxBytes: args.maxBytes });
const bytes = Buffer.byteLength(rendered.text, "utf8");
const report = {
  bytes,
  max_bytes: args.maxBytes,
  warning_bytes: args.warningBytes || null,
  warning: Number.isFinite(args.warningBytes) && bytes > args.warningBytes,
  omitted: rendered.omitted.map((item) => item.displayPath),
  truncated: rendered.truncated,
  represented: loaded
    .map((item) => item.displayPath)
    .filter((path) => !rendered.omitted.some((item) => item.displayPath === path)),
};
process.stdout.write(`${JSON.stringify(report)}\n`);
if (report.omitted.length > 0 || report.truncated.length > 0 || bytes > args.maxBytes) {
  process.exitCode = 2;
}
