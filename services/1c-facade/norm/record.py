"""Normalised facade record: one shape for every backend.

Every answer a backend can give is an entity plus an optional edge. Parsers
build these; verbs assemble them into an envelope. Nothing downstream is
allowed to see a backend-specific shape.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

KINDS = {"metadata", "module", "routine", "attribute", "form", "element", "command",
         "snippet"}
REL_TYPES = {"calls", "called_by", "references", "referenced_by", "typed_as", "overrides",
             "child_of"}
TIERS = {"indexed", "live", "grep"}

# Container mounts differ per backend; strip them so `loc.path` is repo-relative
# and comparable across backends. This is the bridge that restores identity when
# a backend hashes the module name (code_metadata does, for vector chunks).
_MOUNTS = ("/app/metadata_files/", "/app/code/", "/app/metadata/")


def rel_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    p = path.replace(chr(92), "/")
    for m in _MOUNTS:
        if p.startswith(m):
            return p[len(m):]
    return p.lstrip("/")


@dataclass
class Loc:
    path: Optional[str] = None
    line: Optional[int] = None
    end: Optional[int] = None


@dataclass
class Rel:
    """Relation FROM this record TO `to`."""
    type: str
    to: Optional[str] = None
    depth: Optional[int] = None
    via: Optional[str] = None


@dataclass
class Src:
    backend: str
    tool: str
    tier: str = "indexed"
    score: Optional[float] = None


@dataclass
class Record:
    id: str
    kind: str
    name: str
    owner: Optional[str] = None
    loc: Optional[Loc] = None
    sig: Optional[str] = None
    rel: Optional[Rel] = None
    text: Optional[str] = None
    src: Optional[Src] = None

    def errors(self) -> List[str]:
        out = []
        if self.kind not in KINDS:
            out.append(f"kind={self.kind!r}")
        if self.rel and self.rel.type not in REL_TYPES:
            out.append(f"rel.type={self.rel.type!r}")
        if self.src and self.src.tier not in TIERS:
            out.append(f"src.tier={self.src.tier!r}")
        if not self.id or not self.name:
            out.append("empty id/name")
        return out


@dataclass
class ParseResult:
    """Parser output plus the signals that detect parser drift."""
    records: List[Record] = field(default_factory=list)
    resolved_id: Optional[str] = None
    echoed_id: Optional[str] = None   # what the backend itself said it resolved
    declared: Optional[int] = None   # count the backend claimed in its header
    status: str = "ok"               # ok | empty | not_found | unparsed
    note: Optional[str] = None

    sections: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def note_section(self, name: str, declared: Optional[int], parsed: int) -> None:
        self.sections[name] = {"declared": declared if declared is not None else -1,
                               "parsed": parsed}

    @property
    def drift(self) -> List[str]:
        """Where a header count disagrees with what we parsed: the format moved."""
        out = []
        if self.declared is not None and self.declared != len(self.records):
            out.append(f"total: declared {self.declared}, parsed {len(self.records)}")
        for name, c in self.sections.items():
            if c["declared"] >= 0 and c["declared"] != c["parsed"]:
                out.append(f"{name}: declared {c['declared']}, parsed {c['parsed']}")
        return out


def prune(obj: Any) -> Any:
    """dataclass -> dict without None fields, for compact fixtures."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: prune(v) for k, v in vars(obj).items() if v is not None and v != []}
    if isinstance(obj, list):
        return [prune(x) for x in obj]
    return obj
