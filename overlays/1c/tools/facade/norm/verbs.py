"""The six verbs.

Everything measured about the backends is encoded here as routing, so the
choice stops being something a model makes from prose descriptions:

    find(kind=routine)     code_metadata     0.1s with a full body vs 4.9s
    find(kind=metadata)    code_metadata     0.1s vs 7.1s
    find(kind=text)        both, union       outputs overlap by 3%
    describe               graph + code      dossier is richer; code adds types
    calls                  resolve -> graph  8 of 8 vs 2 of 8 and a false hit
    usages(where=metadata) both, union       they answer different questions
    usages(where=code)     grep              no index covers it at all
    check                  external CLI      rules live in the distribution

Fan-out is selective on purpose. On `find(kind=text)` it nearly doubles recall
for free, because the two rankers barely agree and run concurrently. On `calls`
it would add a known false record, and on `find(kind=metadata)` it would cost a
seventy-fold slowdown to add nothing.
"""
import os
import re
import subprocess

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

    # -- plumbing ---------------------------------------------------------

    @staticmethod
    def _default_resolver(project):
        resolver = Resolver(project.source)
        resolver.build()
        return resolver

    def resolver(self, project):
        if project.name not in self._resolvers:
            self._resolvers[project.name] = self.resolver_factory(project)
        return self._resolvers[project.name]

    def client(self, backend):
        if backend.url not in self._clients:
            self._clients[backend.url] = self.client_factory(backend.url)
        return self._clients[backend.url]

    def _ask(self, envelope, project, kind, tool, args):
        """Call one backend, recording liveness in coverage. None on failure."""
        backend = project.backend(kind)
        if backend is None:
            envelope.coverage.add_backend(kind, "down", detail="not in registry")
            return None
        status = self.health.ensure(backend)
        if not status.usable:
            envelope.coverage.add_backend(kind, status.state, detail=status.detail)
            return None
        elapsed, outcome, text = self.client(backend).call(tool, args)
        envelope.coverage.add_backend(kind, "up", ms=elapsed * 1000,
                                      index_age_s=status.index_age_s)
        if outcome in ("ERR", "FAIL"):
            envelope.coverage.note("%s.%s failed: %s" % (kind, tool, text[:120]))
            envelope.coverage.degraded = True
            return None
        return text

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
                envelope.coverage.note("metadatasearch reply kept verbatim")
                envelope.extend(_raw_snippet(text, "code", "metadatasearch"))
            return envelope

        # text: fan out -- the two rankers overlap by ~3%, so the union is
        # nearly twice as complete and costs max(t1, t2) rather than t1 + t2
        graph_text = self._ask(envelope, project, "graph", "search_code",
                               {"query": query, "top_k": limit})
        if graph_text:
            envelope.merge(graph_parsers.parse_search_code(graph_text), "graph")
        code_text = self._ask(envelope, project, "code", "codesearch",
                              {"query": query, "limit": limit})
        if code_text:
            envelope.coverage.note("code chunks carry hashed module ids; "
                                   "identity restored from loc.path")
            envelope.extend(_raw_snippet(code_text, "code", "codesearch"))
        return envelope.dedupe()

    def describe(self, id, project=None, sections=None):
        project = self.registry.get(project)
        envelope = Envelope("describe(%r)" % id)
        envelope.coverage.resolved_id = id
        args = {"object_name": id}
        if sections:
            args["sections"] = sections
        text = self._ask(envelope, project, "graph", "get_object_dossier", args)
        if text:
            envelope.merge(graph_parsers.parse_dossier(text), "graph")
        detail = self._ask(envelope, project, "code", "get_metadata_details",
                           {"object_name": id})
        if detail:
            envelope.merge(code_parsers.parse_metadata_details(detail), "code")
        return envelope.dedupe()

    def calls(self, id, project=None, direction="callers", depth=1):
        project = self.registry.get(project)
        envelope = Envelope("calls(%r, %s, depth=%d)" % (id, direction, depth))
        resolution = self._resolve(envelope, project, id)
        if not resolution.ok:
            return envelope
        canonical = resolution.id
        # graph resolves qualified names and traverses the real edge set;
        # code_metadata matches bare names and misses most of them
        bare = canonical.rsplit(".", 1)[-1]
        text = self._ask(envelope, project, "graph", "trace_call_chain",
                         {"routine_name": bare, "direction": direction, "depth": depth})
        if text:
            envelope.merge(
                graph_parsers.parse_call_chain(text, direction, root_id=canonical), "graph")
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
            # neither index answers this: measured against grep, 50 files
            # reference the object in code and both backends returned none
            hits = grep_usages(project.source, id)
            envelope.coverage.note(
                "usages in code answered by grep: no index covers them")
            envelope.extend(hits)

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
            proc = subprocess.run(command.split() + ["--scope", scope],
                                  cwd=project.source, capture_output=True,
                                  text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            envelope.coverage.note("checker failed: " + type(exc).__name__)
            envelope.coverage.degraded = True
            return envelope
        envelope.coverage.note("checker exit=%d" % proc.returncode)
        for line in (proc.stdout or "").splitlines():
            if line.strip():
                envelope.records.append(Record(
                    id=line.strip()[:120], kind="snippet", name="violation",
                    text=line.rstrip(),
                    src=Src(backend="rules", tool="check", tier="grep")))
        return envelope

    def status(self, project=None):
        """Liveness of the whole fleet, or of one project."""
        names = [project] if project else self.registry.names()
        envelope = Envelope("status(%s)" % (project or "all"))
        for name in names:
            entry = self.registry.get(name)
            for kind in sorted(entry.backends):
                state = self.health.probe(entry.backend(kind))
                envelope.coverage.add_backend(
                    "%s/%s" % (name, kind), state.state, ms=state.ms,
                    index_age_s=state.index_age_s, detail=state.detail)
        return envelope


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


def _raw_snippet(text, backend, tool):
    """Keep an unparsed reply as one snippet rather than dropping it."""
    return [Record(id=tool + ":raw", kind="snippet", name=tool, text=text,
                   src=Src(backend=backend, tool=tool, tier="indexed"))]
