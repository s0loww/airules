"""Project registry: the facade's addressing table.

One entry per 1C project, naming its source tree, its two backends and the
containers behind them. This is what lets a target project carry a single
`.mcp.json` entry instead of one per server, and it is what removes the
guess-the-host failure mode: the caller names a project, the facade looks the
address up.

The registry is data, not code -- JSON so the standard library is enough.
Location, in order: $FACADE_REGISTRY, then `facade-registry.json` next to this
package. `registry.example.json` documents the shape.
"""
import io
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(HERE, "facade-registry.json")
EXAMPLE_PATH = os.path.join(HERE, "registry.example.json")


class Backend(object):
    """One MCP endpoint plus the container that serves it, if any."""

    __slots__ = ("kind", "url", "container", "cold_ok", "timeout", "code_root", "expose")

    DEFAULT_TIMEOUT = 120.0
    DEFAULT_CODE_ROOT = "/app/code"

    def __init__(self, kind, url, container=None, cold_ok=False, timeout=None,
                 code_root=None, expose=None):
        self.kind = kind                # "code" | "graph"
        self.url = url
        self.container = container      # docker name, or None if not managed
        self.cold_ok = cold_ok          # may the facade start it on demand?
        # Per-call ceiling. A graph walk on a full ERP base legitimately takes
        # tens of seconds while a code lookup takes a tenth of one; one global
        # number is either too tight for the first or too loose for the second.
        self.timeout = float(timeout) if timeout else self.DEFAULT_TIMEOUT
        # Where the backend mounts the export. Tools that take a module path
        # (get_module_structure) want it absolute inside the container.
        self.code_root = (code_root or self.DEFAULT_CODE_ROOT).rstrip("/")
        # Tools of this backend published through the facade one to one. None
        # means "whatever the registry-wide default for this kind says"; an
        # explicit empty list switches publication off for this backend.
        self.expose = list(expose) if expose is not None else None

    def __repr__(self):
        return "Backend(%s, %s)" % (self.kind, self.url)


class Project(object):
    __slots__ = ("name", "source", "backends", "aliases", "frozen")

    def __init__(self, name, source, backends, aliases=None, frozen=False):
        self.name = name
        self.source = source            # path to the configuration export
        self.backends = backends        # {"code": Backend, "graph": Backend}
        self.aliases = tuple(aliases or ())
        # A snapshot that does not change between runs: reopen the stored
        # index and skip the rescan. Re-hashing a full ERP base is 120 000
        # files, and over a bind mount that is minutes even when nothing
        # changed -- the scan itself is the cost, not the parsing.
        self.frozen = bool(frozen)

    def backend(self, kind):
        return self.backends.get(kind)

    def __repr__(self):
        return "Project(%s)" % self.name


SHARED = "shared"


class Registry(object):
    def __init__(self, projects, default=None, expose=None, shared=None):
        self._projects = {p.name: p for p in projects}
        # Platform servers -- documentation, syntax, code check, templates --
        # belong to no configuration. They sit in one pseudo-project so the
        # same backend plumbing (health, sessions, coverage) serves them, but
        # it is not addressable by name: `get("shared")` is not a project.
        self.shared = shared or Project(name=SHARED, source=None, backends={})
        # {"code": ["verify_xml", ...]} -- published for every backend of that
        # kind unless the backend names its own list
        self.expose = dict(expose or {})
        self._by_alias = {}
        for project in projects:
            for alias in project.aliases:
                self._by_alias[alias.lower()] = project.name
        self.default = default or (projects[0].name if projects else None)

    def __len__(self):
        return len(self._projects)

    def names(self):
        return sorted(self._projects)

    def get(self, name=None):
        """Resolve a project by name or alias. None -> the default project."""
        if not name:
            name = self.default
        if name in self._projects:
            return self._projects[name]
        alias = self._by_alias.get(str(name).lower())
        if alias:
            return self._projects[alias]
        raise KeyError("unknown project %r; known: %s"
                       % (name, ", ".join(self.names()) or "<none>"))


def _backend_from_dict(kind, spec):
    return Backend(kind=kind, url=spec["url"], container=spec.get("container"),
                   cold_ok=bool(spec.get("cold_ok", False)),
                   timeout=spec.get("timeout"), code_root=spec.get("code_root"),
                   expose=spec.get("expose"))


def _project_from_dict(name, raw):
    backends = {}
    for kind, spec in (raw.get("backends") or {}).items():
        backends[kind] = Backend(kind=kind, url=spec["url"],
                                 container=spec.get("container"),
                                 cold_ok=bool(spec.get("cold_ok", False)),
                                 timeout=spec.get("timeout"),
                                 code_root=spec.get("code_root"),
                                 expose=spec.get("expose"))
    return Project(name=name, source=raw.get("source"), backends=backends,
                   aliases=raw.get("aliases"), frozen=raw.get("frozen", False))


def load(path=None):
    """Load the registry. Missing file -> an empty registry, not an error."""
    path = path or os.environ.get("FACADE_REGISTRY") or DEFAULT_PATH
    if not os.path.isfile(path):
        return Registry([])
    with io.open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    projects = [_project_from_dict(name, spec)
                for name, spec in sorted((raw.get("projects") or {}).items())]
    shared = Project(name=SHARED, source=None, backends={
        kind: _backend_from_dict(kind, spec)
        for kind, spec in (raw.get("shared") or {}).items()})
    return Registry(projects, default=raw.get("default"), expose=raw.get("expose"),
                    shared=shared)
