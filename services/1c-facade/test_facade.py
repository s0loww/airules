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
import threading
import time

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
    ("code", "codesearch"): "code_codesearch__ok",
    ("code", "metadatasearch"): "code_metadatasearch__names",
    ("code", "search_forms"): "code_search_forms__ok",
    ("code", "inspect_form_layout"): "code_form_layout__ok",
    ("code", "get_module_structure"): "code_module_structure__ok",
}

# every backend call made by any ReplayClient, for asserting routes
CALLS = []


class ReplayClient(object):
    def __init__(self, url):
        self.kind = "graph" if "8013" in url else "code"
        self.calls = []

    def call(self, tool, args):
        self.calls.append(tool)
        CALLS.append((self.kind, tool, dict(args)))
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


def build_facade(health=None, graph=True, resolver_factory=None):
    backends = {"code": registry_mod.Backend("code", "http://127.0.0.1:8012/mcp")}
    if graph:
        backends["graph"] = registry_mod.Backend("graph", "http://127.0.0.1:8013/mcp/")
    reg = registry_mod.Registry([registry_mod.Project(
        name="demo", source=SOURCE, aliases=("дем",), backends=backends)])
    if resolver_factory is None:
        resolver = Resolver(SOURCE)
        resolver.build()
        resolver_factory = lambda _project: resolver     # noqa: E731
    return Facade(reg, health or AlwaysUpHealth(), ReplayClient,
                  resolver_factory=resolver_factory)


class SlowReplayClient(ReplayClient):
    """Each call takes a fixed time -- to tell a parallel fan-out from a serial one."""

    DELAY = 0.3

    def call(self, tool, args):
        time.sleep(self.DELAY)
        return ReplayClient.call(self, tool, args)


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

    # -- 0.2: find(kind=form | metadata | text) ------------------------
    env = facade.find("договор", kind="form")
    ok("find(kind=form) answers with forms",
       env.records and all(r.kind == "form" for r in env.records),
       str([r.kind for r in env.records]))
    env = facade.find("ДоговорыКонтрагентов", kind="metadata")
    eq("find(kind=metadata) is parsed, not a raw blob",
       [r.id for r in env.records], ["Справочники.ДоговорыКонтрагентов"])
    env = facade.find("отправка почты", kind="text")
    eq("find(kind=text) merges both rankers",
       {r.src.backend for r in env.records if r.src}, {"graph", "code"})
    eq("parallel fan-out reports coverage in request order",
       [b["name"] for b in env.coverage.backends], ["graph", "code"])

    slow = Facade(facade.registry, AlwaysUpHealth(), SlowReplayClient,
                  resolver_factory=lambda _p: facade.resolver(facade.registry.get()))
    started = time.time()
    slow.find("отправка почты", kind="text")
    took = time.time() - started
    ok("the text fan-out runs concurrently", took < 2 * SlowReplayClient.DELAY,
       "%.2fs for two %.1fs calls" % (took, SlowReplayClient.DELAY))

    # -- 0.2: describe a form, a module --------------------------------
    del CALLS[:]
    env = facade.describe("Справочники.ДоговорыКонтрагентов.Форма.ФормаЭлемента")
    tools = [c[1] for c in CALLS]
    ok("describe(form) asks for the layout", "inspect_form_layout" in tools, str(tools))
    ok("describe(form) asks for its module", "get_module_structure" in tools, str(tools))
    ok("describe(form) skips the object dossier", "get_object_dossier" not in tools, str(tools))
    module_args = [c[2] for c in CALLS if c[1] == "get_module_structure"]
    eq("module path is absolute inside the backend",
       module_args[0]["module_path"],
       "/app/code/Catalogs/ДоговорыКонтрагентов/Forms/ФормаЭлемента/Ext/Form/Module.bsl")
    ok("the layout's elements come back",
       any(r.kind == "element" for r in env.records), str(len(env.records)))

    del CALLS[:]
    facade.describe("ДЕМО_ОбщегоНазначенияСервер")
    ok("a bare common-module name gets its structure",
       "get_module_structure" in [c[1] for c in CALLS], str(CALLS))

    # -- 0.2: calls falls back to code when graph cannot answer --------
    no_graph = build_facade(graph=False)
    env = no_graph.calls("ОтправкаПочты")
    eq("calls without graph answers from code", len(env.records), 2)
    eq("the fallback is flagged degraded", env.coverage.degraded, True)
    ok("the fallback is explained",
       any("code backend" in n for n in env.coverage.notes), str(env.coverage.notes))
    eq("fallback records still point at the canonical id",
       {r.rel.to for r in env.records if r.rel}, {CANON})
    env = facade.calls("ОтправкаПочты")
    ok("with graph up, code is not asked",
       all(b["name"] != "code" for b in env.coverage.backends),
       str(env.coverage.backends))

    # -- 0.2: status(reindex) reaches the backend ----------------------
    del CALLS[:]
    facade.status(reindex=True)
    ok("reindex reaches the code backend",
       ("code", "reindex") in [(c[0], c[1]) for c in CALLS], str(CALLS))

    # -- 0.2: concurrent first use builds the resolver once ------------
    built = []

    def counting_factory(project):
        built.append(project.name)
        time.sleep(0.3)
        r = Resolver(SOURCE)
        r.build()
        return r

    racing = build_facade(resolver_factory=counting_factory)
    threads = [threading.Thread(target=racing.find, args=("ОтправкаПочты",))
               for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    eq("four concurrent callers build the index once", len(built), 1)

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
