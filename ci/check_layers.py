#!/usr/bin/env python3
"""airules layer-purity checker.

Scans the layered distribution (core/, overlays/, project-template/) and reports
content that violates the purity contract of its layer: leaked credentials,
machine paths, domain names, stack terms in the generic core, hardcoded models,
unmarked max-effort defaults, retired self-verification wording, missing UTF-8
BOM in script files, credentials echoed into console output,
distribution-only paths inside installable files, rule files that do not
declare their genre (``kind``), and rules nothing refers to.

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
MODEL_MAP_REL = os.path.join("core", "install", "model-map.yaml")
MODEL_PROFILES_REL = os.path.join("core", "install", "model-profiles.md")

# Rule id for the file-level (not line-level) BOM check below.
PS1_BOM_RULE_ID = "ps1-bom"
UTF8_BOM = b"\xef\xbb\xbf"

# Rule id and vocabulary for the frontmatter genre check below.
RULE_KIND_RULE_ID = "rule-kind"
VALID_KINDS = ("invariant", "case", "recipe", "process", "router")
KIND_LINE_RE = re.compile(r"^\s*kind\s*:\s*(\S+)\s*$")

# Rule ids whose lines are cleared by a manual-escalation marker.
ESCALATION_RULE_ID = "max-default"


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
            "regex": (
                r"(?i)\bmodel\s*:\s*"
                r"(opus|sonnet|haiku|fable|mythos|gpt-|claude-|qwen|deepseek|glm)"
            ),
            "severity": "error",
            "layers": ("core",),
            "description": "Hardcoded model in core (belongs in install/model-map.yaml).",
        },
        # --- max effort default: core incl. model-map, unless marked as escalation ---
        # The guard sits on the channel's TOP effort step, not on xhigh: xhigh is
        # a legitimate default for planning and heavy implementation, while max
        # costs more for a worse result and is only ever a manual escalation.
        {
            "id": "max-default",
            "regex": r"(?i)\bmax\b",
            "severity": "error",
            "layers": ("core",),
            "description": "Top effort step (max) used without a manual-escalation marker.",
        },
        # --- distribution-only paths in installable files ---
        # Rules and overlay content install FLAT into the target (rules/,
        # tools/, .claude/skills/ ...), so references like core/rules/... or
        # overlays/<stack>/... resolve only inside this repository and break
        # after install. Install-time artifacts (core/install, the role
        # registry, layer READMEs) are exempt via _is_installable_path.
        {
            "id": "install-path",
            "regex": r"(?:\b(?:core|overlays)/[A-Za-z0-9_.\-]+/|\.claude/rules/)",
            "severity": "error",
            "layers": ("core", "overlays", "project-template"),
            "description": "Distribution-only path in an installable file (breaks after flat install).",
            "install_only": True,
        },
        # --- retired self-verification wording: core and overlays ---
        # Removed in 0.4.0: the model verifies its own work without being told,
        # and these phrasings stack with that behavior at pure extra cost.
        # Instrumental gates (syntax, static analysis, validators) are NOT this
        # rule's target — they never phrase themselves this way.
        # Scope widened 2026-08-14: the reason is stack-independent, and the
        # overlay had kept a self-review cycle that the core had already
        # retired. The "internal review" phrasings are part of the same family
        # and were missing from the pattern, which is why nothing caught it.
        {
            "id": "stale-verification",
            "regex": (
                r"(?i)(?:\bdouble[-\s]check\b|\bre-verify\b|\bre-read your\b"
                r"|\bproofread (?:your|the) own\b"
                r"|\b(?:verification|verifying|re-check(?:ing)?) subagent\b"
                r"|\bsubagent (?:for|to) (?:verify|verification|double)"
                r"|\binternal (?:code )?review\b"
                r"|внутренн\w+ ревью"
                r"|двойная проверка|перепроверь\b)"
            ),
            "severity": "error",
            "layers": ("core", "overlays"),
            "description": "Retired self-verification wording (see docs/LAYERS.md).",
        },
    ]
    # model-hardcode second flavour: bare opus/sonnet/haiku in core .md rules/agents.
    raw.append(
        {
            "id": "model-hardcode",
            "regex": r"(?i)\b(opus|sonnet|haiku|fable|mythos)\b",
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


def _is_installable_path(rel_path):
    """Files that are copied or rendered into target projects. core/install,
    the registry/template files consumed only at install time, and layer-level
    READMEs stay distribution-internal and may reference repository paths."""
    norm = rel_path.replace("\\", "/")
    parts = norm.split("/")
    top = parts[0]
    if top == "project-template":
        return not (len(parts) == 2 and parts[1] == "README.md")
    if top == "core":
        if len(parts) < 3:
            return False
        second = parts[1]
        if second == "install":
            return False
        if second == "agents":
            return len(parts) >= 4 and parts[2] == "roles"
        return second in ("rules", "templates", "skills", "commands", "hooks")
    if top == "overlays":
        return not (len(parts) == 3 and parts[2] == "README.md")
    return False


def _rule_applies_to_path(rule, rel_path):
    """Return True if this rule should be evaluated for rel_path."""
    top = rel_path.replace("\\", "/").split("/", 1)[0]
    layers = rule["layers"]
    if "*" not in layers and top not in layers:
        return False

    if rule.get("install_only") and not _is_installable_path(rel_path):
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


def _escalation_ok(line):
    """The top effort step is allowed only if the line marks it as a manual
    escalation."""
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
    if rule["id"] == ESCALATION_RULE_ID:
        if _escalation_ok(line):
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


def _is_rule_file(rel_path):
    """True for installable rule bodies: core/rules/<name>.md and
    overlays/<stack>/rules/<name>.md. Layer READMEs and everything outside a
    rules/ directory are not rules."""
    parts = rel_path.replace("\\", "/").split("/")
    if not parts[-1].endswith(".md"):
        return False
    if parts[0] == "core":
        return len(parts) == 3 and parts[1] == "rules"
    if parts[0] == "overlays":
        return len(parts) == 4 and parts[2] == "rules"
    return False


def check_rule_kind(path, rel_path):
    """Whole-file check: every rule declares its genre in the frontmatter.

    ``kind`` decides the delivery channel — only ``invariant`` files are wired
    into the path-matching hook, the rest stay on the lazy Rule Index — so a
    missing or unknown value silently drops a rule out of the routing it was
    written for. Returns a single (rel_path, lineno, rule_id, message) tuple or
    None. Not part of the line-oriented RULES list because the answer depends on
    the whole frontmatter block, not on one line."""
    if not _is_rule_file(rel_path):
        return None
    text = read_text(path)
    if text is None:
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return (rel_path, 1, RULE_KIND_RULE_ID, "missing frontmatter")

    kind = None
    kind_lineno = 1
    close = None
    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == "---":
            close = index
            break
        if _line_suppresses(line, RULE_KIND_RULE_ID):
            return None
        match = KIND_LINE_RE.match(line)
        if match is not None:
            kind = match.group(1).strip("\"'")
            kind_lineno = index + 1
    if close is None:
        return (rel_path, 1, RULE_KIND_RULE_ID, "unterminated frontmatter")
    if kind is None:
        return (rel_path, 1, RULE_KIND_RULE_ID, "missing kind")
    if kind not in VALID_KINDS:
        return (
            rel_path,
            kind_lineno,
            RULE_KIND_RULE_ID,
            "unknown kind '{0}' (expected one of: {1})".format(
                kind, ", ".join(VALID_KINDS)
            ),
        )
    return None


RULE_ORPHAN_RULE_ID = "rule-orphan"


def _rule_stems(base_dir):
    """{stem: rel_path} for every rule body under the scanned layers."""
    found = {}
    for layer in SCAN_LAYERS:
        for base, _dirs, files in os.walk(os.path.join(base_dir, layer)):
            rel_base = os.path.relpath(base, base_dir).replace("\\", "/")
            if not rel_base.endswith("/rules"):
                continue
            for name in files:
                if name.endswith(".md"):
                    found[name[:-3]] = rel_base + "/" + name
    return found


def collect_rule_orphans(base_dir):
    """Repository-level check: every rule is referenced from somewhere.

    A rule nobody points at is loaded only if the reader already knows it
    exists — which, for a lazily read rule set, means it is not loaded at all.
    The failure is silent: the file is present, passes every other check, and
    is never read. Two of these were found by hand before this check existed.

    Not part of the per-file rules because the answer depends on the whole
    tree, not on one file. Returns a list of (rel_path, lineno, id, message).
    """
    stems = _rule_stems(base_dir)
    if not stems:
        return []
    patterns = {
        stem: re.compile(r"(?<![\w-])" + re.escape(stem) + r"(?![\w-])")
        for stem in stems
    }
    referenced = set()
    for layer in SCAN_LAYERS:
        for path in _iter_text_files(os.path.join(base_dir, layer)):
            rel = os.path.relpath(path, base_dir).replace("\\", "/")
            text = read_text(path)
            if text is None:
                continue
            for stem, pattern in patterns.items():
                if stem in referenced or rel == stems[stem]:
                    continue  # a rule naming itself proves nothing
                if pattern.search(text):
                    referenced.add(stem)
    return [
        (stems[stem], 1, RULE_ORPHAN_RULE_ID, "no rule, agent or template refers to it")
        for stem in sorted(set(stems) - referenced)
    ]


RULES_MAP_RULE_ID = "rules-map"


def collect_map_defects(base_dir):
    """Repository-level check: every overlay's hook map agrees with its rules.

    Delegated to the shipped hook's own ``--check-map`` rather than reimplemented
    here, so the distribution's CI and the installer run the same code. A second
    implementation would be free to drift, and the whole point of the check is
    that a map and the rules it points at drift silently.

    Returns a list of (rel_path, lineno, id, message).
    """
    script = os.path.join(base_dir, "core", "hooks", "rule-inject.py")
    if not os.path.isfile(script):
        return []
    overlays_dir = os.path.join(base_dir, "overlays")
    if not os.path.isdir(overlays_dir):
        return []

    defects = []
    for stack in sorted(os.listdir(overlays_dir)):
        root = os.path.join(overlays_dir, stack)
        map_dir = os.path.join(root, "hooks")
        if not os.path.isfile(os.path.join(map_dir, "rules-map.json")):
            continue  # an overlay without a map simply installs without the hook
        rel = "overlays/{0}/hooks/rules-map.json".format(stack)
        try:
            proc = subprocess.run(
                [sys.executable, script, "--check-map", root, map_dir],
                cwd=base_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except OSError as error:
            defects.append((rel, 1, RULES_MAP_RULE_ID, "cannot run --check-map: {0}".format(error)))
            continue
        if proc.returncode == 0:
            continue
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if line and not line.startswith("карта:"):
                defects.append((rel, 1, RULES_MAP_RULE_ID, line))
        if not defects:
            defects.append((rel, 1, RULES_MAP_RULE_ID, "--check-map failed without output"))
    return defects


INJECTION_RULE_ID = "hook-injection"


def collect_injection_failures(base_dir):
    """Repository-level check: what the hook injects for a given path.

    ``--check-map`` proves the map is consistent with the rules; it says nothing
    about whether a mask actually catches the path it was written for. A mask
    that catches nothing passes every other gate — valid map, rule present, no
    reminder delivered. Delegated to its own script because the answer requires
    running the hook as a real process (see that file for why).

    Returns a list of (rel_path, lineno, id, message).
    """
    script = os.path.join(base_dir, "ci", "check_hook_injection.py")
    if not os.path.isfile(script):
        return []
    rel = "ci/hook_cases.json"
    try:
        proc = subprocess.run(
            [sys.executable, script, "check"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as error:
        return [(rel, 1, INJECTION_RULE_ID, "cannot run: {0}".format(error))]
    if proc.returncode == 0:
        return []
    failures = []
    for line in (proc.stdout or "").splitlines():
        line = line.rstrip()
        # The summary line and the section header carry no defect of their own.
        if not line.strip() or line.startswith(("путей:", "== ")):
            continue
        failures.append((rel, 1, INJECTION_RULE_ID, line.strip()))
    if not failures:
        failures.append((rel, 1, INJECTION_RULE_ID, "check failed without output"))
    return failures


INSTALL_RULE_ID = "install-sim"


def collect_install_failures(base_dir):
    """Repository-level check: does a working install still assemble from this tree?

    The purity rules read sources; this one reads the result. It also carries the
    freshness check for ``docs/INVENTORY.md`` — the counts there are produced by
    the same build, so a stale inventory is a failed check rather than a document
    nobody notices has drifted.

    Returns a list of (rel_path, lineno, id, message).
    """
    script = os.path.join(base_dir, "ci", "simulate_install.py")
    if not os.path.isfile(script):
        return []
    try:
        proc = subprocess.run(
            [sys.executable, script],
            cwd=base_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as error:
        return [("ci/simulate_install.py", 1, INSTALL_RULE_ID,
                 "cannot run: {0}".format(error))]
    if proc.returncode == 0:
        return []
    failures = []
    for line in (proc.stdout or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(("FAIL", "BLOCK", "HIGH")) or "  FAIL  " in line:
            failures.append(("ci/simulate_install.py", 1, INSTALL_RULE_ID,
                             stripped.replace("FAIL", "", 1).strip()))
    if not failures:
        failures.append(("ci/simulate_install.py", 1, INSTALL_RULE_ID,
                         "install simulation failed without a named check"))
    return failures


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
        kind_hit = check_rule_kind(abs_path, rel_path)
        if kind_hit is not None:
            violations.append(kind_hit)
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
        kind_hit = check_rule_kind(abs_path, rel_for_rules)
        if kind_hit is not None:
            hits.add(kind_hit[2])
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

    # 3) The repository-level orphan check, exercised against the fixture tree:
    # no fixture references any other, so every fixture rule must come back.
    expected_orphans = set(expected.get("orphans", []))
    actual_orphans = {item[0] for item in collect_rule_orphans(fixtures_dir)}
    ok = expected_orphans == actual_orphans
    all_pass = all_pass and ok
    detail = ""
    if not ok:
        detail = " missing {0} unexpected {1}".format(
            sorted(expected_orphans - actual_orphans),
            sorted(actual_orphans - expected_orphans),
        )
    print("{0}  rule-orphan over fixtures{1}".format("PASS" if ok else "FAIL", detail))

    print("SELFTEST {0}".format("PASS" if all_pass else "FAIL"))
    return 0 if all_pass else 1


def main(argv=None):
    # Violations are printed, and on Windows stdout defaults to the console
    # codepage — which turns any non-Latin message into unreadable bytes and can
    # abort the run outright on a character it cannot encode.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
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
    # Repository-level, so it runs whole in both modes: whether a rule is
    # referenced cannot be decided from the staged subset alone.
    orphans = collect_rule_orphans(REPO_ROOT)
    _report(orphans)
    count += len(orphans)
    # Same reasoning: the map is checked against the whole rule set, not a
    # staged subset of it.
    map_defects = collect_map_defects(REPO_ROOT)
    _report(map_defects)
    count += len(map_defects)
    injection = collect_injection_failures(REPO_ROOT)
    _report(injection)
    count += len(injection)
    install = collect_install_failures(REPO_ROOT)
    _report(install)
    count += len(install)
    if count:
        print("airules: {0} layer-purity violation(s) found.".format(count), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
