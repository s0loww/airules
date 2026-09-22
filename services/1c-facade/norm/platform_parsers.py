"""Mappers for the platform servers: documentation, ITS, syntax check, templates.

These servers are not about any one configuration, and they answer in prose:
markdown articles, a link list, NDJSON diagnostics. The parsers cut that prose
into records at the seams the servers themselves print, and keep the text --
there is no structure underneath worth inventing.

One property matters more than any field: whether an answer is empty. The
documentation search ranks without a threshold, so it answers *something* to
any query; only the exact-name lookup can say "not found". The routing in
`verbs.docs` is built around that.
"""
import json
import re

from record import Loc, ParseResult, Record, Src

_NOT_FOUND = re.compile(r"^\s*No documentation found", re.IGNORECASE)
_HEADING = re.compile(r"^#\s+(?P<title>.+)$", re.MULTILINE)
_LINK = re.compile(r"^\[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\)", re.MULTILINE)
_TEMPLATE = re.compile(r"\*\*Template:\*\*\s*(?P<id>.+)")
_TEMPLATE_DESC = re.compile(r"\*\*Description:\*\*\s*(?P<desc>.+)")
_CODE_BLOCK = re.compile(r"```[a-zA-Z]*\n(?P<code>.*?)```", re.DOTALL)


def parse_docs(text, tool="docsearch", backend="docs"):
    """Platform documentation: articles separated by a `---` line, each opening
    with `# Объект.Метод (Object.Method)`."""
    if not text or not text.strip():
        return ParseResult(status="empty")
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
        ident = _TEMPLATE.search(chunk).group("id").strip()
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
