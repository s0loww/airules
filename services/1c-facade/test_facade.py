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


PLATFORM_PORTS = {"8003": "docs", "8002": "syntax", "8007": "codecheck", "8004": "templates"}
PLATFORM_REPLAY = {
    ("docs", "docinfo"): "platform_docinfo__ok",
    ("docs", "docsearch"): "platform_docsearch__ok",
    ("codecheck", "its_help"): "platform_its__ok",
    ("syntax", "syntaxcheck"): "platform_syntax__issues",
    ("templates", "templatesearch"): "platform_templates__ok",
    ("templates", "get_template"): "platform_template__one",
}


class ReplayClient(object):
    def __init__(self, url):
        self.kind = "graph" if "8013" in url else "code"
        for port, kind in PLATFORM_PORTS.items():
            if ":" + port + "/" in url:
                self.kind = kind
        self.calls = []

    def tools(self):
        if self.kind != "code":
            return []
        return [{"name": "verify_xml", "description": "Validate XML against XSD.",
                 "inputSchema": {"type": "object",
                                 "properties": {"xml": {"type": "string"}},
                                 "required": ["xml"]}}]

    def call(self, tool, args):
        self.calls.append(tool)
        CALLS.append((self.kind, tool, dict(args)))
        if (self.kind, tool) in PLATFORM_REPLAY:
            name = PLATFORM_REPLAY[(self.kind, tool)]
            if tool == "docinfo" and args.get("name") == "НетТакогоМетодаВообще":
                name = "platform_docinfo__missing"
            with io.open(os.path.join(FX, name + ".txt"), encoding="utf-8") as handle:
                return 0.01, "OK", handle.read()
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
    shared = registry_mod.Project(name=registry_mod.SHARED, source=None, backends={
        kind: registry_mod.Backend(kind, "http://127.0.0.1:%s/mcp" % port)
        for port, kind in PLATFORM_PORTS.items()})
    reg = registry_mod.Registry([registry_mod.Project(
        name="demo", source=SOURCE, aliases=("дем",), backends=backends)], shared=shared)
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

    # -- 0.2: pass-through of single-source backend tools --------------
    facade.registry.expose = {"code": ["verify_xml", "get_xsd_schema"]}
    listed = {t["name"]: t for t in facade.exposed_tools()}
    eq("a published tool with a known schema is listed", sorted(listed), ["code_verify_xml"])
    schema = listed["code_verify_xml"]["inputSchema"]
    ok("the backend schema is kept and gains a project argument",
       "xml" in schema["properties"] and "project" in schema["properties"],
       str(sorted(schema["properties"])))
    eq("the backend's required list survives", schema.get("required"), ["xml"])
    del CALLS[:]
    text, notes = facade.call_exposed("code_verify_xml", {"xml": "<a/>", "project": "дем"})
    eq("the call reaches the backend with the project argument stripped",
       CALLS[-1], ("code", "verify_xml", {"xml": "<a/>"}))
    try:
        facade.call_exposed("code_nope", {})
        out.append((False, "an unpublished tool must be refused"))
    except KeyError:
        out.append((True, "an unpublished tool is refused"))
    facade.registry.expose = {}

    # -- 0.2: platform verbs --------------------------------------------
    del CALLS[:]
    env = facade.docs("ТаблицаЗначений.Найти")
    eq("a name-shaped query goes to the exact lookup", [c[1] for c in CALLS], ["docinfo"])
    eq("and comes back as that article", [r.id for r in env.records],
       ["doc:ТаблицаЗначений.Найти"])
    del CALLS[:]
    env = facade.docs("НетТакогоМетодаВообще")
    eq("an unknown name falls back to the search",
       [c[1] for c in CALLS], ["docinfo", "docsearch"])
    ok("the fallback is said", any("no article named" in n for n in env.coverage.notes),
       str(env.coverage.notes))
    del CALLS[:]
    env = facade.docs("как найти строку в таблице", scope="any")
    eq("scope=any asks documentation and ITS at once",
       sorted(c[1] for c in CALLS), ["docsearch", "its_help"])
    ok("the missing relevance threshold is flagged",
       any("threshold" in n for n in env.coverage.notes), str(env.coverage.notes))

    env = facade.lint(code="Процедура А()\nКонецПроцедуры")
    ok("lint(syntax) returns located diagnostics",
       env.records and all(r.loc and r.loc.line for r in env.records),
       str(len(env.records)))
    env = facade.lint(path="../../outside.bsl", project="demo")
    ok("lint refuses a path outside the export",
       any("inside the project" in n for n in env.coverage.notes), str(env.coverage.notes))
    del CALLS[:]
    env = facade.lint(path="CommonModules/ДЕМО_ОбменДанными/Ext/Module.bsl", project="demo")
    eq("lint reads a module of the export and sends its code",
       [c[1] for c in CALLS], ["syntaxcheck"])
    ok("diagnostics carry the module path",
       all(r.loc.path == "CommonModules/ДЕМО_ОбменДанными/Ext/Module.bsl"
           for r in env.records if r.loc), str([r.loc.path for r in env.records][:2]))

    env = facade.template(query="остатки регистра")
    ok("template search returns templates",
       env.records and all(r.id.startswith("template:") for r in env.records))
    eq("one template by id", [r.id for r in facade.template(id="1").records], ["template:1"])

    env = facade.status()
    ok("status lists the platform servers",
       {"shared/docs", "shared/syntax", "shared/codecheck", "shared/templates"}
       <= {b["name"] for b in env.coverage.backends},
       str([b["name"] for b in env.coverage.backends]))

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
