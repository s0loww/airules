"""Name resolver: bare name -> canonical qualifier.

This exists because of a measured defect. `code_metadata` matches a routine by
its bare name, so `ОтправкаПочты` returns callers of *every* routine with that
name (2 of 8 correct, plus one from an unrelated module), while the qualified
form returns nothing at all. `graph_metadata` resolves qualified names but
echoes its own spelling. Merging records from both is impossible until one
canonical id is decided *before* either is called.

The index is built from the configuration export, not from a backend: it must
answer while a backend is down, and it must not depend on whichever indexer
happens to be fresh. SQLite, standard library only, incremental by content
hash.
"""
import hashlib
import io
import os
import re
import sqlite3

# Export directory -> the qualifier 1C itself uses. Only containers that can
# own code or be referenced by type are listed.
CONTAINERS = {
    "AccountingRegisters": "РегистрыБухгалтерии",
    "AccumulationRegisters": "РегистрыНакопления",
    "BusinessProcesses": "БизнесПроцессы",
    "CalculationRegisters": "РегистрыРасчета",
    "Catalogs": "Справочники",
    "ChartsOfAccounts": "ПланыСчетов",
    "ChartsOfCalculationTypes": "ПланыВидовРасчета",
    "ChartsOfCharacteristicTypes": "ПланыВидовХарактеристик",
    "CommonForms": "ОбщиеФормы",
    "CommonModules": "ОбщиеМодули",
    "Constants": "Константы",
    "DataProcessors": "Обработки",
    "DocumentJournals": "ЖурналыДокументов",
    "Documents": "Документы",
    "Enums": "Перечисления",
    "ExchangePlans": "ПланыОбмена",
    "FilterCriteria": "КритерииОтбора",
    "HTTPServices": "HTTPСервисы",
    "InformationRegisters": "РегистрыСведений",
    "Reports": "Отчеты",
    "Sequences": "Последовательности",
    "Tasks": "Задачи",
    "WebServices": "WebСервисы",
}

# Procedure/function declarations. 1C allows Cyrillic identifiers, so \w with
# re.UNICODE is right, but the keywords come in both languages.
_DECL = re.compile(
    r"^[ \t]*(?:Процедура|Функция|Procedure|Function)[ \t]+"
    r"(?P<name>[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]*)[ \t]*\(",
    re.MULTILINE)
_EXPORT_TAIL = re.compile(r"^\s*(?:Экспорт|Export)\b", re.IGNORECASE)


def _is_export(text, open_paren):
    """Is this declaration exported?

    The marker sits after the closing parenthesis of *this* declaration, so the
    parameter list has to be walked rather than scanned for inside a fixed
    window: a window long enough to cover a multi-line parameter list also
    reaches into the next routine and picks up its `Экспорт`.
    """
    depth = 0
    limit = min(len(text), open_paren + 4000)
    for position in range(open_paren, limit):
        char = text[position]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                line_end = text.find("\n", position)
                tail = text[position + 1:line_end if line_end != -1 else len(text)]
                return 1 if _EXPORT_TAIL.match(tail) else 0
    return 0

_MODULE_PATH = re.compile(
    r"^(?P<container>[A-Za-z]+)/(?P<object>[^/]+)/Ext/(?P<module>[A-Za-z]+)\.bsl$")
_FORM_PATH = re.compile(
    r"^(?P<container>[A-Za-z]+)/(?P<object>[^/]+)/Forms/(?P<form>[^/]+)"
    r"/Ext/Form/Module\.bsl$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS symbols (
    name   TEXT NOT NULL,
    owner  TEXT NOT NULL,
    qual   TEXT NOT NULL,
    kind   TEXT NOT NULL,
    path   TEXT NOT NULL,
    line   INTEGER,
    export INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS symbols_qual ON symbols(qual);
CREATE INDEX IF NOT EXISTS symbols_path ON symbols(path);
"""


class Resolution(object):
    """Outcome of a lookup. `candidates` is populated when ambiguous."""

    __slots__ = ("query", "id", "kind", "candidates", "confidence")

    def __init__(self, query, id=None, kind=None, candidates=(), confidence="none"):
        self.query = query
        self.id = id
        self.kind = kind
        self.candidates = list(candidates)
        self.confidence = confidence      # exact | unique | ambiguous | none

    @property
    def ok(self):
        return self.id is not None

    def as_dict(self):
        out = {"query": self.query, "confidence": self.confidence}
        if self.id:
            out["id"] = self.id
            out["kind"] = self.kind
        if self.candidates:
            out["candidates"] = self.candidates
        return out


def read_source(path):
    """1C exports are UTF-8 with BOM, sometimes UTF-16 or cp1251."""
    raw = open(path, "rb").read()
    for encoding in ("utf-8-sig", "utf-16", "cp1251"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", "replace")


def owner_of(rel):
    """Canonical owner for a module path, or None if the path is not a module."""
    match = _FORM_PATH.match(rel)
    if match:
        container = CONTAINERS.get(match.group("container"))
        if not container:
            return None
        return "%s.%s.Форма.%s" % (container, match.group("object"), match.group("form"))
    match = _MODULE_PATH.match(rel)
    if not match:
        return None
    container = match.group("container")
    if container == "CommonModules":
        # a common module is addressed by its bare name in BSL, so that is the
        # canonical owner -- this is the form call sites actually use
        return match.group("object")
    russian = CONTAINERS.get(container)
    if not russian:
        return None
    return "%s.%s" % (russian, match.group("object"))


def _walk(source):
    for root, _dirs, files in os.walk(source):
        for name in files:
            if name.endswith(".bsl"):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, source).replace(os.sep, "/")
                yield full, rel


def _digest(path):
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


class Resolver(object):
    """SQLite-backed symbol index over one configuration export."""

    def __init__(self, source, db_path=":memory:"):
        self.source = source
        self.db = sqlite3.connect(db_path)
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # -- building ---------------------------------------------------------

    def build(self, force=False):
        """Index the export. Incremental by content hash; returns a count map."""
        counts = {"new": 0, "modified": 0, "unchanged": 0, "deleted": 0}
        known = dict(self.db.execute("SELECT path, hash FROM files"))
        seen = set()
        for full, rel in _walk(self.source):
            seen.add(rel)
            digest = _digest(full)
            if not force and known.get(rel) == digest:
                counts["unchanged"] += 1
                continue
            counts["modified" if rel in known else "new"] += 1
            self.db.execute("DELETE FROM symbols WHERE path = ?", (rel,))
            self._index_file(full, rel)
            self.db.execute(
                "INSERT INTO files(path, hash) VALUES(?, ?) "
                "ON CONFLICT(path) DO UPDATE SET hash = excluded.hash", (rel, digest))
        for gone in set(known) - seen:
            counts["deleted"] += 1
            self.db.execute("DELETE FROM symbols WHERE path = ?", (gone,))
            self.db.execute("DELETE FROM files WHERE path = ?", (gone,))
        self.db.commit()
        return counts

    def _index_file(self, full, rel):
        owner = owner_of(rel)
        if not owner:
            return
        text = read_source(full)
        offsets = None
        rows = []
        for match in _DECL.finditer(text):
            if offsets is None:
                offsets = _line_offsets(text)
            name = match.group("name")
            line = _line_of(offsets, match.start())
            export = _is_export(text, match.end() - 1)
            rows.append((name, owner, owner + "." + name, "routine", rel, line, export))
        if rows:
            self.db.executemany(
                "INSERT INTO symbols(name, owner, qual, kind, path, line, export) "
                "VALUES(?,?,?,?,?,?,?)", rows)

    # -- lookup -----------------------------------------------------------

    def resolve(self, name, owner_hint=None, prefer_export=True):
        """Bare or qualified name -> canonical id.

        A qualified query is honoured as-is when it exists. A bare name that
        matches one symbol resolves; several matches come back as candidates so
        the caller can see the ambiguity instead of silently getting the wrong
        one -- which is exactly the failure this module exists to prevent.
        """
        name = (name or "").strip()
        if not name:
            return Resolution(name)

        rows = self.db.execute(
            "SELECT qual, owner, export FROM symbols WHERE qual = ?", (name,)).fetchall()
        if rows:
            return Resolution(name, id=rows[0][0], kind="routine", confidence="exact")

        bare = name.rsplit(".", 1)[-1]
        params = [bare]
        sql = "SELECT DISTINCT qual, owner, export FROM symbols WHERE name = ?"
        if owner_hint:
            sql += " AND owner = ?"
            params.append(owner_hint)
        rows = self.db.execute(sql, params).fetchall()
        if not rows:
            return Resolution(name)
        if len(rows) == 1:
            return Resolution(name, id=rows[0][0], kind="routine", confidence="unique")
        if prefer_export:
            exported = [r for r in rows if r[2]]
            if len(exported) == 1:
                return Resolution(name, id=exported[0][0], kind="routine",
                                  confidence="unique",
                                  candidates=sorted(r[0] for r in rows))
        return Resolution(name, candidates=sorted(r[0] for r in rows),
                          confidence="ambiguous")

    def stats(self):
        files = self.db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        symbols = self.db.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        owners = self.db.execute("SELECT COUNT(DISTINCT owner) FROM symbols").fetchone()[0]
        return {"files": files, "symbols": symbols, "owners": owners}


def _line_offsets(text):
    offsets = [0]
    start = text.find("\n")
    while start != -1:
        offsets.append(start + 1)
        start = text.find("\n", start + 1)
    return offsets


def _line_of(offsets, position):
    low, high = 0, len(offsets) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if offsets[mid] <= position:
            low = mid
        else:
            high = mid - 1
    return low + 1
