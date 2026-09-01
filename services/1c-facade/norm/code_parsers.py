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


def parse_call_hierarchy(text, direction="callers", root_id=None):
    data = _data(text)
    if data is None:
        return ParseResult(status="unparsed", note="call hierarchy: not success JSON")
    key = "callers" if direction == "callers" else "callees"
    items = data.get(key) or []
    # the backend echoes the bare name it was asked with; the facade's resolver
    # supplies the canonical id so records from both backends can be merged
    root = root_id or data.get("method")
    rel_type = "calls" if direction == "callers" else "called_by"
    res = ParseResult(resolved_id=root, status="ok" if items else "empty")
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
        return ParseResult(status="unparsed", note="search_function: not success JSON")
    items = data.get("results") or []
    res = ParseResult(status="ok" if items else "empty")
    for it in items:
        path = rel_path(it.get("path") or it.get("module"))
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
        return ParseResult(status="unparsed", note="metadata_details: not success JSON")
    root = data.get("full_path") or data.get("name")
    attrs = data.get("attributes") or []
    res = ParseResult(resolved_id=root, status="ok" if attrs else "empty")
    res.note_section("attributes", None, len(attrs))
    for a in attrs:
        res.records.append(Record(
            id=root + "." + a.get("name", ""), kind="attribute", name=a.get("name"),
            owner=root, text=a.get("type"),
            src=Src(backend=BACKEND, tool="get_metadata_details", tier="indexed")))
    return res


def parse_dependencies(text, direction="reverse"):
    data = _data(text)
    if data is None:
        return ParseResult(status="unparsed", note="graph_dependencies: not success JSON")
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
