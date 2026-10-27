"""The verbs: six over a configuration, three over the platform.

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
    docs                   docs / codecheck  exact name -> docinfo, prose -> docsearch,
                                             ITS -> its_help; search has no threshold
    lint                   syntax / codecheck analyzer fast; check and review are models
    template               templates         one server, one verb

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
import platform_parsers
from envelope import Envelope
from record import Loc, Record, Src
from registry import SHARED
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
        self._schemas = {}                   # exposed tool name -> tools/list entry

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
        if project.frozen and resolver.stats()["files"] and not resolver.stale_schema:
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

    def _call_paged(self, backend, kind, tool, args):
        """One backend call; for graph, the pages behind it as well.

        Graph images of 27.09.2026 cut every answer at 200 items whatever
        `max_items` asks for, and hand back a `cursor`; the next page continues
        the same prose where the first stopped. The pages are fetched and their
        text joined into one envelope, so the parsers see the whole answer.
        Past _GRAPH_PAGES the envelope keeps `returned` short of `total`, and
        the parser reports it -- a cut answer is never passed off as whole."""
        client = self.client(backend)
        elapsed, outcome, text = client.call(tool, args)
        if kind != "graph" or outcome != "OK":
            return elapsed, outcome, text
        try:
            first = json.loads(text)
        except (ValueError, TypeError):
            return elapsed, outcome, text
        if not isinstance(first, dict) or not first.get("cursor") \
                or not isinstance(first.get("text"), str):
            return elapsed, outcome, text
        texts, returned, cursor = [first["text"]], first.get("returned") or 0, first["cursor"]
        pages = 1
        while cursor and pages < _GRAPH_PAGES:
            more_elapsed, more_outcome, more = client.call(tool, dict(args, cursor=cursor))
            elapsed += more_elapsed
            try:
                page = json.loads(more) if more_outcome == "OK" else None
            except (ValueError, TypeError):
                page = None
            if not isinstance(page, dict) or not isinstance(page.get("text"), str):
                break
            texts.append(page["text"])
            returned += page.get("returned") or 0
            cursor = page.get("cursor")
            pages += 1
        joined = "\n".join(t.rstrip("\n") for t in texts)
        merged = dict(first, text=joined, returned=returned, cursor=cursor)
        return elapsed, outcome, json.dumps(merged, ensure_ascii=False)

    def _query(self, project, kind, tool, args):
        """Call one backend. Returns (text or None, coverage events).

        Coverage is returned as events rather than written straight into an
        envelope so that parallel calls can report in a fixed order: the same
        question gives the same coverage block however the threads interleave.
        """
        events = []
        backend = project.backend(kind)
        if backend is None:
            if project.grouped:
                # in a group a unit without this backend is by design (the base
                # often has none) -- the fold reports it once, not per call
                return None, events
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
            elapsed, outcome, text = self._call_paged(backend, kind, tool, args)
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
            events.append(("note", "%s.%s failed: %s" % (kind, tool, text[:400])))
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

    # -- base + extensions ------------------------------------------------

    def _units(self, project, scope=None):
        """The parts of a group a verb consults, base first.

        A configuration without extensions is its own single unit. In a group,
        `scope` picks: "all" -- the base and every extension; "base"; or an
        extension's name -- the base plus that extension, since an extension
        without the code it extends answers half a question. The default is
        what the caller named: a base means all of it, an extension means that
        extension on top of its base.
        """
        base = self.registry.get(project.parent) if project.parent else project
        if not base.extensions:
            return [project]
        if scope is None:
            scope = project.name if project.parent else "all"
        if scope == "all":
            return [base] + [self.registry.get(name) for name in base.extensions]
        if scope == "base" or scope == base.name:
            return [base]
        unit = self.registry.get(scope)
        if unit.parent != base.name:
            raise KeyError("scope %r is not an extension of %s; extensions: %s"
                           % (scope, base.name, ", ".join(base.extensions)))
        return [base, unit]

    def _index_building(self, unit):
        """Is another thread building this unit's resolver right now?"""
        with self._lock:
            if unit.name in self._resolvers:
                return False
            gate = self._building.get(unit.name)
        return bool(gate and gate.locked())

    @staticmethod
    def _label(unit):
        return ("ext:" + unit.name) if unit.parent else "base"

    def _group_extensions(self, units):
        base = next((u for u in units if not u.parent), None)
        if base is None:
            base = self.registry.get(units[0].parent)
        return [self.registry.get(name) for name in base.extensions]

    def _over_units(self, envelope, units, work):
        """Run `work(envelope, unit)` for every unit and fold the results.

        Units run concurrently, each into its own envelope, so one slow
        extension backend does not serialise the rest. Folding stamps every
        record with its unit and every backend and note with the unit's label.
        A unit that simply lacks the object (an extension that never borrowed
        it) is not a degraded answer; a unit whose backend is down is.
        """
        if len(units) == 1:
            unit = units[0]
            work(envelope, unit)
            if unit.grouped:
                for record in envelope.records:
                    record.scope = self._label(unit)
                if not unit.backends:
                    envelope.coverage.note(
                        "%s: бэкендов нет — ответ только из индекса резолвера"
                        % self._label(unit))
            return
        # A unit whose index is being built right now is left out rather than
        # waited for: a full ERP base takes minutes to index, and an extension
        # must not stop answering because its base is warming up.
        building = [u for u in units if self._index_building(u)]
        for unit in building:
            envelope.coverage.note(
                "%s: индекс строится — единица пропущена, ответ неполон" % self._label(unit))
            envelope.coverage.degraded = True
        units = [u for u in units if u not in building]
        if not units:
            return
        subs = []
        for _unit in units:
            sub = Envelope(envelope.coverage.asked)
            sub.absent_ok = True
            subs.append(sub)
        with ThreadPoolExecutor(max_workers=len(units)) as pool:
            futures = [pool.submit(work, sub, unit) for sub, unit in zip(subs, units)]
            for future in futures:
                future.result()
        cov = envelope.coverage
        for sub, unit in zip(subs, units):
            label = self._label(unit)
            for record in sub.records:
                record.scope = label
            envelope.records.extend(sub.records)
            for entry in sub.coverage.backends:
                entry = dict(entry)
                entry["name"] = "%s/%s" % (label, entry["name"])
                cov.backends.append(entry)
                if entry["state"] != "up":
                    cov.degraded = True
            for text in sub.coverage.notes:
                cov.note("%s: %s" % (label, text))
            if sub.coverage.degraded:
                cov.degraded = True
            if sub.coverage.index_age_s is not None and (
                    cov.index_age_s is None or sub.coverage.index_age_s > cov.index_age_s):
                cov.index_age_s = sub.coverage.index_age_s
            if cov.resolved_id is None and sub.coverage.resolved_id:
                cov.resolved_id = sub.coverage.resolved_id
            for candidate in sub.coverage.candidates:
                if candidate not in cov.candidates:
                    cov.candidates.append(candidate)
            if not unit.backends:
                cov.note("%s: бэкендов нет — ответ только из индекса резолвера" % label)

    def _mark_overrides(self, envelope, units):
        """Flag base routines that an extension intercepts.

        The one place the facade knows extension semantics, and it earns it:
        without the flag, `find` over the base shows code the runtime replaces.
        The flag names the extension, the directive and the method, because
        &Перед / &После add to the base code while &Вместо replaces it.
        """
        if not any(r.kind == "routine" and r.scope == "base" for r in envelope.records):
            return
        intercepted = {}
        for ext in self._group_extensions(units):
            if self._index_building(ext):
                envelope.coverage.note("ext:%s: индекс строится — перехваты не отмечены"
                                       % ext.name)
                continue
            try:
                rows = self.resolver(ext).overrides()
            except Exception:                        # noqa: BLE001 - index optional
                continue
            for owner, target, method, directive, _path, _line in rows:
                intercepted.setdefault(owner + "." + target, []).append(
                    "ext:%s &%s %s" % (ext.name, directive, method))
        marked = 0
        for record in envelope.records:
            if record.kind == "routine" and record.scope == "base" and record.id in intercepted:
                record.overridden_by = intercepted[record.id]
                marked += 1
        if marked:
            envelope.coverage.note(
                "%d процедур(ы) базы перехвачены расширениями — см. overridden_by"
                % marked)

    @staticmethod
    def _order(envelope):
        """Same id: the extension's record above the base's, both kept."""
        first = {}
        for index, record in enumerate(envelope.records):
            first.setdefault(record.id, index)
        envelope.records.sort(key=lambda r: (first[r.id], 1 if r.scope == "base" else 0))
        return envelope

    def _finish(self, envelope, units):
        envelope.dedupe()
        self._mark_overrides(envelope, units)
        return self._order(envelope)

    # -- verbs ------------------------------------------------------------

    def find(self, query, project=None, kind="any", exact=False, limit=20, scope=None):
        project = self.registry.get(project)
        units = self._units(project, scope)
        envelope = Envelope("find(%r, kind=%s)" % (query, kind))
        self._over_units(envelope, units, lambda env, unit: self._find_one(
            env, unit, query, kind, exact, limit))
        return self._finish(envelope, units)

    def _find_one(self, envelope, project, query, kind, exact, limit):
        # A routine name has no whitespace, so under `any` a phrase goes straight
        # to the text search. Since the images of 27.09.2026 the backend's
        # function search matches loosely and answers a phrase with look-alike
        # names -- taken as a routine hit, that ended the search before the
        # graph was asked.
        routine_like = kind == "routine" or (kind == "any" and not re.search(r"\s", (query or "").strip()))
        if routine_like:
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
                envelope.dedupe()
                return

        if kind == "metadata":
            text = self._ask(envelope, project, "code", "metadatasearch",
                             {"query": query, "limit": limit})
            if text:
                envelope.merge(code_parsers.parse_metadatasearch(text), "code")
            return

        if kind == "form":
            # the only index of forms there is: element trees, data paths, titles
            text = self._ask(envelope, project, "code", "search_forms",
                             {"query": query, "limit": limit})
            if text:
                envelope.merge(code_parsers.parse_search_forms(text), "code")
            return

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

    def describe(self, id, project=None, sections=None, scope=None):
        """Dossier of an object; the layout of a form; the structure of a module.

        What `id` names decides the route. `Справочники.X.Форма.Y` is a form: its
        layout plus the structure of its module. A module path (`.../Module.bsl`)
        is a module. Anything else is an object -- the graph dossier plus typed
        attributes from code, and with `sections` containing "modules" or "form"
        the object's module structures or its forms' layouts on top. In a group
        every unit that has the object contributes: an extension that borrowed
        it adds its attributes, forms and modules.
        """
        project = self.registry.get(project)
        units = self._units(project, scope)
        envelope = Envelope("describe(%r)" % id)
        # `Документы.X.ТабличныеЧасти.Строки` is how the export nests it; both
        # backends know the section only as `Документы.X.Строки`
        id = _TABULAR_PATH.sub(r"\g<object>.", id or "")
        envelope.coverage.resolved_id = id
        self._over_units(envelope, units, lambda env, unit: self._describe_one(
            env, unit, id, sections))
        envelope.coverage.resolved_id = id
        self._finish(envelope, units)
        if not envelope.records and self._answered_in_full(envelope):
            envelope.coverage.not_found = True
            envelope.coverage.note("объект не найден: %s" % id)
        return envelope

    @staticmethod
    def _answered_in_full(envelope):
        """Every backend asked was up and settled: then an empty answer means the
        object is not there, rather than that nobody could tell."""
        cov = envelope.coverage
        unsettled = ("unparsed", "индекс строится", "перестраивает индекс", "in progress",
                     "incomplete", "failed", "no session", "format drift")
        return bool(cov.backends) and all(
            b["state"] == "up" and not b.get("detail") for b in cov.backends) and not any(
            marker in n for n in cov.notes for marker in unsettled)

    def _describe_one(self, envelope, project, id, sections):
        wanted = set(sections or ())
        local = wanted & _OWN_SECTIONS

        form = _FORM_ID.match(id or "")
        if form:
            self._describe_form(envelope, project, form.group("object"), form.group("form"))
            self._describe_modules(envelope, project, self._module_paths(project, id), id)
            return
        if (id or "").endswith(".bsl"):
            self._describe_modules(envelope, project, [id.lstrip("/")], None)
            return

        args = {"object_name": id}
        passed = sorted(wanted - _OWN_SECTIONS)
        if passed:
            args["sections"] = passed
        text, detail = self._ask_many(envelope, project, [
            ("graph", "get_object_dossier", args),
            ("code", "get_metadata_details", {"object_name": id}),
        ])
        dossier = graph_parsers.parse_dossier(text) if text else None
        details = code_parsers.parse_metadata_details(detail) if detail else None
        if self._describe_part(envelope, project, id, dossier, details):
            return
        if dossier:
            envelope.merge(dossier, "graph")
        if details:
            envelope.merge(details, "code")
        # a bare common-module name is a module in itself: its structure is
        # the description, whether or not it was asked for by section
        if "modules" in local or "." not in (id or ""):
            self._describe_modules(envelope, project, self._module_paths(project, id), id)
        if "form" in local:
            self._describe_form(envelope, project, id, "")

    def _describe_part(self, envelope, project, id, dossier, details):
        """A tabular section or one of its columns, described through its owner.

        Neither backend knows `Документы.X.Строки` as an object: the graph says
        "не найден", code offers look-alikes. The columns and their types live
        in the owner's metadata details, so when the id itself is unknown the
        owners are tried -- one level up for a section, two for a column -- and
        only the records at or under the requested id are kept.
        """
        found = any(r is not None and r.status in ("ok", "empty") for r in (dossier, details))
        parts = (id or "").split(".")
        if found or len(parts) < 3:
            return False
        for cut in (1, 2):
            if len(parts) - cut < 2:
                break
            owner = ".".join(parts[:-cut])
            detail = self._ask(envelope, project, "code", "get_metadata_details",
                               {"object_name": owner})
            parsed = code_parsers.parse_metadata_details(detail) if detail else None
            if parsed is None or parsed.status != "ok":
                continue
            kept = [r for r in parsed.records if r.id == id or r.id.startswith(id + ".")]
            if kept:
                envelope.extend(kept)
                return True
        return False

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
            if owner and not getattr(envelope, "absent_ok", False):
                envelope.coverage.note(
                    "no module with routines found for %s in the export" % owner)
            return
        if backend is None:
            return
        root = backend.code_root
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

    def calls(self, id, project=None, direction="callers", depth=1, scope=None):
        project = self.registry.get(project)
        units = self._units(project, scope)
        envelope = Envelope("calls(%r, %s, depth=%d)" % (id, direction, depth))
        # One canonical id for the whole group, decided before any backend is
        # asked -- in the unit the caller named first. A bare name asked of the
        # base means the base's routine even when an extension's own module
        # happens to declare a namesake; asked of an extension, the reverse.
        resolution = None
        candidates = []
        for unit in sorted(units, key=lambda u: 0 if u.name == project.name else 1):
            if len(units) > 1 and self._index_building(unit):
                continue                             # reported by the fold below
            attempt = self.resolver(unit).resolve(id)
            for candidate in attempt.candidates:
                if candidate not in candidates:
                    candidates.append(candidate)
            if attempt.ok:
                resolution = attempt
                break
        envelope.coverage.candidates = candidates
        if resolution is None:
            if candidates:
                envelope.coverage.note("name is ambiguous; pass a qualified id to pick one")
            envelope.coverage.note("unresolved name: " + str(id))
            return envelope
        envelope.coverage.resolved_id = resolution.id
        if resolution.candidates and resolution.confidence == "ambiguous":
            envelope.coverage.note("name is ambiguous; pass a qualified id to pick one")
        canonical = resolution.id
        self._over_units(envelope, units, lambda env, unit: self._calls_one(
            env, unit, canonical, direction, depth))
        envelope.coverage.resolved_id = canonical
        blind = [self._label(u) for u in units
                 if u.grouped and not (u.backend("graph") or u.backend("code"))]
        if blind:
            # the resolver knows declarations, not call sites: zero callers here
            # means "none seen in the units that have a call index", nothing more
            envelope.coverage.note(
                "вызовы из кода %s не покрыты: нет индекса вызовов — пустой ответ "
                "не значит «никто не вызывает»" % ", ".join(blind))
        return self._finish(envelope, units)

    def _calls_one(self, envelope, project, canonical, direction, depth):
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
            envelope.dedupe()
            return
        if project.grouped and project.backend("code") is None:
            return

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

    def usages(self, id, project=None, where="both", scope=None):
        project = self.registry.get(project)
        units = self._units(project, scope)
        envelope = Envelope("usages(%r, where=%s)" % (id, where))
        self._over_units(envelope, units, lambda env, unit: self._usages_one(
            env, unit, id, where))
        envelope.coverage.resolved_id = id
        return self._finish(envelope, units)

    def _usages_one(self, envelope, project, id, where):
        if where in ("metadata", "both"):
            text, deps = self._ask_many(envelope, project, [
                ("graph", "find_usages_of_object", {"object_name": id, "limit": 100}),
                ("code", "graph_dependencies",
                 {"object_name": id, "direction": "reverse", "limit": 100}),
            ])
            if text:
                envelope.merge(graph_parsers.parse_usages(text), "graph")
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
        if not project:
            for kind, backend in sorted(self.registry.shared.backends.items()):
                state = self.health.probe(backend)
                envelope.coverage.add_backend(
                    "%s/%s" % (SHARED, kind), state.state, ms=state.ms,
                    detail=state.detail)
        for name in names:
            entry = self.registry.get(name)
            if entry.extensions:
                envelope.coverage.note("%s: база, расширения — %s"
                                       % (entry.name, ", ".join(entry.extensions)))
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


    # -- platform verbs -------------------------------------------------

    def docs(self, query, scope="platform", version=None):
        """Platform documentation and ITS.

        The documentation search ranks without a threshold -- it answers any
        query with *something* -- so emptiness cannot drive the routing. What
        can: a query shaped like a name (`ТаблицаЗначений.Найти`) goes to the
        exact lookup first, which does say "not found", and only then to the
        search. A version pins the lookup to that platform version's docs.
        ITS is a different corpus (methodology, not syntax); `any` asks both
        at once.
        """
        envelope = Envelope("docs(%r, scope=%s)" % (query, scope))
        shared = self.registry.shared
        platform = scope in ("platform", "any")
        its = scope in ("its", "any")
        requests = []
        if platform:
            if version:
                requests.append(("codecheck", "search_1c_documentation",
                                 {"query": query, "version": version}))
            elif _NAME_LIKE.match(query or ""):
                requests.append(("docs", "docinfo", {"name": query}))
            else:
                requests.append(("docs", "docsearch", {"query": query}))
        if its:
            requests.append(("codecheck", "its_help", {"query": query}))
        if not requests:
            envelope.coverage.note("scope must be platform, its or any")
            return envelope
        texts = self._ask_many(envelope, shared, requests)
        for (kind, tool, _args), text in zip(requests, texts):
            if text is None:
                continue
            if tool == "its_help":
                envelope.merge(platform_parsers.parse_its(text), kind)
            elif tool == "search_1c_documentation":
                envelope.merge(platform_parsers.as_text(text, kind, tool, query), kind)
            else:
                parsed = platform_parsers.parse_docs(text, tool, kind)
                if tool == "docinfo" and parsed.status == "not_found":
                    # the name was not a documented one: fall back to the search
                    envelope.coverage.note("no article named %r; answered by search" % query)
                    again = self._ask(envelope, shared, "docs", "docsearch", {"query": query})
                    if again:
                        envelope.merge(platform_parsers.parse_docs(again), "docs")
                    continue
                envelope.merge(parsed, kind)
                if parsed.fetch:
                    self._fetch_bodies(envelope, shared, parsed)
        for record in envelope.records:
            if record.src and record.src.backend == "docs" and not record.text:
                # an empty article read as an answer is worse than none
                envelope.coverage.note("%s: no text in the documentation answer" % record.id)
                envelope.coverage.degraded = True
        if any(r.src and r.src.tool == "docsearch" for r in envelope.records):
            envelope.coverage.note(
                "documentation search has no relevance threshold — check that "
                "the articles are about the question")
        return envelope.dedupe()

    def _fetch_bodies(self, envelope, shared, parsed):
        """Fill the records docinfo sent without a body: one lookup per doc_id,
        all at once. The ambiguity itself stays said in coverage."""
        if parsed.note:
            envelope.coverage.note(parsed.note)
        by_id = {r.id: r for r in parsed.records}
        wanted = [(rid, doc_id) for rid, doc_id in parsed.fetch.items() if rid in by_id]
        texts = self._ask_many(envelope, shared, [
            ("docs", "docinfo", {"name": doc_id}) for _rid, doc_id in wanted])
        for (rid, _doc_id), text in zip(wanted, texts):
            if not text:
                continue
            whole = platform_parsers.parse_docs(text, "docinfo", "docs")
            body = next((r for r in whole.records if r.text), None)
            if body is not None:
                by_id[rid].text = body.text

    def lint(self, code=None, path=None, project=None, mode="syntax"):
        """Check BSL code: `syntax` is the fast analyzer gate, `check` a
        correctness pass, `review` a style and standards pass. The modes are
        not mixed in one call: the first answers in a tenth of a second, the
        other two are model-backed and take tens of seconds."""
        envelope = Envelope("lint(mode=%s)" % mode)
        if path and not code:
            code = self._read_project_file(envelope, project, path)
            if code is None:
                return envelope
        if not code:
            envelope.coverage.note("pass code, or path to a module in the project")
            return envelope
        route = {"syntax": ("syntax", "syntaxcheck"),
                 "check": ("codecheck", "check_1c_code"),
                 "review": ("codecheck", "review_1c_code")}.get(mode)
        if route is None:
            envelope.coverage.note("mode must be syntax, check or review")
            return envelope
        kind, tool = route
        text = self._ask(envelope, self.registry.shared, kind, tool, {"code": code})
        if text is None:
            return envelope
        if mode == "syntax":
            envelope.merge(platform_parsers.parse_syntax(text), kind)
            if path:
                for record in envelope.records:
                    if record.loc:
                        record.loc.path = path
        else:
            envelope.merge(platform_parsers.as_text(text, kind, tool, mode), kind)
        return envelope

    def template(self, query=None, id=None):
        """Code templates: search by description, or one template by id."""
        envelope = Envelope("template(%r)" % (id or query))
        if id:
            text = self._ask(envelope, self.registry.shared, "templates",
                             "get_template", {"template_id": str(id)})
            tool = "get_template"
        elif query:
            text = self._ask(envelope, self.registry.shared, "templates",
                             "templatesearch", {"query": query})
            tool = "templatesearch"
        else:
            envelope.coverage.note("pass query or id")
            return envelope
        if text:
            envelope.merge(platform_parsers.parse_templates(text, tool), "templates")
        return envelope.dedupe()

    def _read_project_file(self, envelope, project, path):
        entry = self.registry.get(project)
        root = os.path.realpath(entry.source or "")
        full = os.path.realpath(os.path.join(root, path))
        if not entry.source or not full.startswith(root + os.sep):
            envelope.coverage.note("path must lie inside the project export")
            return None
        try:
            return read_source(full)
        except OSError as exc:
            envelope.coverage.note("cannot read %s: %s" % (path, type(exc).__name__))
            return None

    # -- pass-through ---------------------------------------------------

    def exposure(self):
        """Which backend tools are published one to one, and where they live.

        Returns {public name: (kind, tool, [project names, default first])}.
        The route is data -- the registry's `expose` lists -- not code: a tool
        joins or leaves the facade by editing the registry. The public name is
        `<kind>_<tool>`: Claude accepts tool names matching [a-zA-Z0-9_-] only,
        so the `code.verify_xml` spelling of the design is not an option.
        """
        plan = {}
        names = self.registry.names()
        default = self.registry.default
        ordered = ([default] if default in names else []) + [n for n in names if n != default]
        for project_name in ordered:
            project = self.registry.get(project_name)
            for kind in sorted(project.backends):
                backend = project.backend(kind)
                tools = backend.expose if backend.expose is not None \
                    else self.registry.expose.get(kind, [])
                for tool in tools:
                    entry = plan.setdefault(_public_name(kind, tool), (kind, tool, []))
                    entry[2].append(project.name)
        # platform servers publish under their own name and take no project
        for kind, backend in sorted(self.registry.shared.backends.items()):
            for tool in backend.expose or []:
                plan.setdefault(_public_name(kind, tool), (kind, tool, [SHARED]))
        return plan

    def _holder(self, name):
        return self.registry.shared if name == SHARED else self.registry.get(name)

    def exposed_tools(self):
        """tools/list entries for the pass-through tools whose schema is known.

        The schema is the backend's own, fetched once and cached. A backend that
        is down at that moment simply leaves its tools out of this listing; the
        next listing tries again, so they appear as soon as it answers.
        """
        out = []
        for name, (kind, tool, projects) in sorted(self.exposure().items()):
            with self._lock:
                cached = self._schemas.get(name)
            if cached is None:
                cached = self._fetch_schema(name, kind, tool, projects)
            if cached is not None:
                out.append(cached)
        return out

    def _fetch_schema(self, name, kind, tool, projects):
        for project_name in projects:
            backend = self._holder(project_name).backend(kind)
            try:
                listing = self.client(backend).tools()
            except Exception:                        # noqa: BLE001 - try the next
                continue
            for item in listing or []:
                if item.get("name") != tool:
                    continue
                schema = dict(item.get("inputSchema") or {"type": "object"})
                if projects != [SHARED]:
                    props = dict(schema.get("properties") or {})
                    props["project"] = {
                        "type": "string",
                        "description": "Проект из реестра, чей %s-бэкенд ответит; "
                                       "опущен — %s." % (kind, projects[0])}
                    schema["properties"] = props
                entry = {"name": name,
                         "description": "[проброс %s.%s, ответ без нормализации] %s"
                                        % (kind, tool, item.get("description") or ""),
                         "inputSchema": schema}
                with self._lock:
                    self._schemas[name] = entry
                return entry
        return None

    def call_exposed(self, name, arguments):
        """Proxy one pass-through call. Returns (text or None, coverage notes)."""
        plan = self.exposure()
        if name not in plan:
            raise KeyError("unknown tool: %s" % name)
        kind, tool, projects = plan[name]
        arguments = dict(arguments or {})
        wanted = arguments.pop("project", None)
        if projects == [SHARED]:
            text, events = self._query(self.registry.shared, kind, tool, arguments)
            return text, [e[1] for e in events if e[0] == "note"]
        project = self.registry.get(wanted or projects[0])
        if project.name not in projects:
            raise KeyError("%s is not published for project %r; published for: %s"
                           % (name, project.name, ", ".join(projects)))
        text, events = self._query(project, kind, tool, arguments)
        notes = [e[1] for e in events if e[0] == "note"]
        return text, notes


def _public_name(kind, tool):
    return re.sub(r"[^A-Za-z0-9_-]", "_", "%s_%s" % (kind, tool))[:64]


# A query that looks like a platform name: `ТаблицаЗначений`, `Массив.Найти`,
# `Запрос.Выполнить` -- one or two identifiers, no spaces.
_NAME_LIKE = re.compile(r"^[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*(?:\.[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)?$")


# Sections the facade handles itself rather than passing to the graph dossier.
_OWN_SECTIONS = {"modules", "form"}

# Graph pages followed per call: 200 items each, so up to 4 000 -- a dossier of
# the largest ERP catalog fits; beyond that the answer is reported as cut.
_GRAPH_PAGES = 20

# `Справочники.X.Форма.Y` -- the resolver's spelling of a form -- plus the
# spellings a caller is likely to type.
_TABULAR_PATH = re.compile(
    r"^(?P<object>[^.]+\.[^.]+)\.(?:ТабличныеЧасти|ТабличнаяЧасть|TabularSections|TabularSection)\.")
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

