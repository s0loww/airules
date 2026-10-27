"""Fixture gate for the facade parsers.

Two independent checks, in the style of ci/check_layers.py:

  1. INVARIANTS -- counts established outside the servers: a grep over the
     configuration source on capture day, or an agreement between the two
     backends. These catch a parser that is self-consistently wrong. The
     committed fixtures are anonymised (see anonymise.py) -- identifiers are
     mapped and code bodies dropped, but every count is preserved, so the
     numbers below still mean what they meant against the real corpus.
  2. SNAPSHOT -- parsed records against expected.json. This catches format
     drift when a comol image is updated.

Usage:
    python test_parsers.py            # gate; exit 1 on any failure
    python test_parsers.py --update   # re-baseline expected.json after review
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "norm"))

from record import prune                      # noqa: E402
import graph_parsers as G                     # noqa: E402
import code_parsers as C                      # noqa: E402
import platform_parsers as P                  # noqa: E402

FX = os.path.join(HERE, "fixtures")
EXPECTED = os.path.join(FX, "expected.json")


def load(name):
    ext = "json" if name.startswith("code_") else "txt"
    with io.open(os.path.join(FX, name + "." + ext), encoding="utf-8") as f:
        return f.read()


CASES = {
    "graph_call_chain__callers": lambda t: G.parse_call_chain(t, "callers"),
    "graph_call_chain__callees": lambda t: G.parse_call_chain(t, "callees"),
    "graph_call_chain__deep":    lambda t: G.parse_call_chain(t, "callers"),
    "graph_call_chain__empty":   lambda t: G.parse_call_chain(t, "callers"),
    "graph_call_chain__tails":   lambda t: G.parse_call_chain(t, "callers"),
    "graph_call_chain__owned_missing": lambda t: G.parse_call_chain(t, "callers"),
    "graph_call_chain__no_callers": lambda t: G.parse_call_chain(t, "callers"),
    "graph_usages__ok":          G.parse_usages,
    "graph_usages__empty":       G.parse_usages,
    "graph_search_code__ok":     G.parse_search_code,
    "graph_dossier__ok":         G.parse_dossier,
    "code_call_hierarchy__ok":   lambda t: C.parse_call_hierarchy(t, "callers"),
    "code_search_function__ok":  C.parse_search_function,
    "code_metadata_details__ok": C.parse_metadata_details,
    "code_dependencies__reverse": lambda t: C.parse_dependencies(t, "reverse"),
    "code_search_forms__ok":     C.parse_search_forms,
    "code_search_forms__empty":  C.parse_search_forms,
    "code_form_layout__ok":      C.parse_form_layout,
    "code_module_structure__ok": C.parse_module_structure,
    "code_module_structure__missing": C.parse_module_structure,
    "code_metadatasearch__ok":   C.parse_metadatasearch,
    "code_metadatasearch__names": C.parse_metadatasearch,
    "code_metadatasearch__empty": C.parse_metadatasearch,
    "code_codesearch__ok":       C.parse_codesearch,
    "platform_docsearch__ok":    P.parse_docs,
    "platform_docinfo__ok":      lambda t: P.parse_docs(t, "docinfo"),
    "platform_docinfo__missing": lambda t: P.parse_docs(t, "docinfo"),
    "platform_its__ok":          P.parse_its,
    "platform_syntax__issues":   P.parse_syntax,
    "platform_templates__ok":    P.parse_templates,
    "platform_template__one":    lambda t: P.parse_templates(t, "get_template"),
    # graph/code images of 27.09.2026, captured on a small extension
    "graph_call_chain__callers__v4": lambda t: G.parse_call_chain(t, "callers"),
    "graph_call_chain__callees__v4": lambda t: G.parse_call_chain(t, "callees"),
    "graph_call_chain__deep__v4":    lambda t: G.parse_call_chain(t, "callers"),
    "graph_call_chain__empty__v4":   lambda t: G.parse_call_chain(t, "callers"),
    "graph_usages__ok__v4":          G.parse_usages,
    "graph_usages__empty__v4":       G.parse_usages,
    "graph_search_code__ok__v4":     G.parse_search_code,
    "graph_dossier__ok__v4":         G.parse_dossier,
    "graph_dossier__folded__v4":     G.parse_dossier,
    "code_call_hierarchy__ok__v4":   lambda t: C.parse_call_hierarchy(t, "callers"),
    "code_search_function__ok__v4":  C.parse_search_function,
    "code_metadata_details__ok__v4": C.parse_metadata_details,
    "code_metadata_details__ambiguous__v4": C.parse_metadata_details,
    "code_dependencies__reverse__v4": lambda t: C.parse_dependencies(t, "reverse"),
    "code_search_forms__ok__v4":     C.parse_search_forms,
    "code_search_forms__empty__v4":  C.parse_search_forms,
    "code_form_layout__ok__v4":      C.parse_form_layout,
    "code_module_structure__ok__v4": C.parse_module_structure,
    "code_module_structure__missing__v4": C.parse_module_structure,
    "code_metadatasearch__ok__v4":   C.parse_metadatasearch,
    "code_metadatasearch__names__v4": C.parse_metadatasearch,
    "code_metadatasearch__empty__v4": C.parse_metadatasearch,
    "code_codesearch__ok__v4":       C.parse_codesearch,
    # layouts of the comol images of 27.09.2026 (docs JSON 4.1, syntax TOON)
    "platform_docsearch__ok__v4":    P.parse_docs,
    "platform_docinfo__ok__v4":      lambda t: P.parse_docs(t, "docinfo"),
    "platform_docinfo__missing__v4": lambda t: P.parse_docs(t, "docinfo"),
    "platform_docinfo__variants__v4":  lambda t: P.parse_docs(t, "docinfo"),
    "platform_docinfo__ambiguous__v4": lambda t: P.parse_docs(t, "docinfo"),
    "platform_docinfo__by_doc_id__v4": lambda t: P.parse_docs(t, "docinfo"),
    "platform_syntax__issues__v4":   P.parse_syntax,
    "platform_syntax__clean__v4":    P.parse_syntax,
    "platform_templates__ok__v4":    P.parse_templates,
    "platform_template__one__v4":    lambda t: P.parse_templates(t, "get_template"),
}


def run_all():
    return {name: fn(load(name)) for name, fn in CASES.items()}


def snapshot(results):
    out = {}
    for name, r in sorted(results.items()):
        out[name] = {
            "status": r.status,
            "resolved_id": r.resolved_id,
            "declared": r.declared,
            "count": len(r.records),
            "sections": r.sections,
            "records": [prune(x) for x in r.records],
        }
    return out


def invariants(res):
    """Facts established outside the servers. Each returns (ok, message)."""
    checks = []

    def eq(label, got, want):
        checks.append((got == want, label + ": got " + repr(got) + ", want " + repr(want)))

    # grep over 446 .bsl files: 8 external files call ДЕМО_ОбщегоНазначенияСервер.ОтправкаПочты
    cc = res["graph_call_chain__callers"]
    eq("graph callers count (grep ground truth)", len(cc.records), 8)
    eq("graph resolved qualified name", cc.resolved_id, "ДЕМО_ОбщегоНазначенияСервер.ОтправкаПочты")
    eq("graph callers all carry a signature",
       sum(1 for r in cc.records if r.sig), 8)
    eq("graph callers relate to root",
       sum(1 for r in cc.records if r.rel and r.rel.type == "calls" and r.rel.to == cc.resolved_id), 8)

    # measured asymmetry: code_metadata matches on the bare name and finds 2 of 8
    ch = res["code_call_hierarchy__ok"]
    eq("code callers count (known low recall)", len(ch.records), 2)

    # an item tail carries the export marker and the directive in either order
    tails = res["graph_call_chain__tails"]
    eq("both tail orders parse", len(tails.records), 4)
    eq("the directive is kept whichever side it sits on",
       [r.text for r in tails.records], [None, None, "&НаСервере", "&НаСервере"])

    # empty and not-found must stay distinguishable
    eq("callees empty status", res["graph_call_chain__callees"].status, "empty")
    eq("unknown routine status", res["graph_call_chain__empty"].status, "not_found")
    eq("unknown routine asked with its owner is not_found, not drift",
       res["graph_call_chain__owned_missing"].status, "not_found")
    eq("no callers is empty, not drift", res["graph_call_chain__no_callers"].status, "empty")
    eq("usages empty status", res["graph_usages__empty"].status, "empty")

    # server-declared totals must equal what we parsed, everywhere
    for name, r in res.items():
        if r.drift:
            checks.append((False, name + " drift: " + "; ".join(r.drift)))
        else:
            checks.append((True, name + " no drift"))

    # cross-backend agreement: both describe the same object's attributes
    ds = res["graph_dossier__ok"]
    md = res["code_metadata_details__ok"]
    # the object's own attributes: details also carry the columns of tabular
    # sections (owner = the section), which the dossier does not list
    ds_attrs = sum(1 for r in ds.records if r.kind == "attribute" and r.owner == ds.resolved_id)
    md_attrs = sum(1 for r in md.records if r.kind == "attribute" and r.owner == md.resolved_id)
    eq("dossier vs details: attribute count agrees", ds_attrs, md_attrs)

    # with the resolver supplying a canonical id, both backends agree on rel.to --
    # this is the precondition for merging their records at all
    CANON = "ДЕМО_ОбщегоНазначенияСервер.ОтправкаПочты"
    ch2 = C.parse_call_hierarchy(load("code_call_hierarchy__ok"), "callers", root_id=CANON)
    targets = {r.rel.to for r in list(cc.records) + list(ch2.records) if r.rel}
    eq("merged rel.to is canonical across backends", targets, {CANON})

    # -- facade 0.2: forms, modules, metadata and code search ------------
    raw = json.loads(load("code_form_layout__ok"))["data"]
    fl = res["code_form_layout__ok"]
    elements = [r for r in fl.records if r.kind == "element"]
    eq("form layout: every element parsed", len(elements), len(raw["elements"]))
    eq("form layout: the form itself heads the records", fl.records[0].kind, "form")
    ids = {r.id for r in fl.records}
    dangling = [r.id for r in elements if r.rel and r.rel.to not in ids]
    eq("form layout: every parent link lands on a parsed element", dangling, [])
    eq("form layout: form id is the resolver's spelling",
       fl.resolved_id, "Справочники.ДоговорыКонтрагентов.Форма.ФормаЭлемента")

    sf = res["code_search_forms__ok"]
    eq("forms search: every hit is a form with a Form.xml location",
       sum(1 for r in sf.records if r.kind == "form" and r.loc.path.endswith("Form.xml")),
       len(sf.records))
    eq("forms search: nothing found stays empty", res["code_search_forms__empty"].status, "empty")

    ms = res["code_module_structure__ok"]
    eq("module structure: owner rebuilt from the path",
       ms.resolved_id, "СчетФактураВыданный.ФормаСписка")
    eq("module structure: every routine carries a line span",
       sum(1 for r in ms.records if r.loc.line and r.loc.end and r.loc.line <= r.loc.end),
       len(ms.records))
    missing = res["code_module_structure__missing"]
    eq("module structure: a refusal is not_found, not format drift", missing.status, "not_found")

    names = res["code_metadatasearch__names"]
    eq("metadata names: canonical qualifier",
       [r.id for r in names.records], ["Справочники.ДоговорыКонтрагентов"])
    chunks = res["code_metadatasearch__ok"]
    eq("metadata chunks: every hit has a line",
       sum(1 for r in chunks.records if r.loc and isinstance(r.loc.line, int)),
       len(chunks.records))
    eq("metadata: nothing found stays empty", res["code_metadatasearch__empty"].status, "empty")

    cs = res["code_codesearch__ok"]
    eq("codesearch: no hashed module id survives",
       [r.id for r in cs.records if r.id.startswith("Module_")], [])
    eq("codesearch: every chunk is located",
       sum(1 for r in cs.records if r.loc and r.loc.path), len(cs.records))

    # -- platform servers ---------------------------------------------
    eq("docinfo: an exact name gives one article",
       [r.id for r in res["platform_docinfo__ok"].records], ["doc:ТаблицаЗначений.Найти"])
    eq("docinfo: an unknown name is not_found — the only honest empty answer",
       res["platform_docinfo__missing"].status, "not_found")
    ok_ds = res["platform_docsearch__ok"]
    eq("docsearch: one record per article heading",
       len(ok_ds.records),
       sum(1 for chunk in load("platform_docsearch__ok").split("\n---\n")
           if chunk.strip().startswith("# ")))
    its = res["platform_its__ok"]
    eq("its: every link becomes a record",
       len(its.records), load("platform_its__ok").count("](http"))
    syntax = res["platform_syntax__issues"]
    eq("syntax: every diagnostic is 1-based and located",
       sum(1 for r in syntax.records if r.loc and r.loc.line and r.loc.line >= 1),
       len(syntax.records))
    tpl = res["platform_templates__ok"]
    eq("templates: every template is found",
       len(tpl.records), load("platform_templates__ok").count("**Template:**"))
    eq("templates: get_template JSON parses too",
       [r.id for r in res["platform_template__one"].records], ["template:1"])

    # -- graph/code, images of 27.09.2026 ------------------------------
    def declared(name):
        # the count the server printed in the prose inside its envelope
        prose = json.loads(load(name))["text"]
        return int(re.search(r"—\s*(\d+)\s+процедур", prose).group(1))
    for case in ("callers", "callees"):
        name = "graph_call_chain__%s__v4" % case
        eq("v4 graph %s: the envelope is unwrapped, every declared routine parsed" % case,
           (res[name].status, len(res[name].records)), ("ok", declared(name)))
    eq("v4 graph: an unknown routine is not_found, not unparsed",
       res["graph_call_chain__empty__v4"].status, "not_found")
    eq("v4 graph: nothing unparsed on the envelope",
       [n for n in res if n.startswith("graph_") and n.endswith("__v4")
        and res[n].status == "unparsed"], [])
    page = json.loads(load("graph_call_chain__callers__v4"))
    page["total"] = page["returned"] + 5
    eq("v4 graph: a page shorter than total is reported, never passed off as whole",
       "of %d items" % page["total"] in (G.parse_call_chain(json.dumps(page, ensure_ascii=False),
                                                           "callers").note or ""), True)
    folded = res["graph_dossier__folded__v4"]
    eq("v4 graph dossier: typeless attributes and folded dependency lists are no drift",
       folded.drift, [])
    eq("v4 graph dossier: a folded list says how much it left out",
       [n for n in (folded.note or "").split("; ") if "the dossier lists" in n],
       ["downstream: the dossier lists 50 of 59, the rest via usages",
        "upstream: the dossier lists 50 of 53, the rest via usages"])
    eq("v4 code: details by the qualified name keep every attribute",
       (res["code_metadata_details__ok__v4"].status,
        sum(1 for r in res["code_metadata_details__ok__v4"].records
            if r.owner == res["code_metadata_details__ok__v4"].resolved_id)),
       ("ok", len(json.loads(load("code_metadata_details__ok__v4"))["data"]["attributes"])))
    amb = res["code_metadata_details__ambiguous__v4"]
    eq("v4 code: an ambiguous bare name is not_found and names every candidate",
       (amb.status, len((amb.note or "").split("one of: ")[-1].split(", "))),
       ("not_found", len(json.loads(load("code_metadata_details__ambiguous__v4"))["data"]["candidates"])))

    # -- platform servers, images of 27.09.2026 ------------------------
    eq("v4 docinfo: an exact name gives one article",
       [r.id for r in res["platform_docinfo__ok__v4"].records], ["doc:ТаблицаЗначений.Найти"])
    eq("v4 docinfo: a miss is not_found, the nearest documents are not an answer",
       (res["platform_docinfo__missing__v4"].status,
        len(res["platform_docinfo__missing__v4"].records)), ("not_found", 0))
    # an ambiguous name -- overloads of one method, or several symbols -- comes
    # back as candidates without a body; each must say where its body is
    for name in ("platform_docinfo__variants__v4", "platform_docinfo__ambiguous__v4"):
        amb4 = res[name]
        eq("v4 docinfo %s: every bodiless candidate names its doc_id" % name.split("__")[1],
           sorted(amb4.fetch), sorted(r.id for r in amb4.records if not r.text))
        eq("v4 docinfo %s: the candidates are not lost" % name.split("__")[1],
           len(amb4.records), json.loads(load(name))["returned"])
    eq("v4 docinfo: a looked-up doc_id is the whole article, every variant",
       [("Из файла" in r.text and "Из потока" in r.text, not r.text.startswith(" "))
        for r in res["platform_docinfo__by_doc_id__v4"].records], [(True, True)])
    eq("v4 docinfo: the overloads' signatures are kept",
       res["platform_docinfo__variants__v4"].records[0].sig.count("Прочитать("), 2)
    ds4 = json.loads(load("platform_docsearch__ok__v4"))
    eq("v4 docsearch: one record per result",
       len(res["platform_docsearch__ok__v4"].records), len(ds4["results"]))
    syn4 = res["platform_syntax__issues__v4"]
    eq("v4 syntax: every diagnostic of the TOON table is read",
       (syn4.status, len(syn4.records)), ("ok", 5))
    eq("v4 syntax: the parse error keeps its 1-based line",
       [(r.name, r.loc.line) for r in syn4.records if r.owner == "Critical"], [("ParseError", 5)])
    eq("v4 syntax: quoted messages with escaped quotes survive",
       [r.text for r in syn4.records if r.name == "UnusedLocalMethod"],
       ['Неиспользуемый локальный метод "Тест"'])
    eq("v4 syntax: a clean module is empty, not unparsed",
       res["platform_syntax__clean__v4"].status, "empty")
    broken = load("platform_syntax__issues__v4").replace("diagnostics[5]", "diagnostics[6]")
    eq("v4 syntax: rows short of the header are unparsed, never clean",
       P.parse_syntax(broken).status, "unparsed")
    tpl4 = res["platform_templates__ok__v4"]
    eq("v4 templates: ids are the numbers get_template takes",
       [r.id for r in tpl4.records if not r.id[len("template:"):].isdigit()], [])
    eq("v4 templates: every template is found",
       len(tpl4.records), load("platform_templates__ok__v4").count("**Template:**"))
    eq("v4 templates: get_template JSON parses",
       [r.id for r in res["platform_template__one__v4"].records], ["template:4229"])

    # every record must validate against the schema
    bad = []
    for name, r in res.items():
        for rec in r.records:
            errs = rec.errors()
            if errs:
                bad.append(name + "/" + str(rec.id) + ": " + ", ".join(errs))
    checks.append((not bad, "schema validation: " + (", ".join(bad[:3]) if bad else "all records valid")))
    return checks


def main():
    update = "--update" in sys.argv
    res = run_all()
    snap = snapshot(res)

    if update:
        with io.open(EXPECTED, "w", encoding="utf-8", newline="\n") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1, sort_keys=True)
        print("expected.json re-baselined from " + str(len(snap)) + " fixtures")
        return 0

    failures = []
    print("== invariants")
    for ok, msg in invariants(res):
        print(("  ok   " if ok else "  FAIL ") + msg)
        if not ok:
            failures.append(msg)

    print("== snapshot")
    if not os.path.exists(EXPECTED):
        print("  FAIL expected.json missing -- run with --update after reviewing output")
        failures.append("expected.json missing")
    else:
        with io.open(EXPECTED, encoding="utf-8") as f:
            want = json.load(f)
        for name in sorted(snap):
            if name not in want:
                print("  FAIL " + name + ": absent from expected.json")
                failures.append(name)
            elif snap[name] != want[name]:
                a, b = want[name], snap[name]
                diff = [k for k in b if a.get(k) != b.get(k)]
                print("  FAIL " + name + ": differs in " + ", ".join(diff))
                failures.append(name)
            else:
                print("  ok   " + name + " (" + str(snap[name]["count"]) + " записей)")

    print()
    print(("FAILED: " + str(len(failures))) if failures else "все проверки зелёные")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
