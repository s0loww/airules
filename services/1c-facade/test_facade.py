"""Gate for the resolver, the registry and the six verbs.

No live backend is involved: the verbs are driven by a replaying client that
serves the committed fixtures, and the resolver runs over the synthetic export
in `fixtures/source/`. That corpus is small but reproduces the defect the whole
design turns on -- two routines named `ОтправкаПочты`, one exported and one
not -- so name resolution is tested against ambiguity rather than a happy path.

    python test_facade.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "norm"))

import registry as registry_mod                  # noqa: E402
from health import BackendStatus                 # noqa: E402
from resolver import Resolver, owner_of          # noqa: E402
from verbs import Facade, grep_usages            # noqa: E402

FX = os.path.join(HERE, "fixtures")
SOURCE = os.path.join(FX, "source")
CANON = "ДЕМО_ОбщегоНазначенияСервер.ОтправкаПочты"


def fixture(name):
    ext = "json" if name.startswith("code_") else "txt"
    with io.open(os.path.join(FX, name + "." + ext), encoding="utf-8") as handle:
        return handle.read()


# Which fixture answers which backend call.
REPLAY = {
    ("graph", "trace_call_chain"): "graph_call_chain__callers",
    ("graph", "find_usages_of_object"): "graph_usages__ok",
    ("graph", "search_code"): "graph_search_code__ok",
    ("graph", "get_object_dossier"): "graph_dossier__ok",
    ("code", "get_method_call_hierarchy"): "code_call_hierarchy__ok",
    ("code", "search_function"): "code_search_function__ok",
    ("code", "get_metadata_details"): "code_metadata_details__ok",
    ("code", "graph_dependencies"): "code_dependencies__reverse",
    ("code", "codesearch"): "code_search_function__ok",
    ("code", "metadatasearch"): "code_metadata_details__ok",
}


class ReplayClient(object):
    def __init__(self, url):
        self.kind = "graph" if "8013" in url else "code"
        self.calls = []

    def call(self, tool, args):
        self.calls.append(tool)
        name = REPLAY.get((self.kind, tool))
        if name is None:
            return 0.0, "EMPTY", ""
        return 0.01, "OK", fixture(name)


class AlwaysUpHealth(object):
    """Backends answer; no docker is touched during the gate."""

    def __init__(self, state="up", index_age_s=120):
        self.state = state
        self.index_age_s = index_age_s

    def probe(self, backend):
        return BackendStatus(backend.kind, self.state, ms=10,
                             index_age_s=self.index_age_s)

    def ensure(self, backend, **_kwargs):
        return self.probe(backend)


def build_facade(health=None):
    reg = registry_mod.Registry([registry_mod.Project(
        name="demo", source=SOURCE, aliases=("дем",),
        backends={
            "code": registry_mod.Backend("code", "http://127.0.0.1:8012/mcp"),
            "graph": registry_mod.Backend("graph", "http://127.0.0.1:8013/mcp/"),
        })])
    resolver = Resolver(SOURCE)
    resolver.build()
    return Facade(reg, health or AlwaysUpHealth(), ReplayClient,
                  resolver_factory=lambda _project: resolver)


def checks():
    out = []

    def eq(label, got, want):
        out.append((got == want, label + ": got " + repr(got) + ", want " + repr(want)))

    def ok(label, condition, detail=""):
        out.append((bool(condition), label + (": " + detail if detail else "")))

    # -- resolver ------------------------------------------------------
    resolver = Resolver(SOURCE)
    counts = resolver.build()
    eq("resolver indexes the corpus", counts["new"], 6)
    eq("second build is fully incremental", resolver.build()["unchanged"], 6)

    stats = resolver.stats()
    ok("resolver found symbols", stats["symbols"] >= 10, str(stats))

    # the defect the design turns on: two routines share a bare name
    ambiguous = resolver.resolve("ОтправкаПочты")
    eq("bare name prefers the exported one", ambiguous.id, CANON)
    eq("both homonyms are reported", len(ambiguous.candidates), 2)
    eq("qualified name resolves exactly", resolver.resolve(CANON).confidence, "exact")
    eq("unknown name resolves to nothing", resolver.resolve("НетТакого").id, None)

    # genuinely undecidable: three ОбработкаЗаполнения, none exported
    spread = resolver.resolve("ОбработкаЗаполнения")
    eq("undecidable name stays undecided", spread.confidence, "ambiguous")
    ok("undecidable name lists candidates", len(spread.candidates) >= 3,
       str(spread.candidates))

    # owners are canonical per container
    eq("common module owner",
       owner_of("CommonModules/ДЕМО_ОбменДанными/Ext/Module.bsl"), "ДЕМО_ОбменДанными")
    eq("catalog object owner",
       owner_of("Catalogs/ДоговорыКонтрагентов/Ext/ObjectModule.bsl"),
       "Справочники.ДоговорыКонтрагентов")
    eq("form owner",
       owner_of("Catalogs/ДоговорыКонтрагентов/Forms/ФормаЭлемента/Ext/Form/Module.bsl"),
       "Справочники.ДоговорыКонтрагентов.Форма.ФормаЭлемента")

    # -- registry ------------------------------------------------------
    facade = build_facade()
    eq("project resolves by alias", facade.registry.get("дем").name, "demo")
    eq("no name means the default project", facade.registry.get(None).name, "demo")
    try:
        facade.registry.get("нет-такого")
        out.append((False, "unknown project must raise"))
    except KeyError:
        out.append((True, "unknown project raises with the known list"))

    # -- calls ---------------------------------------------------------
    env = facade.calls("ОтправкаПочты")
    eq("calls returns the full caller set", len(env.records), 8)
    eq("calls resolves before asking", env.coverage.resolved_id, CANON)
    targets = {r.rel.to for r in env.records if r.rel}
    eq("every caller points at the canonical id", targets, {CANON})
    ok("calls reports the backend it used",
       any(b["name"] == "graph" for b in env.coverage.backends),
       json.dumps(env.coverage.backends, ensure_ascii=False))

    env = facade.calls("НетТакогоМетода")
    eq("unresolved name yields no records", len(env.records), 0)
    ok("unresolved name is explained",
       any("unresolved" in n for n in env.coverage.notes), str(env.coverage.notes))

    # -- usages --------------------------------------------------------
    env = facade.usages("Справочники.ДоговорыКонтрагентов", where="metadata")
    ok("metadata usages merge both backends", len(env.records) >= 26, str(len(env.records)))
    backends = {r.src.backend for r in env.records if r.src}
    eq("both backends contributed", backends, {"graph", "code"})

    env = facade.usages("Справочники.ДоговорыКонтрагентов", where="code")
    eq("code usages are found at all", len(env.records), 4)
    eq("they are tiered below an index",
       {r.src.tier for r in env.records if r.src}, {"grep"})
    eq("they are attributed to the resolver, not a backend",
       {r.src.backend for r in env.records if r.src}, {"resolver"})
    ok("their provenance is stated",
       any("reference index" in n or "filesystem scan" in n
           for n in env.coverage.notes), str(env.coverage.notes))
    ok("every hit carries a location",
       all(r.loc and r.loc.path and r.loc.line for r in env.records))

    # -- describe ------------------------------------------------------
    env = facade.describe("Справочники.ДоговорыКонтрагентов")
    consulted = {b["name"] for b in env.coverage.backends}
    eq("describe consults both backends", consulted, {"graph", "code"})
    ok("describe dedupes rather than concatenates",
       0 < len(env.records) < 75 + 19,
       "%d records out of 75 + 19 inputs" % len(env.records))
    attribute_ids = [r.id for r in env.records if r.kind == "attribute"]
    eq("each attribute survives exactly once",
       len(attribute_ids), len(set(attribute_ids)))

    # -- degraded path -------------------------------------------------
    cold = build_facade(AlwaysUpHealth(state="cold"))
    env = cold.calls("ОтправкаПочты")
    eq("a cold backend yields no records", len(env.records), 0)
    eq("a cold backend is reported as degraded", env.coverage.degraded, True)
    eq("the cold state is named", env.coverage.backends[0]["state"], "cold")
    ok("resolution still works with backends down",
       env.coverage.resolved_id == CANON, str(env.coverage.resolved_id))

    # -- envelope shape ------------------------------------------------
    payload = facade.calls("ОтправкаПочты").as_dict()
    ok("envelope serialises", "records" in payload and "coverage" in payload,
       ", ".join(sorted(payload)))
    ok("envelope is JSON-clean", bool(json.dumps(payload, ensure_ascii=False)))

    # -- grep helper ---------------------------------------------------
    hits = grep_usages(SOURCE, "Справочники.ДоговорыКонтрагентов")
    eq("grep matches through access prefixes", len(hits), 4)

    return out


def main():
    failures = []
    for good, message in checks():
        print(("  ok   " if good else "  FAIL ") + message)
        if not good:
            failures.append(message)
    print()
    print(("FAILED: " + str(len(failures))) if failures else "все проверки зелёные")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
