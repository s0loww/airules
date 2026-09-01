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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "norm"))

from record import prune                      # noqa: E402
import graph_parsers as G                     # noqa: E402
import code_parsers as C                      # noqa: E402

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
    "graph_usages__ok":          G.parse_usages,
    "graph_usages__empty":       G.parse_usages,
    "graph_search_code__ok":     G.parse_search_code,
    "graph_dossier__ok":         G.parse_dossier,
    "code_call_hierarchy__ok":   lambda t: C.parse_call_hierarchy(t, "callers"),
    "code_search_function__ok":  C.parse_search_function,
    "code_metadata_details__ok": C.parse_metadata_details,
    "code_dependencies__reverse": lambda t: C.parse_dependencies(t, "reverse"),
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
    ds_attrs = sum(1 for r in ds.records if r.kind == "attribute")
    md_attrs = sum(1 for r in md.records if r.kind == "attribute")
    eq("dossier vs details: attribute count agrees", ds_attrs, md_attrs)

    # with the resolver supplying a canonical id, both backends agree on rel.to --
    # this is the precondition for merging their records at all
    CANON = "ДЕМО_ОбщегоНазначенияСервер.ОтправкаПочты"
    ch2 = C.parse_call_hierarchy(load("code_call_hierarchy__ok"), "callers", root_id=CANON)
    targets = {r.rel.to for r in list(cc.records) + list(ch2.records) if r.rel}
    eq("merged rel.to is canonical across backends", targets, {CANON})

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
