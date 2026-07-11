#!/usr/bin/env python3
"""airules layer-purity checker.

Scans the layered distribution (core/, overlays/, project-template/) and reports
content that violates the purity contract of its layer: leaked credentials,
machine paths, domain names, stack terms in the generic core, hardcoded models,
unmarked xhigh reasoning defaults, missing UTF-8 BOM in script files, and
credentials echoed into console output.

Pure standard library, cross-platform, Python 3.9+.

Rule-level suppression: put the marker ``airules:allow <rule-id>`` on the same
line as an intentional example to exempt that line from that rule.
"""

import argparse
import json
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Layers that participate in the purity contract.
SCAN_LAYERS = ("core", "overlays", "project-template")

# Only these extensions are treated as text and scanned; everything else is
# skipped as binary/irrelevant.
TEXT_EXTENSIONS = (
    ".md",
    ".yaml",
    ".yml",
    ".py",
    ".ps1",
    ".json",
    ".toml",
    ".txt",
)

# Per-line marker that suppresses a single rule on that line.
ALLOW_MARKER = "airules:allow"

# The two files where model names are expected by design: the tier map and
# the per-model behavioral profiles rendered by the installer.
MODEL_MAP_REL = os.path.join("core", "channels", "model-map.yaml")
MODEL_PROFILES_REL = os.path.join("core", "channels", "model-profiles.md")

# Rule id for the file-level (not line-level) BOM check below.
PS1_BOM_RULE_ID = "ps1-bom"
UTF8_BOM = b"\xef\xbb\xbf"


# Each rule: id, compiled regex, severity, layers it applies to, description.
# ``layers`` uses the top-level directory name; the special value "*" means the
# whole repository (still excluding ci/fixtures in normal runs).
def _build_rules():
    raw = [
        # --- credentials: whole repo (minus fixtures) ---
        {
            "id": "creds-password",
            # `pass` is covered only in the `pass=value` env-file form: the
            # prose form "Pass: ..." is a common gate wording in the rules.
            # Values starting with $ or [ are variable/expression references
            # (e.g. `$Password = $null`), not hardcoded literals.
            "regex": r"(?i)(?:(?:password|пароль|passwd)\s*[=:]|\bpass\s*=)\s*[\"']?[^\s\"'{*$\[][^\s\"'{*]{2,}",
            "severity": "error",
            "layers": ("*",),
            "description": "Possible hardcoded password.",
        },
        {
            "id": "creds-p-flag",
            "regex": r'/P"[^*"{]',
            "severity": "error",
            "layers": ("*",),
            "description": "Possible /P\"...\" credential flag.",
        },
        {
            "id": "creds-token",
            "regex": r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*[\"']?[A-Za-z0-9_\-]{8,}",
            "severity": "error",
            "layers": ("*",),
            "description": "Possible hardcoded api key / token / secret.",
        },
        {
            "id": "creds-echo",
            "regex": r'(?i)(write-host|write-output|echo)[^\r\n]*\$(password|passwd|pass)\b',
            "severity": "error",
            "layers": ("*",),
            "description": "Password variable leaked into console output.",
        },
        {
            "id": "creds-echo",
            "regex": r'(?i)/P\W{0,3}\$\w*(password|pass)\w*',
            "severity": "error",
            "layers": ("*",),
            "description": "Password variable leaked via /P command-line flag.",
        },
        # --- machine paths: core + overlays ---
        # Three shapes: Windows drive roots that identify a concrete machine
        # (standard install locations like "Program Files" stay allowed), UNC
        # shares, and user-owned POSIX roots.
        {
            "id": "machine-paths",
            "regex": (
                r"(?i)(?:[A-Za-z]:[\\/](Work|Users|projects|bases|WS|repos|Temp|dev)\b"
                r"|\\\\[A-Za-z0-9_.$-]+\\[A-Za-z0-9_.$-]+"
                r"|(?<![\w./-])/(home|mnt)/)"
            ),
            "severity": "error",
            "layers": ("core", "overlays"),
            "description": "Absolute machine path.",
        },
        # --- domain names: core + overlays ---
        {
            "id": "domain-names",
            "regex": r"(\b(BKI|НБКИ|GUTDF|УниверсальнаяВыгрузка)\b|1c-rag-(bki|ka2)|СУТ_[А-Яа-яA-Za-z]|ГС_[А-Яа-яA-Za-z]|\b(КА2|KA2)\b)",
            "severity": "error",
            "layers": ("core", "overlays"),
            "description": "Concrete project / domain name.",
        },
        # --- stack terms in the generic core ---
        # Marker identifiers plus the softer 1C vocabulary that leaked from
        # donor material in the past (Configurator, posting, register,
        # attribute, tabular section, scheduled-job phrasing).
        {
            "id": "stack-in-core",
            "regex": (
                r"(?i)(?:\b(BSL|COMConnector|V83|СКД|БСП)\b"
                r"|1С:Предприятие|1C:Enterprise|managed forms?|tabular sections?"
                r"|конфигуратор\w*|проведени\w*|реквизит\w*"
                r"|табличн\w{0,4}\s+част\w*|регламентн\w{0,4}\s+задани\w*"
                r"|\bрегистр(?:ы|а|у|е|ом|ов|ам|ах|ами)?\b)"
            ),
            "severity": "error",
            "layers": ("core",),
            "description": "Domain/stack term inside generic core.",
        },
        # --- hardcoded model: core only, model-map.yaml excepted ---
        {
            "id": "model-hardcode",
            "regex": r"(?i)\bmodel\s*:\s*(opus|sonnet|haiku|gpt-|claude-|qwen|deepseek|glm)",
            "severity": "error",
            "layers": ("core",),
            "description": "Hardcoded model in core (belongs in channels/model-map.yaml).",
        },
        # --- xhigh default: core incl. model-map, unless marked as escalation ---
        {
            "id": "xhigh-default",
            "regex": r"xhigh",
            "severity": "error",
            "layers": ("core",),
            "description": "xhigh reasoning default without manual-escalation marker.",
        },
    ]
    # model-hardcode second flavour: bare opus/sonnet/haiku in core .md rules/agents.
    raw.append(
        {
            "id": "model-hardcode",
            "regex": r"(?i)\b(opus|sonnet|haiku)\b",
            "severity": "error",
            "layers": ("core",),
            "description": "Hardcoded model name in core markdown.",
            "md_only_dirs": (
                os.path.join("core", "rules"),
                os.path.join("core", "agents"),
            ),
        }
    )
    for rule in raw:
        rule["compiled"] = re.compile(rule["regex"])
    return raw


RULES = _build_rules()


def _rule_applies_to_path(rule, rel_path):
    """Return True if this rule should be evaluated for rel_path."""
    top = rel_path.replace("\\", "/").split("/", 1)[0]
    layers = rule["layers"]
    if "*" not in layers and top not in layers:
        return False

    # model-hardcode markdown flavour is scoped to specific dirs + .md only.
    md_dirs = rule.get("md_only_dirs")
    if md_dirs is not None:
        norm = rel_path.replace("\\", "/")
        if not norm.endswith(".md"):
            return False
        if not any(norm.startswith(d.replace("\\", "/") + "/") for d in md_dirs):
            return False
    return True


def _is_exception(rule, rel_path):
    """model-map.yaml and model-profiles.md are exempt from model-hardcode
    by design (see docs/LAYERS.md)."""
    norm = rel_path.replace("\\", "/")
    if rule["id"] == "model-hardcode" and norm in (
        MODEL_MAP_REL.replace("\\", "/"),
        MODEL_PROFILES_REL.replace("\\", "/"),
    ):
        return True
    return False


def _line_suppresses(line, rule_id):
    """Per-line airules:allow <rule-id> marker."""
    idx = line.find(ALLOW_MARKER)
    if idx == -1:
        return False
    tail = line[idx + len(ALLOW_MARKER):]
    return rule_id in tail.split()


def _placeholder_ok(fragment):
    """Placeholders {{...}} and *** are never credential violations.

    Checked against the matched fragment, not the whole line: a placeholder
    elsewhere on the line must not mask a real secret sitting next to it."""
    if "{{" in fragment and "}}" in fragment:
        return True
    if "***" in fragment:
        return True
    return False


def _xhigh_ok(line):
    """xhigh is allowed only if the line marks it as manual escalation."""
    low = line.lower()
    return ("escalation" in low) or ("эскалация" in low)


def read_text(path):
    """Read a file as utf-8 (BOM tolerated and stripped); None if undecodable."""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return handle.read()
    except (UnicodeDecodeError, OSError):
        return None


def check_line(rule, line, rel_path):
    """Return the matched fragment if this line violates the rule, else None."""
    if _line_suppresses(line, rule["id"]):
        return None
    match = rule["compiled"].search(line)
    if match is None:
        return None
    fragment = match.group(0)

    if rule["id"] in ("creds-password", "creds-token", "creds-p-flag"):
        if _placeholder_ok(fragment):
            return None
    if rule["id"] == "xhigh-default":
        if _xhigh_ok(line):
            return None
    return fragment


def scan_file(path, rel_path, rules):
    """Yield (rel_path, lineno, rule_id, fragment) for every violation."""
    text = read_text(path)
    if text is None:
        # A silently skipped file is a coverage hole (e.g. cp1251 on a
        # Russian-locale Windows box) — warn instead of pretending it passed.
        print(
            "airules: WARNING: {0}: not valid UTF-8 — skipped; re-encode to "
            "include it in the scan".format(rel_path.replace(os.sep, "/")),
            file=sys.stderr,
        )
        return
    lines = text.splitlines()
    for rule in rules:
        if not _rule_applies_to_path(rule, rel_path):
            continue
        if _is_exception(rule, rel_path):
            continue
        for lineno, line in enumerate(lines, start=1):
            fragment = check_line(rule, line, rel_path)
            if fragment is not None:
                yield (rel_path, lineno, rule["id"], fragment)


def check_ps1_bom(path, rel_path):
    """Whole-file check: every *.ps1 in the distribution layers must start
    with a UTF-8 BOM. Returns a single (rel_path, 1, rule_id, message) tuple
    or None. Not part of the line-oriented RULES list because it inspects raw
    bytes rather than decoded text lines."""
    norm = rel_path.replace("\\", "/")
    if not norm.endswith(".ps1"):
        return None
    top = norm.split("/", 1)[0]
    if top not in SCAN_LAYERS:
        return None
    try:
        with open(path, "rb") as handle:
            head = handle.read(3)
    except OSError:
        return None
    if head == UTF8_BOM:
        return None
    first_line = read_text(path)
    first_line = first_line.splitlines()[0] if first_line else ""
    if _line_suppresses(first_line, PS1_BOM_RULE_ID):
        return None
    return (rel_path, 1, PS1_BOM_RULE_ID, "missing UTF-8 BOM")


def _iter_text_files(base_dir):
    """Yield absolute paths of scannable text files under base_dir."""
    for root, _dirs, files in os.walk(base_dir):
        for name in files:
            if os.path.splitext(name)[1].lower() in TEXT_EXTENSIONS:
                yield os.path.join(root, name)


def collect_tree_files():
    """All scannable files in the working tree under the scan layers."""
    result = []
    for layer in SCAN_LAYERS:
        base = os.path.join(REPO_ROOT, layer)
        if os.path.isdir(base):
            result.extend(_iter_text_files(base))
    return result


def collect_staged_files():
    """Staged (ACM) files under the scan layers, absolute paths."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return []
    result = []
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        top = rel.split("/", 1)[0]
        if top not in SCAN_LAYERS:
            continue
        if os.path.splitext(rel)[1].lower() not in TEXT_EXTENSIONS:
            continue
        abs_path = os.path.join(REPO_ROOT, rel.replace("/", os.sep))
        if os.path.isfile(abs_path):
            result.append(abs_path)
    return result


def _report(violations):
    for rel_path, lineno, rule_id, fragment in violations:
        norm = rel_path.replace("\\", "/")
        print("{0}:{1} [{2}] {3}".format(norm, lineno, rule_id, fragment.strip()))


def run_scan(paths):
    """Scan the given absolute paths, print violations, return count."""
    violations = []
    for abs_path in paths:
        rel_path = os.path.relpath(abs_path, REPO_ROOT)
        violations.extend(scan_file(abs_path, rel_path, RULES))
        bom_hit = check_ps1_bom(abs_path, rel_path)
        if bom_hit is not None:
            violations.append(bom_hit)
    # Two flavours of the same rule id (creds-echo, model-hardcode) may match
    # one line; report each (path, line, rule) once.
    seen = set()
    unique = []
    for violation in violations:
        key = violation[:3]
        if key not in seen:
            seen.add(key)
            unique.append(violation)
    _report(unique)
    return len(unique)


def run_selftest():
    """Run patterns over ci/fixtures and compare with expected.json."""
    fixtures_dir = os.path.join(REPO_ROOT, "ci", "fixtures")
    expected_path = os.path.join(fixtures_dir, "expected.json")
    expected = json.loads(read_text(expected_path))

    # Collect actual (rel_path_from_fixtures, rule_id) hits per file.
    actual = {}
    for abs_path in _iter_text_files(fixtures_dir):
        rel_from_fixtures = os.path.relpath(abs_path, fixtures_dir).replace(os.sep, "/")
        if rel_from_fixtures == "expected.json":
            continue
        # Rules resolve their layer from the top-level dir, so during selftest we
        # feed the path relative to fixtures/ — its first segment is the layer.
        rel_for_rules = rel_from_fixtures
        hits = set()
        for item in scan_file(abs_path, rel_for_rules, RULES):
            hits.add(item[2])
        bom_hit = check_ps1_bom(abs_path, rel_for_rules)
        if bom_hit is not None:
            hits.add(bom_hit[2])
        actual[rel_from_fixtures] = hits

    all_pass = True

    # 1) Each expected (file -> [rule-ids]) must fire.
    for rel_file, rule_ids in expected.get("dirty", {}).items():
        found = actual.get(rel_file, set())
        for rule_id in rule_ids:
            ok = rule_id in found
            all_pass = all_pass and ok
            status = "PASS" if ok else "FAIL"
            print("{0}  {1} expects [{2}]".format(status, rel_file, rule_id))

    # 2) Clean files must produce zero violations.
    for rel_file in expected.get("clean", []):
        found = actual.get(rel_file, set())
        ok = len(found) == 0
        all_pass = all_pass and ok
        status = "PASS" if ok else "FAIL"
        detail = "" if ok else " unexpected {0}".format(sorted(found))
        print("{0}  {1} clean{2}".format(status, rel_file, detail))

    print("SELFTEST {0}".format("PASS" if all_pass else "FAIL"))
    return 0 if all_pass else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="airules layer-purity checker")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true", help="check only staged files")
    group.add_argument("--selftest", action="store_true", help="run fixture selftest")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    if args.staged:
        paths = collect_staged_files()
    else:
        paths = collect_tree_files()

    count = run_scan(paths)
    if count:
        print("airules: {0} layer-purity violation(s) found.".format(count), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
