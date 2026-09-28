#!/usr/bin/env python3
"""Sync `overlays/1c/skills/1c-metadata-manage` from the comol/ai_rules_1c upstream.

Maintainer tool, not installed. The upstream vendors Nikolay Shirokov's
cc-1c-skills scripts (MIT) nearly verbatim; we take them the same way and keep
everything of our own in three places that a sync never overwrites:

* `KEEP` — our files (SKILL.md, NOTICE.md, the wrapper `_common/Invoke-1CEdit.ps1`
  that carries the airules script contract, a few docs and tools of our own);
* `GATED` — the mutating tools. Each gets the same short gate inserted after its
  param block: it refuses to run unless launched by the wrapper, so DryRun by
  default and `-Apply` to write hold for every call path;
* `PATCHES` — local fixes on top of upstream, applied as exact-anchor
  replacements. An anchor that no longer matches fails the sync: either
  upstream fixed it (drop the patch) or changed it (redo the patch).

Every upstream `.ps1` must be classified as GATED or READONLY; an unknown one
fails the sync, so a new upstream tool cannot slip in ungated.

Usage:
    python ci/sync_metadata_manage.py [--upstream D:/AI_Projects/_ref/ai_rules_1c] [--check]

`--check` reports what would change without writing.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(REPO, "overlays", "1c", "skills", "1c-metadata-manage")
SKILL_IN_UPSTREAM = os.path.join("content", "skills", "1c-metadata-manage")
DEFAULT_UPSTREAM = r"D:\AI_Projects\_ref\ai_rules_1c"

# Ours: never overwritten, never deleted by a sync.
KEEP = {
    "SKILL.md",
    "NOTICE.md",
    "UPSTREAM.md",
    "docs/ssl-patterns.md",
    "docs/edit-preview.md",          # ours: the wrapper's contract differs from upstream's
    "tools/_common/Invoke-1CEdit.ps1",
    "tools/1c-form-scaffold/scripts/add-form.ps1",
}

# Upstream files we do not take.
SKIP = {
    "docs/CHANGELOG.md",            # upstream's own history; UPSTREAM.md pins the commit
    "docs/v8unpack-cf.md",          # pointer to an upstream skill; ours is rules/v8unpack-source-structure.md
    "tools/_common/Invoke-1CEdit.ps1",  # replaced by ours (different defaults)
}
SKIP_SUFFIXES = (".py",)            # Python ports: not taken (PS tools do not call them)

# Mutating tools: gated. Values say how the wrapper drives them.
#   file     - edits the dump; DryRun = run, diff, restore
#   external - launches the platform / touches a server; DryRun = print the plan
#   native   - has its own -DryRun; the wrapper passes it through
GATED = {
    "cf-edit": "file", "cf-init": "file",
    "cfe-borrow": "file", "cfe-init": "file", "cfe-patch-method": "file",
    "form-add": "file", "form-compile": "file", "form-edit": "file",
    "remove-form": "native",
    "add-help": "file",
    "interface-edit": "file",
    "meta-compile": "file", "meta-edit": "file", "meta-remove": "native",
    "mxl-compile": "file",
    "role-compile": "file",
    "skd-compile": "file", "skd-edit": "file",
    "subsystem-compile": "file", "subsystem-edit": "file",
    "add-template": "file", "remove-template": "native",
    "support-edit": "file",
    "xdto-compile": "file", "xdto-edit": "file",
    "uuid-check": "file",           # read-only unless -Fix: gate is conditional
    "epf-scaffold/init": "file", "erf-scaffold/init": "file",
    "db-create": "external", "db-dump-cf": "external", "db-dump-dt": "external",
    "db-dump-xml": "external", "db-load-cf": "external", "db-load-dt": "external",
    "db-load-git": "native", "db-load-xml": "external", "db-run": "external",
    "db-update": "external", "install-files-update": "external",
    "epf-build": "external", "epf-dump": "external", "stub-db-create": "external",
    "web-publish": "external", "web-stop": "external", "web-unpublish": "native",
}
# Read-only or pure export into a new file: not gated.
READONLY = {
    "cf-info", "cf-validate", "dump-validate", "cfe-diff", "cfe-validate",
    "epf-validate", "form-info", "form-validate", "interface-validate",
    "meta-info", "meta-validate", "mxl-decompile", "mxl-info", "mxl-validate",
    "role-info", "role-validate", "skd-decompile", "skd-info", "skd-validate",
    "subsystem-info", "subsystem-validate", "xdto-decompile", "xdto-info",
    "xdto-validate", "web-info",
    "_common/DevEnv", "_common/MetadataAddress",
}
CONDITIONAL_GATE = {"uuid-check": "$Fix"}

GATE_MARK = "AIRULES_1C_GATE"
GATE = """
# airules gate (inserted by ci/sync_metadata_manage.py): this tool writes, so it
# runs only through _common/Invoke-1CEdit.ps1 - DryRun by default, -Apply to write.
if ({cond}$env:AIRULES_1C_GATE -ne '1') {{
\t[Console]::Error.WriteLine("airules: {name} writes - run it as: tools/_common/Invoke-1CEdit.ps1 -Tool {name} <same arguments>  (DryRun by default, -Apply to write)")
\texit 3
}}
"""

# Local fixes on top of upstream: (path, old, new). Exact, single occurrence,
# on LF-normalized text. Reported upstream: comol/ai_rules_1c#28, #29.
def _validator_patches(rel, name, call, tail):
    """Sibling validator: real path (same scripts/ folder), FAIL when missing, exit code propagated."""
    old = (
        'if (-not $NoValidate) {\n'
        '\t$validateScript = Join-Path (Join-Path $PSScriptRoot "..\\..\\' + name + '") "scripts\\' + name + '.ps1"\n'
        '\t$validateScript = [System.IO.Path]::GetFullPath($validateScript)\n'
        '\tif (Test-Path $validateScript) {\n'
        '\t\tWrite-Host ""\n'
        '\t\tWrite-Host "--- Running ' + name + ' ---"\n'
        '\t\t' + call + '\n'
        '\t}\n'
        '}\n')
    new = (
        '# Local: the validator sits in this scripts/ folder (upstream looked two levels\n'
        '# up and silently skipped); a missing validator fails, its exit code propagates.\n'
        '$script:validateExit = 0\n'
        'if (-not $NoValidate) {\n'
        '\t$validateScript = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "' + name + '.ps1"))\n'
        '\tif (Test-Path $validateScript) {\n'
        '\t\tWrite-Host ""\n'
        '\t\tWrite-Host "--- Running ' + name + ' ---"\n'
        '\t\t' + call + '\n'
        '\t\tif ($LASTEXITCODE -ne 0) {\n'
        '\t\t\tWrite-Host "[FAIL] ' + name + ' reported errors (exit $LASTEXITCODE) - the written result is not valid" -ForegroundColor Red\n'
        '\t\t\t$script:validateExit = 1\n'
        '\t\t}\n'
        '\t} else {\n'
        '\t\tWrite-Host "[FAIL] ' + name + ' not found at: $validateScript - the result was written but NOT validated" -ForegroundColor Red\n'
        '\t\t$script:validateExit = 1\n'
        '\t}\n'
        '}\n')
    return [(rel, old, new), (rel, tail + "exit 0\n", tail + "exit $script:validateExit\n")]


_SCRIPTS = "tools/{0}/scripts/{1}.ps1"
PATCHES = (
    _validator_patches(
        _SCRIPTS.format("1c-cf-manage", "cf-edit"), "cf-validate",
        "& powershell.exe -NoProfile -File $validateScript -ConfigPath $resolvedPath",
        'Write-Host "  Modified:      $($script:modifyCount)"\n')
    + _validator_patches(
        _SCRIPTS.format("1c-interface-manage", "interface-edit"), "interface-validate",
        "& powershell.exe -NoProfile -File $validateScript -CIPath $resolvedPath",
        'Write-Host "  Modified: $($script:modifyCount)"\n')
    + _validator_patches(
        _SCRIPTS.format("1c-subsystem-manage", "subsystem-compile"), "subsystem-validate",
        "& powershell.exe -NoProfile -File $validateScript -SubsystemPath $targetXml",
        'Write-Host "  File:     $targetXml"\n')
    + _validator_patches(
        _SCRIPTS.format("1c-subsystem-manage", "subsystem-edit"), "subsystem-validate",
        "& powershell.exe -NoProfile -File $validateScript -SubsystemPath $resolvedPath",
        'Write-Host "  Modified:  $($script:modifyCount)"\n')
    + [
        # xdto-edit: siblings live in the same scripts/ folder (upstream: every
        # operation but rename/synonym/comment refused as "skill incomplete").
        (_SCRIPTS.format("1c-xdto-manage", "xdto-edit"),
         '$decompileScript = Join-Path (Join-Path $PSScriptRoot "..\\..\\xdto-decompile") "scripts\\xdto-decompile.ps1"\n'
         '$compileScript   = Join-Path (Join-Path $PSScriptRoot "..\\..\\xdto-compile") "scripts\\xdto-compile.ps1"\n'
         '$validateScript  = Join-Path (Join-Path $PSScriptRoot "..\\..\\xdto-validate") "scripts\\xdto-validate.ps1"\n',
         '# Local: siblings live in this scripts/ folder (upstream path pointed two levels up).\n'
         '$decompileScript = Join-Path $PSScriptRoot "xdto-decompile.ps1"\n'
         '$compileScript   = Join-Path $PSScriptRoot "xdto-compile.ps1"\n'
         '$validateScript  = Join-Path $PSScriptRoot "xdto-validate.ps1"\n'),
        # Event-handler suffixes: platform names, checked against a real dump.
        (_SCRIPTS.format("1c-form-edit", "form-edit"),
         '"OnEndEdit" = "ПриОкончанииРедактирования"',
         '"OnEditEnd" = "ПриОкончанииРедактирования"'),
        (_SCRIPTS.format("1c-form-edit", "form-edit"),
         '"Selection" = "ВыборСтроки"', '"Selection" = "Выбор"'),
        (_SCRIPTS.format("1c-form-edit", "form-edit"),
         '"Drop" = "Помещение"', '"DragEnd" = "ОкончаниеПеретаскивания"'),
        (_SCRIPTS.format("1c-form-compile", "form-compile"),
         '"Selection"            = "ВыборСтроки"', '"Selection"            = "Выбор"'),
        (_SCRIPTS.format("1c-form-compile", "form-compile"),
         '"Drop"                 = "Помещение"', '"DragEnd"              = "ОкончаниеПеретаскивания"'),
        ("tools/1c-form-compile/form-dsl-spec.md",
         "| `Selection` | `ВыборСтроки` |",
         "| `Selection` | `Выбор` |\n| `DragEnd` | `ОкончаниеПеретаскивания` |"),
        # meta-edit refusal names a direct call (gated here) and a Python port we do not ship.
        (_SCRIPTS.format("1c-meta-edit", "meta-edit"),
         '\t[Console]::Error.WriteLine("          Windows:     powershell -NoProfile -File `"$formAddPs1`" -ObjectPath `"$resolvedPath`" -FormName ИмяФормы -Purpose Object -SetDefault")\n'
         '\t[Console]::Error.WriteLine("          Linux/macOS: python3 `"$formAddPy`" -ObjectPath `"$resolvedPath`" -FormName ИмяФормы -Purpose Object -SetDefault")\n',
         '\t[Console]::Error.WriteLine("          tools/_common/Invoke-1CEdit.ps1 -Tool form-add -ObjectPath `"$resolvedPath`" -FormName ИмяФормы -Purpose Object -SetDefault  (DryRun; -Apply to write; runs $formAddPs1)")\n'),
    ]
)


DOC_NOTE = (
    "> **airules:** writing tools run through `tools/_common/Invoke-1CEdit.ps1 -Tool <name>`."
    " Every call below is a **DryRun** (the diff or the plan is printed, nothing is written)"
    " until `-Apply` is added; a writing script called directly exits 3. Passwords go as"
    " `-PasswordEnv <VAR>`, never `-Password`. Details: `docs/edit-preview.md`.\n")


TEST_NAME = "metadata-tools-regression.ps1"
TEST_PATCHES = [
    ("$RepoRoot    = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent\n",
     "$RepoRoot    = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent\n"
     "# airules: the tests drive the tools directly - open the wrapper gate for this process.\n"
     "$env:AIRULES_1C_GATE = '1'\n"),
    ("$ToolsDir    = Join-Path $RepoRoot 'content\\skills\\1c-metadata-manage\\tools'\n",
     "$ToolsDir    = Join-Path $RepoRoot 'overlays\\1c\\skills\\1c-metadata-manage\\tools'\n"),
]
# Upstream's wrapper cases test upstream's wrapper (apply by default, refuse a dirty
# tree); ours are in ci/metadata-tools/wrapper-cases.ps1. Cut [start, end).
TEST_REGION = (
    "Register-Case 'Invoke-1CEdit: -Preview restores the tree byte-for-byte (copy backend)' {",
    "Register-Case 'support: meta-edit refuses add-template before any mutation' {",
    "# airules: our wrapper's cases replace upstream's (different contract).\n"
    ". (Join-Path $PSScriptRoot 'wrapper-cases.ps1')\n\n",
)


# Upstream rule name -> our rule that owns the same ground (rules/<name>.md in the target).
RULE_MAP = {
    "designer-batch-checks": "getconfigfiles",    # Step 3: the three-signal verdict
    "extension-workspace": "extension-patterns",
    "query-design": "dev-standards-architecture",
    "dev-standards-env": "dev-standards-core",    # §1: .dev.env
}
# Exact phrases pointing at upstream-only material.
DOC_REFS = [
    ("server not exposed → `content/rules/help-corpus-retrieval.md`",
     "not in this project's MCP profile → skip it"),
    ("`content/commands/update1cbase.md → Update retry loop`",
     "the deploy runbook (`commands/deploy-and-test.md`)"),
    ("Slash command: `/check-uuid` (source: `content/commands/check-uuid.md`).",
     "Run it as `tools/_common/Invoke-1CEdit.ps1 -Tool uuid-check` (`-Fix` writes, so it needs `-Apply`)."),
    ("`content/skills/1c-ui-regression/SKILL.md`", "the tester role (`1c-tester`)"),
]
OVERLAY_RULES = set(
    f[:-3] for f in os.listdir(os.path.join(REPO, "overlays", "1c", "rules")) if f.endswith(".md"))


def rewrite_doc(text):
    """Point `-File .../<writing tool>.ps1` calls at the wrapper and add the DryRun note."""
    import re

    def repl(m):
        folder, name = m.group(3), m.group(4)
        key = name if name != "init" else folder[3:] + "/init"
        if key not in GATED:
            return m.group(0)
        return "{0}{1}tools/_common/Invoke-1CEdit.ps1{2} -Tool {3}".format(
            m.group(1), m.group(2), m.group(5), key)

    text = re.sub(r'(-File\s+"?)(\S*?)tools/(1c-[a-z-]+)/scripts/([a-z-]+)\.ps1("?)', repl, text)
    # The wrapper refuses a literal password: examples and parameter tables say -PasswordEnv.
    text = re.sub(r'-Password "[^"]*"', '-PasswordEnv IB_PASSWORD', text)
    text = re.sub(r'-Password <[a-z]+>', '-PasswordEnv <VAR>', text)
    text = text.replace("`-Password`", "`-PasswordEnv <VAR>`")
    text = text.replace('/P"<password>"', '/P"***"')
    # Machine paths in examples (repository rule machine-paths).
    text = re.sub(r'(?i)C:\\Bases', '<bases-dir>', text)
    # Upstream rule / command references -> our installed rules, or a neutral pointer.
    for old, new in DOC_REFS:
        text = text.replace(old, new)
    text = re.sub(r'content/rules/([a-z0-9-]+)\.md',
                  lambda m: "rules/{0}.md".format(RULE_MAP.get(m.group(1), m.group(1))), text)
    text = re.sub(r'`?standards\(name="([a-z0-9-]+)"\)`?',
                  lambda m: ("`rules/{0}.md`".format(m.group(1)) if m.group(1) in OVERLAY_RULES
                             else m.group(0)), text)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines[i + 1:i + 1] = ["", DOC_NOTE.rstrip("\n")]
            break
    return "\n".join(lines)


def tool_key(rel):
    """`tools/1c-meta-edit/scripts/meta-edit.ps1` -> `meta-edit`; init scripts keep their folder."""
    parts = rel.split("/")
    base = parts[-1][:-4]
    if parts[1] == "_common":
        return "_common/" + base
    if base == "init":
        return parts[1][3:] + "/init"   # 1c-epf-scaffold -> epf-scaffold/init
    return base


def listing(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root).replace("\\", "/")] = p
    return out


def param_block_end(path):
    """(line, column) right after the script's param block, 1-based as the PS parser gives it."""
    ps = ("$e=$null;$a=[System.Management.Automation.Language.Parser]::ParseFile("
          "'{0}',[ref]$null,[ref]$e);if($a.ParamBlock){{'{{0}} {{1}}' -f "
          "$a.ParamBlock.Extent.EndLineNumber,$a.ParamBlock.Extent.EndColumnNumber}}else{{'-1 -1'}}"
          ).format(path.replace("'", "''"))
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout.strip().splitlines()[-1]
    line, col = (int(x) for x in out.split())
    return line, col


def offset_of(text, line, col):
    """Offset in LF-normalized text for a 1-based (line, column)."""
    if line < 1:
        return -1
    lines = text.split("\n")
    return sum(len(l) + 1 for l in lines[:line - 1]) + col - 1


def to_ps1_bytes(text):
    """Repository rule ps1-bom: UTF-8 with BOM, CRLF."""
    text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    return b"\xef\xbb\xbf" + text.encode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", default=DEFAULT_UPSTREAM)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    src_root = os.path.join(args.upstream, SKILL_IN_UPSTREAM)
    commit = subprocess.run(["git", "-C", args.upstream, "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    up = listing(src_root)
    ours = listing(DEST)
    errors, plan = [], []

    wanted = {}
    for rel, path in up.items():
        if rel in SKIP or rel.endswith(SKIP_SUFFIXES) or rel in KEEP:
            continue
        wanted[rel] = path
        if rel.endswith(".ps1"):
            key = tool_key(rel)
            if key not in GATED and key not in READONLY:
                errors.append("unclassified upstream tool: {0} ({1}) - add it to GATED or READONLY".format(key, rel))

    for key in list(GATED) + list(READONLY):
        if not any(r.endswith(".ps1") and tool_key(r) == key for r in wanted):
            errors.append("classified tool not found upstream: " + key)

    if errors:
        print("\n".join("ERROR " + e for e in errors))
        return 1

    # Build the new content of each file in memory.
    result = {}
    for rel, path in sorted(wanted.items()):
        raw = open(path, "rb").read()
        if rel.endswith(".ps1"):
            text = raw.decode("utf-8-sig").replace("\r\n", "\n")
            key = tool_key(rel)
            if key in GATED:
                end = offset_of(text, *param_block_end(path))
                if end < 0:
                    errors.append("no param block to gate: " + rel)
                    continue
                cond = ""
                if key in CONDITIONAL_GATE:
                    cond = CONDITIONAL_GATE[key] + " -and "
                if text[end - 1] != ")":
                    errors.append("param block offset does not land on ')': " + rel)
                    continue
                text = text[:end] + "\n" + GATE.format(cond=cond, name=key) + text[end:]
            result[rel] = text
        elif rel.endswith(".md"):
            result[rel] = rewrite_doc(raw.decode("utf-8-sig").replace("\r\n", "\n")).encode("utf-8")
        else:
            result[rel] = raw

    for rel, old, new in PATCHES:
        if rel not in result:
            errors.append("patch target missing: " + rel)
            continue
        body = result[rel]
        is_text = isinstance(body, str)
        text = body if is_text else body.decode("utf-8-sig").replace("\r\n", "\n")
        n = text.count(old)
        if n != 1:
            errors.append("patch anchor matched {0}x in {1}: {2!r}".format(n, rel, old[:70]))
            continue
        text = text.replace(old, new)
        result[rel] = text if is_text else text.encode("utf-8")

    if errors:
        print("\n".join("ERROR " + e for e in errors))
        return 1

    # Write / delete.
    for rel, content in result.items():
        data = to_ps1_bytes(content) if rel.endswith(".ps1") else content
        dst = os.path.join(DEST, rel.replace("/", os.sep))
        old = open(dst, "rb").read() if os.path.isfile(dst) else None
        if old != data:
            plan.append(("new" if old is None else "update", rel))
            if not args.check:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, "wb").write(data)
    for rel in sorted(set(ours) - set(result) - KEEP):
        plan.append(("delete", rel))
        if not args.check:
            os.remove(ours[rel])

    # Upstream regression test + fixtures -> ci/metadata-tools/ (maintainer CI, not installed).
    test_src = os.path.join(args.upstream, "tools", "tests")
    test_dst = os.path.join(REPO, "ci", "metadata-tools")
    test = open(os.path.join(test_src, TEST_NAME), "rb").read().decode("utf-8-sig").replace("\r\n", "\n")
    for old, new in TEST_PATCHES:
        if test.count(old) != 1:
            print("ERROR test patch anchor matched {0}x: {1!r}".format(test.count(old), old[:70]))
            return 1
        test = test.replace(old, new)
    start, end, insert = TEST_REGION
    if test.count(start) != 1 or test.count(end) != 1 or test.index(start) > test.index(end):
        print("ERROR test region anchors moved: " + start[:60])
        return 1
    test = test[:test.index(start)] + insert + test[test.index(end):]
    test_files = {TEST_NAME: to_ps1_bytes(test)}
    fixtures = os.path.join(test_src, "fixtures")
    for rel, path in listing(fixtures).items():
        test_files["fixtures/" + rel] = open(path, "rb").read()
    for rel, data in test_files.items():
        dst = os.path.join(test_dst, rel.replace("/", os.sep))
        old = open(dst, "rb").read() if os.path.isfile(dst) else None
        if old != data:
            plan.append(("new" if old is None else "update", "ci/metadata-tools/" + rel))
            if not args.check:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, "wb").write(data)

    if not args.check:
        for d, dirs, fs in os.walk(DEST, topdown=False):
            if not os.listdir(d):
                os.rmdir(d)
        pin = os.path.join(DEST, "UPSTREAM.md")
        text = open(pin, encoding="utf-8").read() if os.path.isfile(pin) else ""
        marker = "Pinned upstream commit: `"
        if marker in text:
            head, tail = text.split(marker, 1)
            text = head + marker + commit + "`" + tail.split("`", 1)[1]
            open(pin, "w", encoding="utf-8", newline="\n").write(text)

    counts = {}
    for kind, _ in plan:
        counts[kind] = counts.get(kind, 0) + 1
    for kind, rel in plan:
        print("{0:7} {1}".format(kind, rel))
    print("upstream {0}: {1}".format(commit[:7], json.dumps(counts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
