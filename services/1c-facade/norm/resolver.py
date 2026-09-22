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
import threading

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

# An extension method intercepting a routine of the base configuration. The
# annotation sits on the lines just above the declaration, possibly next to a
# compilation directive (&НаСервере) or a comment.
_OVERRIDE = re.compile(
    r"^[ \t]*&(?P<directive>Вместо|Перед|После|ИзменениеИКонтроль|"
    r"Around|Before|After|ChangeAndValidate)[ \t]*\([ \t]*\"(?P<target>[^\"]+)\"",
    re.IGNORECASE)
_OVERRIDE_CANON = {"around": "Вместо", "before": "Перед", "after": "После",
                   "changeandvalidate": "ИзменениеИКонтроль"}

# Bumped whenever the index gains a table or a column: a stored index of an
# older shape is rebuilt from scratch, because the incremental pass trusts file
# hashes and would otherwise never fill the new table for unchanged files.
SCHEMA_VERSION = 2


def _override_above(lines, decl_line):
    """(directive, target) of the annotation above a declaration, or None."""
    index = decl_line - 2                     # 1-based line -> previous line index
    for _ in range(6):
        if index < 0:
            return None
        line = lines[index].strip()
        if not line or line.startswith("//"):
            index -= 1
            continue
        if not line.startswith("&"):
            return None
        match = _OVERRIDE.match(lines[index])
        if match:
            directive = match.group("directive")
            return (_OVERRIDE_CANON.get(directive.lower(), directive),
                    match.group("target"))
        index -= 1
    return None


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
CREATE TABLE IF NOT EXISTS refs (
    name   TEXT NOT NULL,
    prefix TEXT NOT NULL,
    path   TEXT NOT NULL,
    line   INTEGER,
    text   TEXT
);
CREATE INDEX IF NOT EXISTS refs_name ON refs(name);
CREATE INDEX IF NOT EXISTS refs_path ON refs(path);
CREATE TABLE IF NOT EXISTS overrides (
    owner     TEXT NOT NULL,
    target    TEXT NOT NULL,
    method    TEXT NOT NULL,
    directive TEXT NOT NULL,
    path      TEXT NOT NULL,
    line      INTEGER
);
CREATE INDEX IF NOT EXISTS overrides_path ON overrides(path);
"""

# References to a metadata object in code, through the access prefixes 1C
# actually uses (`Справочники.X`, `СправочникСсылка.X`, `ДокументОбъект.X`, ...).
# Indexed while the export is being read for symbols anyway: no index covers
# these, and walking the tree per request costs seconds on a bind mount.
_REF = re.compile(
    r"\b(?P<prefix>Справочник|Документ|Перечисление|РегистрСведений|"
    r"РегистрНакопления|РегистрБухгалтерии|РегистрРасчета|ПланВидовХарактеристик|"
    r"ПланСчетов|ПланВидовРасчета|БизнесПроцесс|Задача|Обработка|Отчет|"
    r"ПланОбмена|ЖурналДокументов|Константа)[А-Яа-яЁё]*\s*\.\s*"
    r"(?P<name>[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]*)")


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
        # A resolver outlives a single request and is shared by whatever serves
        # them -- a threading HTTP server hands each call to a fresh thread, and
        # sqlite3 refuses a connection used outside its creating thread. The
        # lock below is what makes lifting that restriction safe, so the two
        # belong together.
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            stored = self.db.execute("PRAGMA user_version").fetchone()[0]
            self.db.executescript(SCHEMA)
            has_files = self.db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        # a stored index of an older shape: its unchanged files would never be
        # re-read, so the new tables would stay empty -- rebuild it once
        self.stale_schema = bool(has_files) and stored < SCHEMA_VERSION

    def close(self):
        with self._lock:
            self.db.close()

    # -- building ---------------------------------------------------------

    def build(self, force=False):
        """Index the export. Incremental by content hash; returns a count map."""
        counts = {"new": 0, "modified": 0, "unchanged": 0, "deleted": 0}
        if self.stale_schema:
            # An index of an older shape starts over -- but as an ordinary
            # incremental pass over an emptied index, with the new version
            # recorded up front. Interrupted halfway (a restart during the
            # minutes a full ERP takes), the next pass resumes from what was
            # committed instead of starting from zero again.
            with self._lock:
                for table in ("symbols", "refs", "overrides", "files"):
                    self.db.execute("DELETE FROM %s" % table)
                self.db.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
                self.db.commit()
            self.stale_schema = False
        with self._lock:
            known = dict(self.db.execute("SELECT path, hash FROM files"))
        seen = set()
        pending = 0
        for full, rel in _walk(self.source):
            seen.add(rel)
            digest = _digest(full)
            if not force and known.get(rel) == digest:
                counts["unchanged"] += 1
                continue
            counts["modified" if rel in known else "new"] += 1
            pending += 1
            if pending % 500 == 0:
                with self._lock:
                    self.db.commit()
            with self._lock:
                self.db.execute("DELETE FROM symbols WHERE path = ?", (rel,))
                self.db.execute("DELETE FROM refs WHERE path = ?", (rel,))
                self.db.execute("DELETE FROM overrides WHERE path = ?", (rel,))
                self._index_file(full, rel)
                self.db.execute(
                    "INSERT INTO files(path, hash) VALUES(?, ?) "
                    "ON CONFLICT(path) DO UPDATE SET hash = excluded.hash",
                    (rel, digest))
        with self._lock:
            for gone in set(known) - seen:
                counts["deleted"] += 1
                self.db.execute("DELETE FROM symbols WHERE path = ?", (gone,))
                self.db.execute("DELETE FROM refs WHERE path = ?", (gone,))
                self.db.execute("DELETE FROM overrides WHERE path = ?", (gone,))
                self.db.execute("DELETE FROM files WHERE path = ?", (gone,))
            self.db.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
            self.db.commit()
        self.stale_schema = False
        return counts

    def _index_file(self, full, rel):
        text = read_source(full)
        offsets = _line_offsets(text)
        # split(chr(10)), not splitlines(): the latter also breaks on a lone
        # CR, on form feeds and on U+2028, so its numbering drifts from the
        # offset table -- and 1C exports do contain stray CRs
        lines = text.split(chr(10))

        owner = owner_of(rel)
        if owner:
            rows = []
            intercepts = []
            for match in _DECL.finditer(text):
                name = match.group("name")
                line = _line_of(offsets, match.start())
                rows.append((name, owner, owner + "." + name, "routine", rel,
                             line, _is_export(text, match.end() - 1)))
                above = _override_above(lines, line)
                if above:
                    intercepts.append((owner, above[1], name, above[0], rel, line))
            if rows:
                self.db.executemany(
                    "INSERT INTO symbols(name, owner, qual, kind, path, line, export) "
                    "VALUES(?,?,?,?,?,?,?)", rows)
            if intercepts:
                self.db.executemany(
                    "INSERT INTO overrides(owner, target, method, directive, path, line) "
                    "VALUES(?,?,?,?,?,?)", intercepts)

        # One reference per object per line: a line naming the same object twice
        # is one usage to a reader.
        seen = set()
        rows = []
        for match in _REF.finditer(text):
            line = _line_of(offsets, match.start())
            key = (match.group("name"), line)
            if key in seen:
                continue
            seen.add(key)
            body = lines[line - 1].strip()[:200] if line <= len(lines) else ""
            rows.append((match.group("name"), match.group("prefix"), rel, line, body))
        if rows:
            self.db.executemany(
                "INSERT INTO refs(name, prefix, path, line, text) VALUES(?,?,?,?,?)", rows)

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

        with self._lock:
            rows = self.db.execute(
                "SELECT qual, owner, export FROM symbols WHERE qual = ?",
                (name,)).fetchall()
        if rows:
            return Resolution(name, id=rows[0][0], kind="routine", confidence="exact")

        bare = name.rsplit(".", 1)[-1]
        params = [bare]
        sql = "SELECT DISTINCT qual, owner, export FROM symbols WHERE name = ?"
        if owner_hint:
            sql += " AND owner = ?"
            params.append(owner_hint)
        with self._lock:
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

    def symbols(self, name, exact=True, limit=50):
        """Routines matching a name, from the index built out of the source.

        Authoritative where a backend is not: every declaration in the export is
        here by construction, while a backend's own function search has gaps --
        measured on УЛК, it returned nothing for `ПолучитьЗначениеНастройки`
        while finding its neighbours.
        """
        bare = (name or "").strip().rsplit(".", 1)[-1]
        if not bare:
            return []
        if exact:
            sql = ("SELECT qual, owner, path, line, export FROM symbols "
                   "WHERE name = ? ORDER BY export DESC, qual LIMIT ?")
            params = (bare, limit)
        else:
            sql = ("SELECT qual, owner, path, line, export FROM symbols "
                   "WHERE name LIKE ? ORDER BY export DESC, qual LIMIT ?")
            params = ("%" + bare + "%", limit)
        with self._lock:
            return self.db.execute(sql, params).fetchall()

    def references(self, name, limit=200):
        """Where a metadata object is used in code.

        No backend index covers this: both of them work at the metadata level
        and answer about attributes and object-to-object links, not call sites.
        Walking the export per request costs seconds over a bind mount, so the
        answer is served from the same index the resolver already builds.
        """
        bare = (name or "").strip().rsplit(".", 1)[-1]
        if not bare:
            return []
        with self._lock:
            return self.db.execute(
                "SELECT path, line, text, prefix FROM refs WHERE name = ? "
                "ORDER BY path, line LIMIT ?", (bare, limit)).fetchall()

    def modules(self, owner):
        """Module paths of a canonical owner (`Справочники.X`, a common module's
        bare name, `Справочники.X.Форма.Y`). Only modules that declare at least
        one routine are known -- an empty module has nothing to describe anyway."""
        owner = (owner or "").strip()
        if not owner:
            return []
        with self._lock:
            return [row[0] for row in self.db.execute(
                "SELECT DISTINCT path FROM symbols WHERE owner = ? ORDER BY path",
                (owner,))]

    def overrides(self):
        """Every interception an extension declares: (owner, target routine,
        extension method, directive, path, line). In the base's own index this
        is empty; it is the extensions' index that carries it."""
        with self._lock:
            return self.db.execute(
                "SELECT owner, target, method, directive, path, line FROM overrides "
                "ORDER BY owner, target").fetchall()

    def stats(self):
        with self._lock:
            files = self.db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            symbols = self.db.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            owners = self.db.execute(
                "SELECT COUNT(DISTINCT owner) FROM symbols").fetchone()[0]
            refs = self.db.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
        return {"files": files, "symbols": symbols, "owners": owners, "refs": refs}


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
