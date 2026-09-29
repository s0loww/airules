#!/usr/bin/env python3
"""Sync `core/skills/archify` from our archify fork.

Maintainer tool, not installed. archify (tt-a1i/archify, MIT) is vendored from our fork
in D:\\AI_Projects\\diag_builder (branch `detail-link`: node fields `link` and
`description`, see the fork's FORK.md). The fork's git history is the source of truth for
those changes and runs archify's own golden tests; this script only copies a pinned commit.

* `git archive <commit> archify/` — exactly the tracked files of that commit, never the
  working tree (the fork folder holds untracked experiments);
* `EXCLUDE` — what the installed skill does not need at run time (tests, rendered example
  pages, build-time generators that need devDependencies, the upstream update checker);
* `KEEP` — our files in the destination, never overwritten or deleted;
* `patch_skill` — exact-anchor edits of SKILL.md (the update-awareness section is cut up to
  the next `## ` heading; the description is shortened); an anchor that no longer matches
  fails the sync.

The run-time needs no npm packages (verified: bin/, renderers/, scripts/check-render-output
import only node:*); Node >= 18 is the only requirement.

Usage:
    python ci/sync_archify.py [--fork D:/AI_Projects/diag_builder] [--ref detail-link] [--check]
"""
import argparse
import fnmatch
import io
import os
import subprocess
import sys
import tarfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(REPO, "core", "skills", "archify")
DEFAULT_FORK = r"D:\AI_Projects\diag_builder"
DEFAULT_REF = "detail-link"
PREFIX = "archify/"

KEEP = {"UPSTREAM.md"}

EXCLUDE = [
    "test/*",                     # archify's own test suite: runs in the fork, not in projects
    "examples/*.html",            # rendered example pages (3.6 MB); SKILL.md reads the JSON ones
    "package-lock.json",          # nothing is installed: the run-time has no npm dependencies
    "skill-release.json",         # upstream release channel, read only by the update checker
    "scripts/check-update.mjs",   # asks tt-a1i for updates: would steer users off the fork
    "scripts/update-contract.mjs",
    "scripts/generate-*.mjs",     # build-time generators, need devDependencies
    "renderers/*/README.md",      # renderer developer notes; SKILL.md and references never read them
]

TEXT_SUFFIXES = (".mjs", ".js", ".json", ".md", ".html", ".css", ".svg", ".txt")

UPDATE_SECTION = "## Update awareness\n"
DESCRIPTION_NEW = (
    "description: Create validated architecture, workflow, sequence, data-flow and lifecycle "
    "diagrams as standalone interactive HTML (inline SVG, PNG export) from a typed JSON spec; "
    "nodes may link to neighbouring diagrams. Use for standalone diagrams; inline diagrams in "
    "Markdown use mermaid-diagrams.\n")


def matches(rel):
    return any(fnmatch.fnmatch(rel, pat) for pat in EXCLUDE)


def export(fork, ref):
    commit = subprocess.run(["git", "-C", fork, "rev-parse", ref], capture_output=True, text=True,
                            check=True).stdout.strip()
    raw = subprocess.run(["git", "-C", fork, "archive", "--format=tar", commit, PREFIX.rstrip("/")],
                         capture_output=True, check=True).stdout
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            rel = m.name[len(PREFIX):]
            if rel and not matches(rel):
                data = tar.extractfile(m).read()
                # git archive applies the fork's checkout EOL (CRLF on Windows); the
                # distribution stores these text files with LF (.gitattributes), so the
                # install manifest hashes the same bytes on every machine.
                if rel.endswith(TEXT_SUFFIXES) or rel == "LICENSE":
                    data = data.replace(b"\r\n", b"\n")
                files[rel] = data
    return commit, files


def patch_skill(text, errors):
    # 1. the update-awareness section goes: it would point users at upstream releases
    if text.count(UPDATE_SECTION) != 1:
        errors.append("SKILL.md: section anchor %r matched %dx" % (UPDATE_SECTION, text.count(UPDATE_SECTION)))
    else:
        start = text.index(UPDATE_SECTION)
        nxt = text.find("\n## ", start + len(UPDATE_SECTION))
        text = text[:start] + (text[nxt + 1:] if nxt != -1 else "")
    # 2. a short description that also routes against mermaid-diagrams
    lines = text.split("\n")
    idx = [i for i, l in enumerate(lines) if l.startswith("description: ")]
    if len(idx) != 1:
        errors.append("SKILL.md: expected one 'description:' line, found %d" % len(idx))
    else:
        lines[idx[0]] = DESCRIPTION_NEW.rstrip("\n")
        text = "\n".join(lines)
    if "check-update" in text:
        errors.append("SKILL.md still mentions check-update after the patch")
    return text


def listing(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root).replace("\\", "/")] = p
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fork", default=DEFAULT_FORK)
    ap.add_argument("--ref", default=DEFAULT_REF)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    commit, files = export(args.fork, args.ref)
    errors = []
    if "SKILL.md" not in files:
        errors.append("SKILL.md missing in the export")
    else:
        text = files["SKILL.md"].decode("utf-8").replace("\r\n", "\n")
        files["SKILL.md"] = patch_skill(text, errors).encode("utf-8")
    if errors:
        print("\n".join("ERROR " + e for e in errors))
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
    for rel, path in sorted(listing(DEST).items()) if os.path.isdir(DEST) else []:
        if rel not in files and rel not in KEEP:
            plan.append(("delete", rel))
            if not args.check:
                os.remove(path)

    if not args.check:
        for d, _, _ in sorted(os.walk(DEST), key=lambda x: -len(x[0])):
            if not os.listdir(d):
                os.rmdir(d)
        pin = os.path.join(DEST, "UPSTREAM.md")
        if os.path.isfile(pin):
            text = open(pin, encoding="utf-8").read()
            marker = "Pinned fork commit: `"
            if marker in text:
                head, tail = text.split(marker, 1)
                text = head + marker + commit + "`" + tail.split("`", 1)[1]
                open(pin, "w", encoding="utf-8", newline="\n").write(text)

    counts = {}
    for kind, rel in plan:
        counts[kind] = counts.get(kind, 0) + 1
        if len(plan) <= 60:
            print("{0:7} {1}".format(kind, rel))
    size = sum(len(v) for v in files.values())
    print("fork {0} ({1}): {2} files, {3:.1f} MB; {4}".format(
        args.ref, commit[:7], len(files), size / 1e6, counts or "no changes"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
