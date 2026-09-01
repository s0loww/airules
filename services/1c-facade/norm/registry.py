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

    __slots__ = ("kind", "url", "container", "cold_ok")

    def __init__(self, kind, url, container=None, cold_ok=False):
        self.kind = kind                # "code" | "graph"
        self.url = url
        self.container = container      # docker name, or None if not managed
        self.cold_ok = cold_ok          # may the facade start it on demand?

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


class Registry(object):
    def __init__(self, projects, default=None):
        self._projects = {p.name: p for p in projects}
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


def _project_from_dict(name, raw):
    backends = {}
    for kind, spec in (raw.get("backends") or {}).items():
        backends[kind] = Backend(kind=kind, url=spec["url"],
                                 container=spec.get("container"),
                                 cold_ok=bool(spec.get("cold_ok", False)))
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
    return Registry(projects, default=raw.get("default"))
