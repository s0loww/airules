"""Parsers for graph_metadata's prose responses.

The server answers in formatted Russian text, not JSON. That text is
machine-generated from a stable template, so a regex parser is the right tool:
deterministic, pinned by fixtures, free. Every parser reports the count the
server declared in its own header next to what we actually parsed -- a mismatch
means the image changed the format and fixtures must be re-captured
(facade/capture.py).
"""
import re
from record import Record, Loc, Rel, Src, ParseResult, rel_path

BACKEND = "graph"


def _directive(tail):
    """The compilation directive from an item tail, if it carries one."""
    match = _CC_DIRECTIVE.search(tail or "")
    return match.group(1) if match else None

# ---------------------------------------------------------------- call chain

_CC_HEAD = re.compile(
    r"^Цепочка вызовов '(?P<name>[^'(]+?)\s*\((?P<owner>[^)]+)\)'\s*"
    r"\(direction=(?P<dir>\w+),\s*depth=(?P<depth>\d+)\)\s*—\s*(?P<n>\d+)", re.M)
# "вызовы не найдены" answers callees, "вызывающие не найдены" answers callers:
# the same empty result in two wordings.
_CC_NONE = re.compile(
    r"^'(?P<name>[^']+)'\s*\((?P<owner>[^)]+)\):\s*(?:вызовы|вызывающие) не найдены", re.M)
# Asked with an owner (`object_name`, which `calls` always passes to pin the
# homonym) the refusal reads "Процедура 'X' (object: Y) не найдена"; the bare
# form lacks the parenthesis. Both are one answer: the graph does not know it.
_CC_404 = re.compile(
    r"^(?:Процедура|Функция)\s*'(?P<name>[^']+)'\s*(?:\(object:\s*(?P<owner>[^)]*)\)\s*)?"
    r"не найдена", re.M)
_CC_DEPTH = re.compile(r"^\s*Глубина\s+(?P<d>\d+):", re.M)
# The tail after `(owner / kind)` carries an export marker and a compilation
# directive in either order -- both `... Экспорт` and `... [&НаСервере] Экспорт`
# occur. Matching a fixed order silently dropped the second shape, which the
# drift detector caught the first time this met a new configuration.
_CC_ITEM = re.compile(
    r"^\s*-\s+(?P<name>[^\s(]+)\s*\((?P<owner>[^/)]+?)\s*/\s*(?P<mtype>[^)]+)\)"
    r"(?P<tail>(?:\s+(?:Экспорт|Export)|\s*\[[^\]]*\])*)\s*$", re.IGNORECASE)
_CC_DIRECTIVE = re.compile(r"\[([^\]]*)\]")
_CC_SIG = re.compile(r"^\s*Сигнатура:\s*(?P<sig>.+?)\s*$")


def parse_call_chain(text, direction="callers", root_id=None):
    text = text.strip()
    m404 = _CC_404.search(text)
    if m404:
        return ParseResult(status="not_found",
                           note="routine not known to graph: " + m404.group("name"))
    mnone = _CC_NONE.search(text)
    if mnone:
        return ParseResult(status="empty",
                           resolved_id=mnone.group("owner").strip() + "." + mnone.group("name").strip())
    head = _CC_HEAD.search(text)
    if not head:
        return ParseResult(status="unparsed", note="call-chain header not recognised")

    echoed = head.group("owner").strip() + "." + head.group("name").strip()
    root = root_id or echoed
    direction = head.group("dir") or direction
    # a caller calls the root; a callee is called by it
    rel_type = "calls" if direction == "callers" else "called_by"

    res = ParseResult(resolved_id=root, echoed_id=echoed,
                      declared=int(head.group("n")))
    depth, pending = None, None
    for line in text.splitlines():
        md = _CC_DEPTH.match(line)
        if md:
            depth = int(md.group("d"))
            continue
        mi = _CC_ITEM.match(line)
        if mi:
            owner = mi.group("owner").strip()
            name = mi.group("name").strip()
            pending = Record(
                id=owner + "." + name, kind="routine", name=name, owner=owner,
                rel=Rel(type=rel_type, to=root, depth=depth),
                src=Src(backend=BACKEND, tool="trace_call_chain", tier="indexed"),
                text=_directive(mi.group("tail")))
            res.records.append(pending)
            continue
        ms = _CC_SIG.match(line)
        if ms and pending is not None:
            pending.sig = ms.group("sig")
            pending = None
    return res


# -------------------------------------------------------------- object usages

_US_HEAD = re.compile(r"^Object '(?P<obj>[^']+)' is referenced in (?P<n>\d+)\s", re.M)
_US_NONE = re.compile(r"^No attribute-level usages found for object '(?P<obj>[^']+)'", re.M)
_US_ITEM = re.compile(
    r"^\s*\d+\.\s+(?P<qual>[^\s\[]+)\s*\[(?P<akind>[^\]]+)\]\s*\(Тип:\s*(?P<type>[^)]+)\)")


def parse_usages(text):
    text = text.strip()
    mnone = _US_NONE.search(text)
    if mnone:
        return ParseResult(status="empty", resolved_id=mnone.group("obj"))
    head = _US_HEAD.search(text)
    if not head:
        return ParseResult(status="unparsed", note="usages header not recognised")

    root = head.group("obj")
    # here the backend echoes the object it was asked about, so there is nothing
    # to disagree with -- unlike the call chain, which resolves a name itself
    res = ParseResult(resolved_id=root, echoed_id=root,
                      declared=int(head.group("n")))
    for line in text.splitlines():
        mi = _US_ITEM.match(line)
        if not mi:
            continue
        qual = mi.group("qual")
        parts = qual.split(".")
        owner = ".".join(parts[:-1])
        res.records.append(Record(
            id=qual, kind="attribute", name=parts[-1], owner=owner or None,
            rel=Rel(type="typed_as", to=root, via=mi.group("akind").strip()),
            text=mi.group("type").strip(),
            src=Src(backend=BACKEND, tool="find_usages_of_object", tier="indexed")))
    return res


# --------------------------------------------------------------- code search

_SC_HEAD = re.compile(r"^Found (?P<n>\d+) results? for:\s*'(?P<q>.*)'\s*\("
                      r"search_type=(?P<st>\w+),\s*detail_level=(?P<dl>\w+)\)", re.M)
_SC_ITEM = re.compile(r"^\s*\d+\.\s+(?P<name>[^\s(]+)\s*\((?P<owner>[^/)]+?)\s*/\s*(?P<mtype>[^)]+)\)")
_SC_SCORE = re.compile(r"^\s*Score:\s*(?P<score>[\d.]+)\s*(?:\[(?P<how>[^\]]+)\])?")
_SC_SIG = re.compile(r"^\s*Signature:\s*(?P<sig>.+?)\s*$")
_SC_FILE = re.compile(r"^\s*File:\s*(?P<path>.+?):(?P<line>\d+)\s*$")


def parse_search_code(text):
    text = text.strip()
    head = _SC_HEAD.search(text)
    if not head:
        return ParseResult(status="unparsed", note="search_code header not recognised")
    res = ParseResult(declared=int(head.group("n")), note="search_type=" + head.group("st"))
    cur = None
    for line in text.splitlines():
        mi = _SC_ITEM.match(line)
        if mi:
            owner = mi.group("owner").strip()
            name = mi.group("name").strip()
            cur = Record(id=owner + "." + name, kind="routine", name=name, owner=owner,
                         src=Src(backend=BACKEND, tool="search_code", tier="indexed"))
            res.records.append(cur)
            continue
        if cur is None:
            continue
        m = _SC_SCORE.match(line)
        if m:
            cur.src.score = float(m.group("score"))
            continue
        m = _SC_SIG.match(line)
        if m:
            cur.sig = m.group("sig")
            continue
        m = _SC_FILE.match(line)
        if m:
            cur.loc = Loc(path=rel_path(m.group("path")), line=int(m.group("line")))
    return res


# ------------------------------------------------------------------- dossier

_DS_HEAD = re.compile(r"^#\s*Досье:\s*(?P<id>\S+)(?:\s*\[конфигурация:\s*(?P<cfg>[^\]]+)\])?", re.M)
_DS_404 = re.compile(r"^Объект\s+'(?P<id>[^']+)'\s+не найден", re.M)
_DS_SECTION = re.compile(r"^(?P<lvl>#{2,3})\s*(?P<title>.+?)(?:\s*\((?P<n>\d+)\))?\s*$")
_DS_ATTR = re.compile(r"^\s*\d+\.\s+(?P<name>\S+)\s+—\s+(?P<type>.+?)\s*$")
_DS_TAB = re.compile(r"^\s*\d+\.\s+(?P<name>\S+)(?:\s*[\[(](?P<syn>[^\])]*)[\])])?\s*$")
_DS_DEP = re.compile(r"^\s*\d+\.\s+(?P<qual>\S+)\s*\((?P<via>[^,)]+),\s*(?P<kind>[^)]+)\)")
_DS_ROUTINE = re.compile(r"^\s*-\s*(?:Процедура|Функция)\s+(?P<name>[^\s(]+)\s*\((?P<args>.*)\)\s*$")

_SECTION_BY_TITLE = (
    ("Реквизиты", "attributes"),
    ("Табличные части", "tabular"),
    ("Формы", "forms"),
    ("Downstream", "downstream"),
    ("Upstream", "upstream"),
    ("Код", "code"),
)


def parse_dossier(text):
    text = text.strip()
    head = _DS_HEAD.search(text)
    if not head:
        missing = _DS_404.search(text)
        if missing:
            return ParseResult(status="not_found",
                               note="object not known to graph: " + missing.group("id"))
        return ParseResult(status="unparsed", note="dossier header not recognised")
    root = head.group("id")
    res = ParseResult(resolved_id=root, note=head.group("cfg"))

    section = None
    declared = None
    counters = {}
    module_type = None

    def close(sec, dec):
        if sec:
            res.note_section(sec, dec, counters.get(sec, 0))

    for line in text.splitlines():
        ms = _DS_SECTION.match(line)
        if ms:
            title = ms.group("title").strip()
            # a level-3 heading inside "Код" names the module, not a new section
            if ms.group("lvl") == "###" and section == "code" and not any(
                    title.startswith(p) for p, _ in _SECTION_BY_TITLE):
                module_type = title
                continue
            close(section, declared)
            declared = int(ms.group("n")) if ms.group("n") else None
            section = None
            for prefix, key in _SECTION_BY_TITLE:
                if title.startswith(prefix):
                    section = key
                    break
            if section == "code":
                module_type = None
            continue
        if not section or not line.strip():
            continue

        if section == "attributes":
            m = _DS_ATTR.match(line)
            if m:
                res.records.append(Record(
                    id=root + "." + m.group("name"), kind="attribute", name=m.group("name"),
                    owner=root, text=m.group("type"),
                    src=Src(BACKEND, "get_object_dossier")))
                counters[section] = counters.get(section, 0) + 1
        elif section in ("tabular", "forms"):
            m = _DS_TAB.match(line)
            if m:
                res.records.append(Record(
                    id=root + "." + m.group("name"),
                    kind="form" if section == "forms" else "metadata",
                    name=m.group("name"), owner=root,
                    src=Src(BACKEND, "get_object_dossier")))
                counters[section] = counters.get(section, 0) + 1
        elif section in ("downstream", "upstream"):
            m = _DS_DEP.match(line)
            if m:
                # downstream: they reference root; upstream: root references them
                rtype = "references" if section == "downstream" else "referenced_by"
                qual = m.group("qual")
                parts = qual.split(".")
                res.records.append(Record(
                    id=qual, kind="metadata", name=parts[-1],
                    owner=".".join(parts[:-1]) or None,
                    rel=Rel(type=rtype, to=root,
                            via=m.group("kind").strip() + ":" + m.group("via").strip()),
                    src=Src(BACKEND, "get_object_dossier")))
                counters[section] = counters.get(section, 0) + 1
        elif section == "code":
            m = _DS_ROUTINE.match(line)
            if m:
                owner = root + "." + (module_type or "Module")
                res.records.append(Record(
                    id=owner + "." + m.group("name"), kind="routine", name=m.group("name"),
                    owner=owner, sig=line.strip().lstrip("- "),
                    src=Src(BACKEND, "get_object_dossier")))
                counters[section] = counters.get(section, 0) + 1
    close(section, declared)
    return res
