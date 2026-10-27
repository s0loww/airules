"""Mappers for code_metadata's JSON responses.

These are cheap -- the backend already returns structure. The work here is
identity recovery: code_metadata reports module paths (call hierarchy) or a
hashed module id (vector chunks, e.g. "Module_c0cca8fd" with
module_type "Unknown"), so the canonical owner has to be rebuilt from
`loc.path`. That path is the only field both backends agree on, and it is what
makes records from the two sides comparable.
"""
import json
import re
from record import Record, Loc, Rel, Src, ParseResult, rel_path

BACKEND = "code"

# CommonModules/<Name>/Ext/Module.bsl -> <Name>
# Documents/<Name>/Ext/ObjectModule.bsl -> Документы-ish owner, keep the pair
_OWNER_FROM_PATH = re.compile(
    r"^(?P<container>[A-Za-z]+)/(?P<name>[^/]+)/Ext/(?P<module>[A-Za-z]+)\.bsl$")
_FORM_FROM_PATH = re.compile(
    r"^(?P<container>[A-Za-z]+)/(?P<name>[^/]+)/Forms/(?P<form>[^/]+)/Ext/Form/Module\.bsl$")


def owner_from_path(path):
    """Rebuild a canonical owner from a repo-relative module path."""
    if not path:
        return None
    m = _FORM_FROM_PATH.match(path)
    if m:
        return m.group("name") + "." + m.group("form")
    m = _OWNER_FROM_PATH.match(path)
    if m:
        return m.group("name")
    return None


def _data(text):
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return None
    if payload.get("status") != "success":
        return None
    return payload.get("data")


def _backend_error(text):
    """The backend's own refusal ("Module not found: ..."), or None.

    Distinct from an unparsable reply: a refusal is a definite answer about the
    object, and reporting it as format drift would send someone to re-baseline
    fixtures over what is really a wrong id.
    """
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(payload, dict) and payload.get("status") == "error":
        return str(payload.get("error") or "error")
    return None


def _refused_or_unparsed(text, what):
    error = _backend_error(text)
    if error:
        return ParseResult(status="not_found", note=what + ": " + error)
    return ParseResult(status="unparsed", note=what + ": not success JSON")


def _indexing(res, data):
    """A backend still building its index answers from a fallback layer; an
    empty answer then means "not yet", so that state has to travel along."""
    if data.get("indexing_status") == "in_progress":
        res.note = "backend index in progress; answered from %s" % (
            data.get("search_layer") or "a fallback layer")
    return res


def parse_call_hierarchy(text, direction="callers", root_id=None):
    data = _data(text)
    if data is None:
        return _refused_or_unparsed(text, "call hierarchy")
    key = "callers" if direction == "callers" else "callees"
    items = data.get(key) or []
    # the backend echoes the bare name it was asked with; the facade's resolver
    # supplies the canonical id so records from both backends can be merged
    root = root_id or data.get("method")
    rel_type = "calls" if direction == "callers" else "called_by"
    res = _indexing(ParseResult(resolved_id=root, status="ok" if items else "empty"), data)
    for it in items:
        path = rel_path(it.get("module"))
        owner = owner_from_path(path)
        name = it.get("name")
        res.records.append(Record(
            id=(owner + "." + name) if owner else name,
            kind="routine", name=name, owner=owner,
            loc=Loc(path=path, line=it.get("call_line")),
            rel=Rel(type=rel_type, to=root, depth=1),
            src=Src(backend=BACKEND, tool="get_method_call_hierarchy", tier="indexed")))
    return res


def parse_search_function(text):
    data = _data(text)
    if data is None:
        return _refused_or_unparsed(text, "search_function")
    items = data.get("results") or []
    res = ParseResult(status="ok" if items else "empty")
    for it in items:
        # `module_path` is where the backend puts it; missing it left two
        # homonyms with one bare id, and dedupe folded them into one record
        path = rel_path(it.get("path") or it.get("module_path") or it.get("module"))
        owner = owner_from_path(path)
        name = it.get("name")
        res.records.append(Record(
            id=(owner + "." + name) if owner else name,
            kind="routine", name=name, owner=owner,
            loc=Loc(path=path, line=it.get("start_line"), end=it.get("end_line")),
            text=it.get("body"),
            src=Src(backend=BACKEND, tool="search_function", tier="indexed")))
    return res


def parse_metadata_details(text):
    data = _data(text)
    if data is None:
        return _refused_or_unparsed(text, "metadata_details")
    if data.get("status") == "ambiguous":
        # images from 27.09.2026 no longer pick one of two homonyms (a common
        # module and a catalog) silently; the qualified name resolves it
        candidates = [c.get("full_path") for c in data.get("candidates") or []]
        return ParseResult(status="not_found", note="metadata_details: ambiguous name, one of: "
                           + ", ".join(c for c in candidates if c))
    root = data.get("full_path") or data.get("name")
    attrs = data.get("attributes") or []
    tabular = data.get("tabular_parts") or {}
    res = ParseResult(resolved_id=root, status="ok" if attrs or tabular else "empty")
    res.note_section("attributes", None, len(attrs))
    for a in attrs:
        res.records.append(Record(
            id=root + "." + a.get("name", ""), kind="attribute", name=a.get("name"),
            owner=root, text=a.get("type"),
            src=Src(backend=BACKEND, tool="get_metadata_details", tier="indexed")))
    # columns of tabular sections: the dossier names a section but not the types
    # of its columns, so without these a caller cannot describe a section at all
    columns = 0
    for part, items in tabular.items():
        owner = root + "." + part
        for c in items or []:
            res.records.append(Record(
                id=owner + "." + c.get("name", ""), kind="attribute", name=c.get("name"),
                owner=owner, text=c.get("type"),
                src=Src(backend=BACKEND, tool="get_metadata_details", tier="indexed")))
            columns += 1
    if tabular:
        res.note_section("tabular_columns", None, columns)
    return res


def parse_dependencies(text, direction="reverse"):
    data = _data(text)
    if data is None:
        return _refused_or_unparsed(text, "graph_dependencies")
    root = data.get("object")
    if not data.get("found"):
        return ParseResult(resolved_id=root, status="not_found")
    res = ParseResult(resolved_id=root, status="ok")
    # the backend labels a live XML walk explicitly; carry that into src.tier
    tier = "live" if data.get("search_layer") == "live_xml" else "indexed"
    for key, rtype in (("reverse", "references"), ("forward", "referenced_by")):
        if direction not in (key, "both"):
            continue
        items = data.get(key) or []
        res.note_section(key, None, len(items))
        for it in items:
            # "Справочники.ОбъектыЭксплуатации.xml" -> drop the file extension
            qual = re.sub(r"\.xml$", "", it.get("source", ""))
            parts = qual.split(".")
            res.records.append(Record(
                id=qual, kind="metadata", name=parts[-1],
                owner=".".join(parts[:-1]) or None,
                rel=Rel(type=rtype, to=root, via=it.get("edge_type")),
                src=Src(backend=BACKEND, tool="graph_dependencies", tier=tier,
                        score=it.get("weight"))))
    if not res.records:
        res.status = "empty"
    return res


def parse_metadatasearch(text):
    """Two shapes: `names_only` rows (full_path / name / object_type) and chunk
    rows (a document plus the file and line it came from)."""
    data = _data(text)
    if data is None:
        return _refused_or_unparsed(text, "metadatasearch")
    items = data.get("results") or []
    res = _indexing(ParseResult(status="ok" if items else "empty"), data)
    for it in items:
        if it.get("full_path") and "document" not in it:
            qual = it["full_path"]
            res.records.append(Record(
                id=qual, kind="metadata", name=it.get("name") or qual.rsplit(".", 1)[-1],
                owner=it.get("object_type"), text=it.get("synonym") or None,
                src=Src(backend=BACKEND, tool="metadatasearch", tier="indexed")))
            continue
        raw_id = it.get("id") or ""
        path, _, line = raw_id.rpartition(":")
        if not line.isdigit():
            path, line = raw_id, ""
        meta = it.get("metadata") or {}
        path = rel_path(meta.get("full_path") or path)
        grep = "grep" in (it.get("search_layer"), it.get("search_type"))
        res.records.append(Record(
            id=("%s:%s" % (path, line)) if line else (path or raw_id), kind="snippet",
            name=meta.get("source_file") or path or "metadata",
            loc=Loc(path=path, line=int(line) if line else None),
            text=it.get("document"),
            src=Src(backend=BACKEND, tool="metadatasearch",
                    tier="grep" if grep else "indexed", score=it.get("distance"))))
    return res


def parse_codesearch(text):
    """Vector chunks. The module id is hashed (`Module_c0cca8fd`), so identity is
    rebuilt from `source_path` -- the one field both backends agree on."""
    data = _data(text)
    if data is None:
        return _refused_or_unparsed(text, "codesearch")
    items = data.get("results") or []
    res = _indexing(ParseResult(status="ok" if items else "empty"), data)
    for it in items:
        meta = it.get("metadata") or {}
        path = rel_path(meta.get("source_path"))
        owner = owner_from_path(path)
        name = meta.get("name") or it.get("id")
        grep = (it.get("search_layer") or data.get("search_layer")) == "grep"
        res.records.append(Record(
            id=(owner + "." + name) if owner else (path or name),
            kind="routine" if meta.get("symbol_type") else "snippet",
            name=name, owner=owner,
            loc=Loc(path=path, line=meta.get("start_line"), end=meta.get("end_line")),
            sig=meta.get("directive") or None,
            text=it.get("document"),
            src=Src(backend=BACKEND, tool="codesearch",
                    tier="grep" if grep else "indexed", score=it.get("combined_score"))))
    return res


def form_id(object_name, form_name):
    """`Справочники.X.Форма.Y` -- the same spelling the resolver gives a form module."""
    return "%s.Форма.%s" % (object_name, form_name) if form_name else object_name


def parse_search_forms(text):
    data = _data(text)
    if data is None:
        return _refused_or_unparsed(text, "search_forms")
    items = data.get("results") or []
    res = _indexing(ParseResult(status="ok" if items else "empty"), data)
    for it in items:
        obj, form = it.get("object_name"), it.get("form_name")
        res.records.append(Record(
            id=form_id(obj, form), kind="form", name=form or obj, owner=obj,
            loc=Loc(path=rel_path(it.get("file_path"))),
            text=it.get("title") or None,
            src=Src(backend=BACKEND, tool="search_forms", tier="indexed")))
    return res


def _layout_src():
    return Src(backend=BACKEND, tool="inspect_form_layout", tier="indexed")


def parse_form_layout(text):
    """Element tree, attributes, commands and handlers of one form. The tree is
    kept as parent links (`rel.to`) -- enough for a caller to rebuild it."""
    data = _data(text)
    if data is None:
        return _refused_or_unparsed(text, "inspect_form_layout")
    root = form_id(data.get("object_name"), data.get("form_name"))
    res = _indexing(ParseResult(resolved_id=root), data)
    res.records.append(Record(
        id=root, kind="form", name=data.get("form_name") or root,
        owner=data.get("object_name"), loc=Loc(path=rel_path(data.get("file_path"))),
        text=data.get("title") or None, src=_layout_src()))
    elements = data.get("elements") or []
    for el in elements:
        parent = el.get("parent")
        res.records.append(Record(
            id=root + "." + el.get("name", ""), kind="element", name=el.get("name"),
            owner=root, sig=el.get("type"),
            text=el.get("data_path") or el.get("title") or None,
            rel=Rel(type="child_of", to=root + "." + parent, depth=el.get("depth"))
            if parent else None,
            src=_layout_src()))
    attributes = data.get("attributes") or []
    for at in attributes:
        types = at.get("types") or at.get("type")
        if isinstance(types, list):
            types = ", ".join(str(t) for t in types)
        res.records.append(Record(
            id=root + ".Реквизиты." + at.get("name", ""), kind="attribute",
            name=at.get("name"), owner=root, text=types or None, src=_layout_src()))
    commands = data.get("commands") or []
    for cm in commands:
        res.records.append(Record(
            id=root + ".Команды." + cm.get("name", ""), kind="command",
            name=cm.get("name"), owner=root,
            text=cm.get("action") or cm.get("title") or None, src=_layout_src()))
    handlers = data.get("handlers") or []
    for hd in handlers:
        event = str(hd.get("event") or hd.get("name"))
        res.records.append(Record(
            id=root + ".События." + (str(hd.get("element")) + "." if hd.get("element") else "") + event,
            kind="routine",
            name=hd.get("handler") or hd.get("procedure") or hd.get("action") or event,
            owner=root, sig=event, text=hd.get("element") or None, src=_layout_src()))
    res.note_section("elements", None, len(elements))
    res.note_section("attributes", None, len(attributes))
    res.note_section("commands", None, len(commands))
    res.note_section("handlers", None, len(handlers))
    res.status = "ok" if len(res.records) > 1 else "empty"
    return res


def parse_module_structure(text, owner=None):
    """Procedures and functions of one module with lines, export flag and
    execution context; the stats block is the declared count checked against."""
    data = _data(text)
    if data is None:
        return _refused_or_unparsed(text, "get_module_structure")
    path = rel_path(data.get("path"))
    owner = owner or owner_from_path(path) or path
    routines = (data.get("procedures") or []) + (data.get("functions") or [])
    stats = data.get("stats") or {}
    declared = None
    if "total_procedures" in stats or "total_functions" in stats:
        declared = int(stats.get("total_procedures") or 0) + int(stats.get("total_functions") or 0)
    res = _indexing(ParseResult(resolved_id=owner, declared=declared,
                                status="ok" if routines else "empty"), data)
    for r in routines:
        name = r.get("name")
        flags = [r.get("execution_context") or ""]
        if r.get("is_export"):
            flags.append("Экспорт")
        res.records.append(Record(
            id=owner + "." + name, kind="routine", name=name, owner=owner,
            loc=Loc(path=path, line=r.get("start_line"), end=r.get("end_line")),
            sig=" ".join(f for f in flags if f) or None,
            text=r.get("region") or None,
            src=Src(backend=BACKEND, tool="get_module_structure", tier="indexed")))
    return res
