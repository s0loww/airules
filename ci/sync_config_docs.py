#!/usr/bin/env python3
"""Sync `overlays/1c/skills/1c-config-docs` from the skill's own repository.

Maintainer tool, not installed. The skill (documentation of a 1C configuration from its
code) is developed in its own git repository, D:\\AI_Projects\\1c-docs-skill, next to the
workspace with its runs and the equivalence regression. This script copies the pinned
commit of its `1c-config-docs/` folder:

* `git archive <commit> 1c-config-docs/` — tracked files of that commit only;
* text files get LF, `*.ps1` CRLF + UTF-8 BOM (repository rule ps1-bom);
* `KEEP` — our files in the destination (the pin), never overwritten or deleted.

No patches: everything airules-specific lives in the skill's source (SKILL.md →
"Агенты и модели"), so the copy is byte-for-byte the skill.

Usage:
    python ci/sync_config_docs.py [--source D:/AI_Projects/1c-docs-skill] [--ref main] [--check]
"""
import argparse
import io
import os
import subprocess
import sys
import tarfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(REPO, "overlays", "1c", "skills", "1c-config-docs")
DEFAULT_SOURCE = r"D:\AI_Projects\1c-docs-skill"
DEFAULT_REF = "main"
PREFIX = "1c-config-docs/"
KEEP = {"UPSTREAM.md"}
TEXT_SUFFIXES = (".mjs", ".js", ".json", ".md", ".txt", ".gitignore")


def normalize(rel, data):
    if rel.endswith(".ps1"):
        text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\n", "\r\n")
        return b"\xef\xbb\xbf" + text.encode("utf-8")
    if rel.endswith(TEXT_SUFFIXES):
        return data.replace(b"\r\n", b"\n")
    return data


def export(source, ref):
    commit = subprocess.run(["git", "-C", source, "rev-parse", ref], capture_output=True, text=True,
                            check=True).stdout.strip()
    raw = subprocess.run(["git", "-C", source, "archive", "--format=tar", commit, PREFIX.rstrip("/")],
                         capture_output=True, check=True).stdout
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for m in tar.getmembers():
            rel = m.name[len(PREFIX):]
            if m.isfile() and rel:
                files[rel] = normalize(rel, tar.extractfile(m).read())
    return commit, files


def listing(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root).replace("\\", "/")] = p
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--ref", default=DEFAULT_REF)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    dirty = subprocess.run(["git", "-C", args.source, "status", "--porcelain", "--", PREFIX],
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        print("WARNING: uncommitted changes in the skill source are NOT synced:\n" + dirty)
    commit, files = export(args.source, args.ref)
    if "SKILL.md" not in files:
        print("ERROR SKILL.md missing in the export")
        return 1

    plan = []
    for rel, data in sorted(files.items()):
        dst = os.path.join(DEST, rel.replace("/", os.sep))
        old = open(dst, "rb").read() if os.path.isfile(dst) else None
        if old != data:
            plan.append(("new" if old is None else "update", rel))
            if not args.check:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, "wb").write(data)
    if os.path.isdir(DEST):
        for rel, path in sorted(listing(DEST).items()):
            if rel not in files and rel not in KEEP and "/node_modules/" not in "/" + rel:
                plan.append(("delete", rel))
                if not args.check:
                    os.remove(path)

    if not args.check:
        pin = os.path.join(DEST, "UPSTREAM.md")
        if os.path.isfile(pin):
            text = open(pin, encoding="utf-8").read()
            marker = "Pinned commit: `"
            if marker in text:
                head, tail = text.split(marker, 1)
                text = head + marker + commit + "`" + tail.split("`", 1)[1]
                open(pin, "w", encoding="utf-8", newline="\n").write(text)

    counts = {}
    for kind, rel in plan:
        counts[kind] = counts.get(kind, 0) + 1
    for kind, rel in plan[:40]:
        print("{0:7} {1}".format(kind, rel))
    size = sum(len(v) for v in files.values())
    print("1c-config-docs {0} ({1}): {2} files, {3:.2f} MB; {4}".format(
        args.ref, commit[:7], len(files), size / 1e6, counts or "no changes"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
