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
from health import BackendStatus, indexing_now   # noqa: E402
from resolver import Resolver, owner_of          # noqa: E402
from verbs import Facade, grep_usages            # noqa: E402
from envelope import Envelope                    # noqa: E402
from record import Record                        # noqa: E402
import sqlite3                                   # noqa: E402
import tempfile                                  # noqa: E402

FX = os.path.join(HERE, "fixtures")
SOURCE = os.path.join(FX, "source")
SOURCE_EXT = os.path.join(FX, "source_ext")      # an extension over SOURCE
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


DOCINFO_REPLAY = {
    "НетТакогоМетодаВообще": "platform_docinfo__missing",
    "ТабличныйДокумент.Прочитать": "platform_docinfo__variants__v4",
    "Формат": "platform_docinfo__ambiguous__v4",
}
# doc_ids the documentation server answers with nothing -- a body that cannot
# be fetched must not pass for an article
EMPTY_DOC_IDS = set()


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
            if tool == "docinfo":
                asked = args.get("name") or ""
                if asked in EMPTY_DOC_IDS:
                    return 0.01, "EMPTY", ""
                name = DOCINFO_REPLAY.get(asked, name)
                if asked.endswith(".html"):
                    name = "platform_docinfo__by_doc_id__v4"
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


def build_group(scope_resolvers=None):
    """A base without backends plus one extension with a code backend -- the
    shape of a real ERP fleet, where the host has no containers of its own."""
    path = os.path.join(tempfile.mkdtemp(), "registry.json")
    with io.open(path, "w", encoding="utf-8") as handle:
        json.dump({"version": 2, "default": "base", "projects": {
            "base": {"source": SOURCE, "backends": {}, "extensions": {
                "ext": {"source": SOURCE_EXT, "backends": {
                    "code": {"url": "http://127.0.0.1:8012/mcp"}}}}},
            "solo": {"source": SOURCE, "backends": {
                "code": {"url": "http://127.0.0.1:8012/mcp"}}},
        }}, handle, ensure_ascii=False)
    reg = registry_mod.load(path)
    resolvers = {}
    for name, source in (("base", SOURCE), ("ext", SOURCE_EXT), ("solo", SOURCE)):
        resolvers[name] = Resolver(source)
        resolvers[name].build()
    return Facade(reg, AlwaysUpHealth(), ReplayClient,
                  resolver_factory=lambda project: resolvers[project.name])


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
    del CALLS[:]
    facade.find("отправка почты")
    eq("find(kind=any): a phrase is no routine name -- straight to the text search",
       sorted(c[1] for c in CALLS), ["codesearch", "search_code"])

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
    # an ambiguous name answers with bodiless candidates: the facade fetches
    # each body by its doc_id instead of handing back text=""
    del CALLS[:]
    env = facade.docs("ТабличныйДокумент.Прочитать")
    eq("overloads of one method are one article", [r.id for r in env.records],
       ["doc:ТабличныйДокумент.Прочитать"])
    ok("the article carries every syntax variant",
       all(v in (env.records[0].text or "") for v in ("Из файла", "Из потока")),
       repr((env.records[0].text or "")[:80]))
    eq("the body is fetched by doc_id", [c[1] for c in CALLS], ["docinfo", "docinfo"])
    eq("and the answer is not degraded", env.coverage.degraded, False)
    env = facade.docs("Формат")
    eq("several symbols: every candidate carries a text",
       [bool(r.text) for r in env.records], [True] * 5)
    ok("several symbols: the ambiguity is said",
       any("23" in n for n in env.coverage.notes), str(env.coverage.notes))
    EMPTY_DOC_IDS.add("objects/catalog63/catalog64/SpreadsheetDocument/methods/Read71.html")
    env = facade.docs("ТабличныйДокумент.Прочитать")
    EMPTY_DOC_IDS.clear()
    ok("a body that cannot be fetched is degraded, not an empty article",
       env.coverage.degraded and any("no text" in n for n in env.coverage.notes),
       str(env.coverage.as_dict()))
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

    # -- 0.2: base + extensions ----------------------------------------
    ext_resolver = Resolver(SOURCE_EXT)
    ext_resolver.build()
    rows = {(o, t, m, d) for o, t, m, d, _p, _l in ext_resolver.overrides()}
    eq("the extension's interceptions are indexed", rows, {
        ("ДЕМО_ОбщегоНазначенияСервер", "ОтправкаПочты", "РАСШ_ОтправкаПочты", "Вместо"),
        ("Справочники.ДоговорыКонтрагентов", "ОбработкаЗаполнения",
         "РАСШ_ОбработкаЗаполненияПосле", "После")})

    stored = os.path.join(tempfile.mkdtemp(), "index.sqlite")
    old = Resolver(SOURCE_EXT, stored)
    old.build()
    old.close()
    raw = sqlite3.connect(stored)
    raw.execute("PRAGMA user_version = 1")
    raw.execute("DELETE FROM overrides")
    raw.commit()
    raw.close()
    reopened = Resolver(SOURCE_EXT, stored)
    eq("a stored index of an older schema is flagged", reopened.stale_schema, True)
    reopened.build()
    eq("and rebuilt, filling the new table", len(reopened.overrides()), 2)

    group = build_group()
    eq("v2 registry: an extension knows its base", group.registry.get("ext").parent, "base")
    eq("v2 registry: the base lists its extensions", group.registry.get("base").extensions,
       ["ext"])
    eq("v2 registry: a plain project stays ungrouped", group.registry.get("solo").grouped,
       False)

    env = group.find("ОтправкаПочты", project="base", kind="routine")
    scopes = {(r.id, r.scope) for r in env.records if r.src and r.src.backend == "resolver"}
    ok("base scope=all finds the routine in the base and the extension's namesake",
       ("ДЕМО_ОбщегоНазначенияСервер.ОтправкаПочты", "base") in scopes
       and ("РАСШ_ОбщийСервер.ОтправкаПочты", "ext:ext") in scopes, str(sorted(scopes)))
    base_rec = [r for r in env.records
                if r.id == "ДЕМО_ОбщегоНазначенияСервер.ОтправкаПочты" and r.scope == "base"]
    eq("the intercepted base routine names its interceptor",
       base_rec[0].overridden_by if base_rec else None,
       ["ext:ext &Вместо РАСШ_ОтправкаПочты"])
    namesake = [r for r in env.records if r.id == "РАСШ_ОбщийСервер.ОтправкаПочты"]
    eq("a namesake in the extension's own module is not an interception",
       [r.overridden_by for r in namesake], [None])
    ok("the base without backends is said once, not as a failure",
       any("base: бэкендов нет" in n for n in env.coverage.notes)
       and all(b["state"] == "up" for b in env.coverage.backends),
       json.dumps(env.coverage.as_dict(), ensure_ascii=False)[:300])
    eq("backends are labelled by unit", {b["name"] for b in env.coverage.backends},
       {"ext:ext/code"})

    env = group.find("ОбработкаЗаполнения", project="base", kind="routine", scope="base")
    eq("scope=base asks the base only", {r.scope for r in env.records}, {"base"})
    marked = {r.id: r.overridden_by for r in env.records if r.overridden_by}
    eq("interception is marked even when the extension is out of scope", marked,
       {"Справочники.ДоговорыКонтрагентов.ОбработкаЗаполнения":
        ["ext:ext &После РАСШ_ОбработкаЗаполненияПосле"]})

    env = group.find("РАСШ_ПроверитьДоговор", project="ext", kind="routine")
    eq("an extension's routine comes from the extension",
       {r.scope for r in env.records if r.src and r.src.backend == "resolver"}, {"ext:ext"})
    ok("an extension's default scope brings its base along",
       any(n.startswith("base:") for n in env.coverage.notes), str(env.coverage.notes))
    try:
        group.find("x", project="base", scope="solo")
        out.append((False, "a scope outside the group must be refused"))
    except KeyError:
        out.append((True, "a scope outside the group is refused"))

    env = group.calls("ОтправкаПочты", project="base")
    eq("calls asked of the base resolves in the base first",
       env.coverage.resolved_id, "ДЕМО_ОбщегоНазначенияСервер.ОтправкаПочты")
    env = group.calls("ОтправкаПочты", project="ext")
    eq("calls asked of the extension resolves in the extension first",
       env.coverage.resolved_id, "РАСШ_ОбщийСервер.ОтправкаПочты")

    env = group.usages("Справочники.ДоговорыКонтрагентов", project="base", where="code")
    eq("usages in code come from every unit", {r.scope for r in env.records},
       {"base", "ext:ext"})

    ordered = Envelope("order")
    ordered.records = [Record(id="X.Y", kind="routine", name="Y", scope="base"),
                       Record(id="Z", kind="routine", name="Z", scope="base"),
                       Record(id="X.Y", kind="routine", name="Y", scope="ext:e")]
    ordered.dedupe()
    Facade._order(ordered)
    eq("same id: the extension's record goes above the base's, both kept",
       [(r.id, r.scope) for r in ordered.records],
       [("X.Y", "ext:e"), ("X.Y", "base"), ("Z", "base")])

    # a base still indexing must not hold its extension's answers hostage
    warming = build_group()
    gate = threading.Lock()
    warming._building["base"] = gate
    warming._resolvers.pop("base", None)
    with gate:
        started = time.time()
        env = warming.find("РАСШ_ПроверитьДоговор", project="ext", kind="routine")
        took = time.time() - started
    ok("an extension answers while its base is still indexing", took < 2.0,
       "%.2fs" % took)
    ok("the skipped base is named and the answer marked incomplete",
       env.coverage.degraded and any("base: индекс строится" in n
                                     for n in env.coverage.notes),
       str(env.coverage.notes))
    eq("the extension's part still arrives",
       {r.scope for r in env.records if r.src and r.src.backend == "resolver"}, {"ext:ext"})

    env = group.find("ОтправкаПочты", project="solo", kind="routine")
    eq("an ungrouped project's records carry no scope", {r.scope for r in env.records}, {None})

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

    # -- graph pages ----------------------------------------------------
    class PagedGraph(object):
        """A graph 4.x cutting its answer in two pages behind a cursor."""
        def __init__(self, _url):
            self.asked = []

        def call(self, tool, args):
            self.asked.append(dict(args))
            head = {"contract_version": "2.0", "total": 3}
            if "cursor" not in args:
                body = dict(head, returned=2, cursor="p2",
                            text="Цепочка вызовов 'Х (М)' (direction=callers, depth=1) — 3 процедур:\n\n"
                                 "  Глубина 1:\n    - А (М / CommonModule)\n    - Б (М / CommonModule)\n")
            else:
                body = dict(head, returned=1, cursor=None, text="    - В (М / CommonModule)\n")
            return 0.0, "OK", json.dumps(body, ensure_ascii=False)

    paged_backend = registry_mod.Backend("graph", "http://paged.invalid/mcp/")
    paged = Facade(facade.registry, AlwaysUpHealth(), PagedGraph)
    elapsed, outcome, text = paged._call_paged(paged_backend, "graph", "trace_call_chain", {"routine_name": "Х"})
    joined = json.loads(text)
    eq("graph pages behind a cursor are followed and joined",
       (joined["returned"], joined["total"], joined["text"].count("    - ")), (3, 3, 3))
    eq("the continuation is asked with the cursor and the original arguments",
       paged.client(paged_backend).asked[-1], {"routine_name": "Х", "cursor": "p2"})

    # -- expired sessions -----------------------------------------------
    import urllib.error
    import mcp_client
    live = {"session": None, "opened": 0}

    def fake_post(url, payload, session_id=None, timeout=120):
        if payload["method"] == "initialize":
            live["opened"] += 1
            live["session"] = "s%d" % live["opened"]
            return live["session"], {"result": {}}
        if session_id != live["session"]:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return None, {"result": {"content": [{"type": "text", "text": "ok"}]}}

    real_post, mcp_client._post = mcp_client._post, fake_post
    try:
        client = mcp_client.Client("http://expiring.invalid/mcp")
        live["session"] = "dropped-by-idle-ttl"          # the server forgot it
        _, status, text = client.call("any", {})
        eq("an expired session is reopened and the call answered, not a 404",
           (status, text, live["opened"]), ("OK", "ok", 2))
    finally:
        mcp_client._post = real_post

    # -- index state of backends --------------------------------------
    alive_loop = json.dumps({"contract_version": "2.0", "data": {
        "any_running": False, "source_refresh": {"enabled": True, "running": True}}})
    eq("graph 4.x: a live re-scan loop is not a pass in progress",
       indexing_now(alive_loop), False)
    eq("graph 4.x: an explicit any_running is believed",
       indexing_now(alive_loop.replace('"any_running": false', '"any_running": true')), True)
    eq("older replies keep the plain match", indexing_now('{"reindex": {"running": true}}'), True)

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
