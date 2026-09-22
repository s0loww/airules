"""The six verbs.

Everything measured about the backends is encoded here as routing, so the
choice stops being something a model makes from prose descriptions:

    find(kind=routine)     code_metadata     0.1s with a full body vs 4.9s
    find(kind=metadata)    code_metadata     0.1s vs 7.1s
    find(kind=form)        code_metadata     the only index of forms
    find(kind=text)        both, union       outputs overlap by 3%
    describe               graph + code      dossier is richer; code adds types
    describe(form|module)  code_metadata     layout / structure, nobody else has it
    calls                  resolve -> graph  8 of 8 vs 2 of 8 and a false hit;
                           code as fallback  only when graph cannot answer at all
    usages(where=metadata) both, union       they answer different questions
    usages(where=code)     grep              no index covers it at all
    check                  external CLI      rules live in the distribution

Fan-out is selective on purpose. On `find(kind=text)` it nearly doubles recall
for free, because the two rankers barely agree and run concurrently. On `calls`
it would add a known false record, and on `find(kind=metadata)` it would cost a
seventy-fold slowdown to add nothing.
"""
import json
import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import code_parsers
import graph_parsers
from envelope import Envelope
from record import Loc, Record, Src
from resolver import Resolver, read_source


class Facade(object):
    def __init__(self, registry, health, client_factory, resolver_factory=None):
        self.registry = registry
        self.health = health
        self.client_factory = client_factory
        self.resolver_factory = resolver_factory or self._default_resolver
        self._clients = {}
        self._resolvers = {}
        # Calls run concurrently (the dispatcher no longer serialises them), so
        # the lazily filled caches need a lock -- and building a resolver needs
        # one per project: indexing a full ERP export takes a minute, and two
        # callers arriving together must not both pay for it.
        self._lock = threading.Lock()
        self._building = {}

    # -- plumbing ---------------------------------------------------------

    @staticmethod
    def _index_path(project):
        """Where a project's index lives, or None to keep it in memory.

        A full ERP base is 25 000 modules and takes about a minute to index;
        paying that on every restart is not worth the simplicity of an in-memory
        database. The index already tracks files by content hash, so reopening a
        stored one costs a rescan of hashes rather than a rebuild.
        """
        state = os.environ.get("FACADE_STATE")
        directory = os.path.dirname(state) if state else None
        if not directory or not os.path.isdir(directory):
            return None
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", project.name)
        return os.path.join(directory, "index-%s.sqlite" % safe)

    @classmethod
    def _default_resolver(cls, project):
        path = cls._index_path(project)
        try:
            resolver = Resolver(project.source, path or ":memory:")
        except Exception:                            # noqa: BLE001 - unwritable
            resolver = Resolver(project.source)
        if project.frozen and resolver.stats()["files"]:
            return resolver                          # snapshot, index already stored
        resolver.build()
        return resolver

    def resolver(self, project):
        with self._lock:
            ready = self._resolvers.get(project.name)
            if ready is not None:
                return ready
            gate = self._building.setdefault(project.name, threading.Lock())
        with gate:
            with self._lock:
                ready = self._resolvers.get(project.name)
            if ready is not None:
                return ready                         # built while we waited
            built = self.resolver_factory(project)
            with self._lock:
                self._resolvers[project.name] = built
            return built

    def client(self, backend):
        with self._lock:
            client = self._clients.get(backend.url)
        if client is None:
            # opening a session is a network round trip: outside the lock
            client = self.client_factory(backend.url)
            if hasattr(client, "timeout"):
                client.timeout = backend.timeout
            with self._lock:
                client = self._clients.setdefault(backend.url, client)
        return client

    def _query(self, project, kind, tool, args):
        """Call one backend. Returns (text or None, coverage events).

        Coverage is returned as events rather than written straight into an
        envelope so that parallel calls can report in a fixed order: the same
        question gives the same coverage block however the threads interleave.
        """
        events = []
        backend = project.backend(kind)
        if backend is None:
            events.append(("backend", (kind, "down"), {"detail": "not in registry"}))
            return None, events
        status = self.health.ensure(backend)
        if not status.usable:
            events.append(("backend", (kind, status.state), {"detail": status.detail}))
            # `degraded` without a reason is just an alarm; name what is missing,
            # so the caller can tell a thin answer from a complete one
            events.append(("note",
                           "backend %s is %s%s — the answer is incomplete"
                           % (kind, status.state,
                              ": " + status.detail if status.detail else "")))
            return None, events
        try:
            elapsed, outcome, text = self.client(backend).call(tool, args)
        except Exception as exc:                     # noqa: BLE001 - session open
            events.append(("backend", (kind, "down"), {"detail": type(exc).__name__}))
            events.append(("note", "%s.%s: no session — %s" % (kind, tool, exc)))
            events.append(("degraded",))
            return None, events
        events.append(("backend", (kind, "up"),
                       {"ms": elapsed * 1000, "index_age_s": status.index_age_s,
                        "detail": "индексируется" if status.indexing else None}))
        if status.indexing:
            # answering but still building: an empty result here means "not yet",
            # not "not there"
            events.append(("note",
                           "бэкенд %s перестраивает индекс — пустой ответ означает "
                           "«ещё нет», а не «нет такого»" % kind))
            events.append(("degraded",))
        if outcome in ("ERR", "FAIL"):
            events.append(("note", "%s.%s failed: %s" % (kind, tool, text[:120])))
            events.append(("degraded",))
            return None, events
        return text, events

    @staticmethod
    def _apply(envelope, events):
        for event in events:
            if event[0] == "backend":
                envelope.coverage.add_backend(*event[1], **event[2])
            elif event[0] == "note":
                envelope.coverage.note(event[1])
            elif event[0] == "degraded":
                envelope.coverage.degraded = True

    def _ask(self, envelope, project, kind, tool, args):
        """Call one backend, recording liveness in coverage. None on failure."""
        text, events = self._query(project, kind, tool, args)
        self._apply(envelope, events)
        return text

    def _ask_many(self, envelope, project, requests):
        """Several backends at once: the wall time is the slowest one, not the
        sum. Coverage is applied in request order once all have answered."""
        if len(requests) == 1:
            return [self._ask(envelope, project, *requests[0])]
        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            futures = [pool.submit(self._query, project, kind, tool, args)
                       for kind, tool, args in requests]
            results = [future.result() for future in futures]
        texts = []
        for text, events in results:
            self._apply(envelope, events)
            texts.append(text)
        return texts

    def _resolve(self, envelope, project, name, required=True):
        resolution = self.resolver(project).resolve(name)
        envelope.coverage.resolved_id = resolution.id
        envelope.coverage.candidates = resolution.candidates
        if resolution.candidates and resolution.confidence == "ambiguous":
            envelope.coverage.note(
                "name is ambiguous; pass a qualified id to pick one")
        if not resolution.ok and required:
            envelope.coverage.note("unresolved name: " + str(name))
        return resolution

    # -- verbs ------------------------------------------------------------

    def find(self, query, project=None, kind="any", exact=False, limit=20):
        project = self.registry.get(project)
        envelope = Envelope("find(%r, kind=%s)" % (query, kind))

        if kind in ("routine", "any"):
            # The resolver is authoritative here: it holds every declaration in
            # the export, while the backend's function search has measured gaps.
            # The backend is still asked -- it carries the body -- and the two
            # merge field by field, so a hit missing from one survives via the
            # other.
            for qual, owner, path, line, export in self.resolver(project).symbols(
                    query, exact=bool(exact), limit=limit):
                envelope.records.append(Record(
                    id=qual, kind="routine", name=qual.rsplit(".", 1)[-1],
                    owner=owner, loc=Loc(path=path, line=line),
                    text="Экспорт" if export else None,
                    src=Src(backend="resolver", tool="symbols", tier="indexed")))
            text = self._ask(envelope, project, "code", "search_function",
                             {"name": query, "exact": bool(exact), "limit": limit})
            if text:
                envelope.merge(code_parsers.parse_search_function(text), "code")
            if envelope.records or kind == "routine":
                return envelope.dedupe()

        if kind == "metadata":
            text = self._ask(envelope, project, "code", "metadatasearch",
                             {"query": query, "limit": limit})
            if text:
                envelope.merge(code_parsers.parse_metadatasearch(text), "code")
            return envelope.dedupe()

        if kind == "form":
            # the only index of forms there is: element trees, data paths, titles
            text = self._ask(envelope, project, "code", "search_forms",
                             {"query": query, "limit": limit})
            if text:
                envelope.merge(code_parsers.parse_search_forms(text), "code")
            return envelope.dedupe()

        # text: fan out -- the two rankers overlap by ~3%, so the union is
        # nearly twice as complete, and asked concurrently it costs max(t1, t2)
        # rather than t1 + t2
        graph_text, code_text = self._ask_many(envelope, project, [
            ("graph", "search_code", {"query": query, "top_k": limit}),
            ("code", "codesearch", {"query": query, "limit": limit}),
        ])
        if graph_text:
            envelope.merge(graph_parsers.parse_search_code(graph_text), "graph")
        if code_text:
            envelope.merge(code_parsers.parse_codesearch(code_text), "code")
        return envelope.dedupe()

    def describe(self, id, project=None, sections=None):
        """Dossier of an object; the layout of a form; the structure of a module.

        What `id` names decides the route. `Справочники.X.Форма.Y` is a form: its
        layout plus the structure of its module. A module path (`.../Module.bsl`)
        is a module. Anything else is an object -- the graph dossier plus typed
        attributes from code, and with `sections` containing "modules" or "form"
        the object's module structures or its forms' layouts on top.
        """
        project = self.registry.get(project)
        envelope = Envelope("describe(%r)" % id)
        envelope.coverage.resolved_id = id
        wanted = set(sections or ())
        local = wanted & _OWN_SECTIONS

        form = _FORM_ID.match(id or "")
        if form:
            self._describe_form(envelope, project, form.group("object"), form.group("form"))
            self._describe_modules(envelope, project, self._module_paths(project, id), id)
            return envelope.dedupe()
        if (id or "").endswith(".bsl"):
            self._describe_modules(envelope, project, [id.lstrip("/")], None)
            return envelope.dedupe()

        args = {"object_name": id}
        passed = sorted(wanted - _OWN_SECTIONS)
        if passed:
            args["sections"] = passed
        text, detail = self._ask_many(envelope, project, [
            ("graph", "get_object_dossier", args),
            ("code", "get_metadata_details", {"object_name": id}),
        ])
        if text:
            envelope.merge(graph_parsers.parse_dossier(text), "graph")
        if detail:
            envelope.merge(code_parsers.parse_metadata_details(detail), "code")
        # a bare common-module name is a module in itself: its structure is
        # the description, whether or not it was asked for by section
        if "modules" in local or "." not in (id or ""):
            self._describe_modules(envelope, project, self._module_paths(project, id), id)
        if "form" in local:
            self._describe_form(envelope, project, id, "")
        return envelope.dedupe()

    def _module_paths(self, project, owner):
        try:
            return self.resolver(project).modules(owner)
        except Exception:                            # noqa: BLE001 - index optional
            return []

    def _describe_form(self, envelope, project, object_name, form_name):
        text = self._ask(envelope, project, "code", "inspect_form_layout",
                         {"object_name": object_name, "form_name": form_name})
        if text:
            envelope.merge(code_parsers.parse_form_layout(text), "code")

    def _describe_modules(self, envelope, project, paths, owner):
        backend = project.backend("code")
        if not paths:
            if owner:
                envelope.coverage.note(
                    "no module with routines found for %s in the export" % owner)
            return
        root = backend.code_root if backend else ""
        # module paths are repo-relative in the resolver; the backend wants them
        # absolute inside its container
        texts = self._ask_many(envelope, project, [
            ("code", "get_module_structure", {"module_path": root + "/" + path})
            for path in paths[:8]])
        for text in texts:
            if text:
                envelope.merge(code_parsers.parse_module_structure(text, owner), "code")
        if len(paths) > 8:
            envelope.coverage.note("%d modules, structure shown for the first 8"
                                   % len(paths))

    def calls(self, id, project=None, direction="callers", depth=1):
        project = self.registry.get(project)
        envelope = Envelope("calls(%r, %s, depth=%d)" % (id, direction, depth))
        resolution = self._resolve(envelope, project, id)
        if not resolution.ok:
            return envelope
        canonical = resolution.id
        # The owner has to travel with the name. Asked for a bare
        # `ПолучитьЗначениеНастройки`, the backend picked a same-named routine in
        # a form module while the resolver had chosen the exported one in a
        # common module -- and the envelope then attributed one routine's callers
        # to the other. Passing `object_name` pins which homonym is meant.
        owner, _, bare = canonical.rpartition(".")
        args = {"routine_name": bare or canonical,
                "direction": direction, "depth": depth}
        if owner:
            args["object_name"] = owner
        text = self._ask(envelope, project, "graph", "trace_call_chain", args)
        if text:
            parsed = graph_parsers.parse_call_chain(text, direction, root_id=canonical)
            # ...and if the backend still resolved elsewhere, say so: silently
            # relabelling its answer with our id is how wrong data looks right.
            if parsed.echoed_id and not _same_routine(parsed.echoed_id, canonical):
                envelope.coverage.note(
                    "backend resolved %r, the resolver chose %r — records describe "
                    "the backend's pick" % (parsed.echoed_id, canonical))
                envelope.coverage.degraded = True
            envelope.merge(parsed, "graph")
            return envelope.dedupe()

        # Graph could not answer at all (not declared, down, failed). The code
        # backend's hierarchy is the weaker source -- measured 2 of 8 callers and
        # a false hit -- and it takes a bare name, so homonyms in other modules
        # can mix in. Better than nothing, and said so in coverage.
        fallback = self._ask(envelope, project, "code", "get_method_call_hierarchy",
                             {"method_name": bare or canonical, "direction": direction,
                              "depth": depth})
        if fallback:
            parsed = code_parsers.parse_call_hierarchy(fallback, direction,
                                                       root_id=canonical)
            envelope.coverage.note(
                "calls answered by the code backend: graph unavailable. It takes a "
                "bare name, so callers of same-named routines elsewhere may be mixed "
                "in, and it is known to miss callers")
            envelope.coverage.degraded = True
            envelope.merge(parsed, "code")
        return envelope.dedupe()

    def usages(self, id, project=None, where="both"):
        project = self.registry.get(project)
        envelope = Envelope("usages(%r, where=%s)" % (id, where))
        envelope.coverage.resolved_id = id

        if where in ("metadata", "both"):
            text = self._ask(envelope, project, "graph", "find_usages_of_object",
                             {"object_name": id, "limit": 100})
            if text:
                envelope.merge(graph_parsers.parse_usages(text), "graph")
            deps = self._ask(envelope, project, "code", "graph_dependencies",
                             {"object_name": id, "direction": "reverse", "limit": 100})
            if deps:
                envelope.merge(code_parsers.parse_dependencies(deps, "reverse"), "code")

        if where in ("code", "both"):
            # Neither backend answers this: both work at the metadata level. The
            # resolver indexes references while it reads the export for symbols
            # anyway, so the answer is a query rather than a tree walk -- which
            # over a bind mount is the difference between milliseconds and
            # seconds, on every call.
            try:
                rows = self.resolver(project).references(id)
            except Exception:                        # noqa: BLE001 - fall back
                rows = None
            if rows is None:
                envelope.coverage.note(
                    "usages in code answered by a filesystem scan: reference "
                    "index unavailable")
                envelope.extend(grep_usages(project.source, id))
            else:
                envelope.coverage.note(
                    "usages in code answered from the reference index: no "
                    "backend covers them")
                bare = id.rsplit(".", 1)[-1]
                for path, line, text, prefix in rows:
                    envelope.records.append(Record(
                        id="%s:%d" % (path, line), kind="snippet", name=bare,
                        owner=prefix, loc=Loc(path=path, line=line), text=text,
                        src=Src(backend="resolver", tool="references", tier="grep")))

        return envelope.dedupe()

    def check(self, project=None, scope="staged"):
        project = self.registry.get(project)
        envelope = Envelope("check(scope=%s)" % scope)
        command = os.environ.get("FACADE_CHECK_CMD")
        if not command:
            envelope.coverage.note(
                "no rule checker configured; set FACADE_CHECK_CMD to the "
                "distribution's checker entry point")
            envelope.coverage.degraded = True
            return envelope
        try:
            proc = subprocess.run(
                command.split() + ["--scope", scope, "--root", project.source, "--json"],
                cwd=project.source, capture_output=True, timeout=300,
                # the checker speaks Russian; Windows would otherwise decode its
                # output with the ANSI code page and choke on the first Cyrillic
                text=True, encoding="utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError) as exc:
            envelope.coverage.note("checker failed: " + type(exc).__name__)
            envelope.coverage.degraded = True
            return envelope
        try:
            report = json.loads(proc.stdout or "{}")
        except ValueError:
            envelope.coverage.note("checker did not return JSON; is --json supported?")
            envelope.coverage.degraded = True
            return envelope
        if not report.get("git", True):
            envelope.coverage.note("git unavailable: use scope=path")
        envelope.coverage.note("checked %d file(s)" % report.get("files", 0))
        for item in report.get("violations", []):
            envelope.records.append(Record(
                id="%s:%s" % (item.get("path"), item.get("line")),
                kind="snippet", name=item.get("rule"),
                owner=item.get("severity"),
                loc=Loc(path=item.get("path"), line=item.get("line")),
                sig=item.get("code"),
                text="%s — %s" % (item.get("message"), item.get("source")),
                src=Src(backend="rules", tool="rules_check", tier="grep")))
        return envelope

    def status(self, project=None, reindex=False):
        """Liveness of the fleet, or of one project; optionally rebuild its index.

        `reindex` is what keeps `frozen` from becoming a trap: a snapshot stays
        untouched until the snapshot itself is replaced on disk, and then one
        call refreshes it without editing the registry or restarting anything.
        """
        names = [project] if project else self.registry.names()
        envelope = Envelope("status(%s%s)" % (project or "all",
                                              ", reindex" if reindex else ""))
        if reindex:
            for name in names:
                entry = self.registry.get(name)
                resolver = Resolver(entry.source, self._index_path(entry) or ":memory:")
                counts = resolver.build()
                with self._lock:
                    self._resolvers[entry.name] = resolver
                envelope.coverage.note(
                    "%s: индекс пересобран — %s" % (entry.name, counts))
                # the backend's own index goes stale on the same snapshot swap;
                # it rebuilds in the background and reports through `stats`
                if entry.backend("code") is not None:
                    text = self._ask(envelope, entry, "code", "reindex", {"force": False})
                    if text:
                        envelope.coverage.note(
                            "%s: code-бэкенд запустил переиндексацию в фоне" % entry.name)
        for name in names:
            entry = self.registry.get(name)
            if not entry.backends:
                envelope.coverage.note(
                    "%s: бэкендов нет — работают только резолвер и индекс ссылок"
                    % entry.name)
                continue
            for kind in sorted(entry.backends):
                state = self.health.probe(entry.backend(kind))
                # label by the canonical project name, never by the alias the
                # caller happened to use -- status is the inventory, and an
                # inventory that echoes your own wording is not one
                envelope.coverage.add_backend(
                    "%s/%s" % (entry.name, kind), state.state, ms=state.ms,
                    index_age_s=state.index_age_s, detail=state.detail)
        return envelope


# Sections the facade handles itself rather than passing to the graph dossier.
_OWN_SECTIONS = {"modules", "form"}

# `Справочники.X.Форма.Y` -- the resolver's spelling of a form -- plus the
# spellings a caller is likely to type.
_FORM_ID = re.compile(
    r"^(?P<object>[^.]+\.[^.]+)\.(?:Форма|Формы|Form|Forms)\.(?P<form>[^.]+)$")


# -------------------------------------------------------------------- grep

_QUALIFIER = re.compile(r"^(?:[А-Яа-яЁё]+)\.(?P<name>.+)$")


def grep_usages(source, id, limit=200):
    """References to a metadata object in BSL, which no index reports.

    Matches the object through the access prefixes 1C actually uses
    (`Справочники.X`, `СправочникСсылка.X`, ...), not a bare substring.
    """
    if not source or not os.path.isdir(source):
        return []
    match = _QUALIFIER.match(id)
    name = match.group("name") if match else id
    pattern = re.compile(
        r"(?:Справочник|Документ|Перечисление|РегистрСведений|РегистрНакопления|"
        r"ПланВидовХарактеристик|ПланСчетов|БизнесПроцесс|Задача|Обработк|Отчет)"
        r"[А-Яа-яЁё]*\s*\.\s*" + re.escape(name) + r"\b")
    out = []
    for root, _dirs, files in os.walk(source):
        for filename in files:
            if not filename.endswith(".bsl"):
                continue
            full = os.path.join(root, filename)
            try:
                text = read_source(full)
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    rel = os.path.relpath(full, source).replace(os.sep, "/")
                    out.append(Record(
                        id="%s:%d" % (rel, number), kind="snippet", name=name,
                        loc=Loc(path=rel, line=number), text=line.strip()[:200],
                        src=Src(backend="grep", tool="grep_usages", tier="grep")))
                    if len(out) >= limit:
                        return out
                    break
    return out


def _same_routine(left, right):
    """Do two qualifiers name the same routine?

    The backend spells owners its own way (a form module comes back as the
    document name), so only a disagreement on the *owner segment closest to the
    routine* is treated as a real mismatch.
    """
    if not left or not right:
        return True
    left_parts = [p.lower() for p in left.split(".")]
    right_parts = [p.lower() for p in right.split(".")]
    if left_parts[-1] != right_parts[-1]:
        return False
    return left_parts[-2:-1] == right_parts[-2:-1]

