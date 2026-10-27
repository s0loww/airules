"""Mappers for the platform servers: documentation, ITS, syntax check, templates.

These servers are not about any one configuration, and they answer in prose:
markdown articles, a link list, NDJSON diagnostics. The parsers cut that prose
into records at the seams the servers themselves print, and keep the text --
there is no structure underneath worth inventing.

One property matters more than any field: whether an answer is empty. The
documentation search ranks without a threshold, so it answers *something* to
any query; only the exact-name lookup can say "not found". The routing in
`verbs.docs` is built around that.

The images of 27.09.2026 changed two layouts: documentation answers with a
JSON envelope (`schema_version` 4.x) and the syntax check with a TOON document
under `events`. Both layouts are parsed; the old ones stay for the fixtures and
for a server not yet updated.
"""
import csv
import json
import re

from record import Loc, ParseResult, Record, Src

_NOT_FOUND = re.compile(r"^\s*No documentation found", re.IGNORECASE)
_HEADING = re.compile(r"^#\s+(?P<title>.+)$", re.MULTILINE)
_LINK = re.compile(r"^\[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\)", re.MULTILINE)
_TEMPLATE = re.compile(r"\*\*Template:\*\*\s*(?P<id>.+)")
_TEMPLATE_ID = re.compile(r"^\*\*ID:\*\*\s*(\d+)\s*$", re.MULTILINE)
_TEMPLATE_DESC = re.compile(r"\*\*Description:\*\*\s*(?P<desc>.+)")
_CODE_BLOCK = re.compile(r"```[a-zA-Z]*\n(?P<code>.*?)```", re.DOTALL)


def parse_docs(text, tool="docsearch", backend="docs"):
    """Platform documentation: articles separated by a `---` line, each opening
    with `# Объект.Метод (Object.Method)`."""
    if not text or not text.strip():
        return ParseResult(status="empty")
    if text.lstrip().startswith("{"):
        return _parse_docs_json(text, tool, backend)
    if _NOT_FOUND.match(text):
        return ParseResult(status="not_found", note=text.strip()[:200])
    res = ParseResult(status="ok")
    for chunk in re.split(r"\n-{3,}\n", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = _HEADING.match(chunk)
        if not match and res.records:
            # `---` also separates sections *inside* an article ("Методическая
            # информация"): a chunk without its own heading continues the last one
            res.records[-1].text += "\n---\n" + chunk
            continue
        title = match.group("title").strip() if match else chunk.splitlines()[0][:120]
        # "ТаблицаЗначений.Найти (ValueTable.Find)" -> the Russian qualifier is the id
        ident = title.split(" (")[0].strip()
        res.records.append(Record(
            id="doc:" + ident, kind="snippet", name=ident, text=chunk,
            src=Src(backend=backend, tool=tool, tier="indexed")))
    if not res.records:
        res.status = "empty"
    return res


def _parse_docs_json(text, tool, backend):
    """Documentation 4.x: `outcome` says found or not, `results` carry the
    article as a list of lines. A miss still lists the nearest documents --
    those are not an answer, so a miss stays not_found."""
    try:
        payload = json.loads(text)
    except ValueError:
        return ParseResult(status="unparsed", note="docs: broken JSON")
    if not isinstance(payload, dict) or "outcome" not in payload:
        return ParseResult(status="unparsed", note="docs: no outcome in the answer")
    outcome = payload.get("outcome")
    if outcome == "not_found":
        return ParseResult(status="not_found",
                           note=(payload.get("message") or "not found")[:200])
    if outcome != "ok":
        return ParseResult(status="unparsed", note="docs: outcome %r: %s" % (
            outcome, (payload.get("message") or "")[:160]))
    res = ParseResult(status="ok")
    for item in payload.get("results") or []:
        citation = item.get("citation") or {}
        ident = citation.get("full_name") or citation.get("name") or item.get("doc_id")
        if not ident:
            continue
        # a method with several call forms lists them instead of one signature
        variants = [v.get("signature") for v in citation.get("variants") or []
                    if v.get("signature")]
        record = Record(
            id="doc:" + ident, kind="snippet", name=ident,
            sig=citation.get("signature") or ("; ".join(variants) or None),
            text="\n".join(item.get("snippets") or []),
            src=Src(backend=backend, tool=tool, tier="indexed", score=item.get("score")))
        res.records.append(record)
        # An ambiguous name -- overloads of one method, or one name on several
        # objects -- answers with candidates and no body; so does a partial hit
        # (`snippet_count`). docinfo takes the doc_id back and returns it whole.
        if item.get("doc_id") and (not record.text or item.get("snippet_count")):
            res.fetch[record.id] = item["doc_id"].split("#")[0]
    resolution = payload.get("resolution") or {}
    if resolution.get("status") == "ambiguous":
        res.note = "docs: %r is ambiguous, %s candidate(s), %s shown" % (
            payload.get("query"), resolution.get("candidate_count") or payload.get("total"),
            payload.get("returned"))
    elif payload.get("truncated"):
        res.note = "docs: %s of %s results" % (payload.get("returned"), payload.get("total"))
    if not res.records:
        res.status = "empty"
    return res


def parse_its(text):
    """ITS search: a header line, then `[Раздел > Статья](url)` per hit."""
    if not text or not text.strip():
        return ParseResult(status="empty")
    res = ParseResult(status="ok")
    found = re.search(r"найдено\s+\*\*(\d+)\*\*", text)
    for match in _LINK.finditer(text):
        url = match.group("url")
        res.records.append(Record(
            id=url, kind="snippet", name=match.group("title").strip(), text=url,
            src=Src(backend="codecheck", tool="its_help", tier="indexed")))
    if found and not res.records:
        res.note = "ITS reported %s documents but no links parsed" % found.group(1)
        res.status = "unparsed"
    elif not res.records:
        res.status = "empty"
    return res


def parse_syntax(text):
    """bsl-analyzer NDJSON: a `start` line, one `file` line with diagnostics.
    Lines come back 0-based; records carry them 1-based like everything else."""
    if not text or not text.strip():
        return ParseResult(status="empty")
    if text.lstrip().startswith("events"):
        return _parse_syntax_toon(text)
    res = ParseResult(status="empty")
    parsed_any = False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        parsed_any = True
        for diag in item.get("diagnostics") or []:
            start = diag.get("start_line")
            number = start + 1 if isinstance(start, int) else None
            res.records.append(Record(
                id="%s:%s" % (diag.get("code"), number), kind="snippet",
                name=diag.get("code") or "diagnostic", owner=diag.get("severity"),
                loc=Loc(line=number), sig=diag.get("code"), text=diag.get("message"),
                src=Src(backend="syntax", tool="syntaxcheck", tier="indexed")))
    if not parsed_any:
        return ParseResult(status="unparsed", note="syntaxcheck: no NDJSON lines")
    if res.records:
        res.status = "ok"
    return res


_TOON_TABLE = re.compile(r"^(?P<indent>\s*)diagnostics\[(?P<n>\d+)\]\{(?P<fields>[^}]*)\}:\s*$")
_TOON_EMPTY = re.compile(r"^\s*diagnostics:\s*\[\]\s*$")
_TOON_INT = re.compile(r"^\s*(?P<key>line_base|total_diagnostics|failed_files):\s*(?P<value>\d+)\s*$")


def _parse_syntax_toon(text):
    """bsl-analyzer 0.2.8x via syntaxcheck 3.4: a TOON document. Diagnostics are
    a table -- `diagnostics[N]{code,message,...}:` and N comma-separated rows,
    strings quoted with backslash escapes. `line_base` says how lines count.

    An empty list is the answer "clean", so it is trusted only when the rows
    read match both the table header and the `total_diagnostics` of the `done`
    event; anything else is unparsed, never empty."""
    lines = text.splitlines()
    numbers = {}
    for line in lines:
        match = _TOON_INT.match(line)
        if match:
            numbers.setdefault(match.group("key"), int(match.group("value")))
    base = numbers.get("line_base", 1)
    rows, declared, tables = [], 0, 0
    index = 0
    while index < len(lines):
        match = _TOON_TABLE.match(lines[index])
        if not match:
            if _TOON_EMPTY.match(lines[index]):
                tables += 1
            index += 1
            continue
        tables += 1
        fields = match.group("fields").split(",")
        count = int(match.group("n"))
        declared += count
        body = lines[index + 1:index + 1 + count]
        for row in csv.reader([line.strip() for line in body],
                              escapechar="\\", doublequote=False):
            if len(row) == len(fields):
                rows.append(dict(zip(fields, row)))
        index += 1 + count
    total = numbers.get("total_diagnostics")
    if not tables or len(rows) != declared or (total is not None and total != declared):
        return ParseResult(status="unparsed", note=(
            "syntaxcheck: read %d diagnostics of %d declared, %s reported"
            % (len(rows), declared, total)))
    res = ParseResult(status="ok" if rows else "empty")
    if numbers.get("failed_files"):
        res.status = "unparsed"
        res.note = "syntaxcheck: %d file(s) failed to analyse" % numbers["failed_files"]
    for diag in rows:
        start = diag.get("start_line", "")
        number = int(start) + (1 - base) if start.lstrip("-").isdigit() else None
        res.records.append(Record(
            id="%s:%s" % (diag.get("code"), number), kind="snippet",
            name=diag.get("code") or "diagnostic", owner=diag.get("severity"),
            loc=Loc(line=number), sig=diag.get("code"), text=diag.get("message"),
            src=Src(backend="syntax", tool="syntaxcheck", tier="indexed")))
    return res


def parse_templates(text, tool="templatesearch"):
    """Code templates: `**Template:** id`, `**Description:** ...`, a fenced code
    block, repeated."""
    if not text or not text.strip():
        return ParseResult(status="empty")
    res = ParseResult(status="ok")
    starts = [m.start() for m in _TEMPLATE.finditer(text)]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        chunk = text[start:end]
        # 4.x prints `**ID:** 4229` right before the title. The title is not
        # unique ("Листинг 8" names a dozen) and get_template takes the number.
        numbers = _TEMPLATE_ID.findall(text[starts[index - 1] if index else 0:start])
        ident = numbers[-1] if numbers else _TEMPLATE.search(chunk).group("id").strip()
        desc = _TEMPLATE_DESC.search(chunk)
        code = _CODE_BLOCK.search(chunk)
        res.records.append(Record(
            id="template:" + ident, kind="snippet",
            name=desc.group("desc").strip() if desc else ident,
            text=code.group("code").strip() if code else chunk.strip(),
            src=Src(backend="templates", tool=tool, tier="indexed")))
    if not res.records:
        # get_template answers with JSON rather than the search layout
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None
        if isinstance(payload, dict) and (payload.get("code") or payload.get("id")):
            ident = str(payload.get("id") or "?")
            res.records.append(Record(
                id="template:" + ident, kind="snippet",
                name=payload.get("description") or ident, text=payload.get("code"),
                src=Src(backend="templates", tool=tool, tier="indexed")))
        else:
            res.status = "empty"
    return res


def as_text(text, backend, tool, name):
    """A generative or free-form answer: one record, the text as is."""
    if not text or not text.strip():
        return ParseResult(status="empty")
    return ParseResult(status="ok", records=[Record(
        id="%s:%s" % (backend, tool), kind="snippet", name=name, text=text,
        src=Src(backend=backend, tool=tool, tier="live"))])
