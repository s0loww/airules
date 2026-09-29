# docgen — content format

One content JSON file produces one Word document per configured language:
`<base>_<suffix>.docx` (suffixes from `languages.primary/secondary.suffix` of the docset
config, e.g. `_sp` / `_ru`). Content writers only edit JSON; layout is the builder's job.
Examples below use the bilingual es/ru pair; in general read `es`/`ru` as
`<primary.code>`/`<secondary.code>`.

## Commands

```bash
node docgen/build.mjs --config <cfg.json> content/03-ventas.json       # one file (several allowed)
node docgen/build.mjs --config <cfg.json> 03-ventas.json               # also looked up in <contentDir>
node docgen/build.mjs --config <cfg.json> 03-ventas.json --out <scratch>/preview
node docgen/build.mjs --config <cfg.json> --all                        # every <contentDir>/*.json except "_"-prefixed
node docgen/reference.mjs --config <cfg.json>                          # object reference from <facts>/inventory.json
node docgen/reference.mjs --config <cfg.json> --content-only           # only regenerate the reference content JSON
```

Exit codes: `0` all built · `1` validation failures (nothing is written for an invalid file) ·
`2` execution error (I/O, locked output file, usage or config error, missing UI strings).
Every run writes a report (`<reportDir>/last-build.json`, reference: `last-reference.json`;
per file: status, errors with JSON paths, warnings, output paths, byte sizes, block stats).

Verification helpers (read-only):

```powershell
./docgen/verify-docx.ps1 -Path out.docx -Expect 'string 1','string 2'   # unzip + XML well-formedness + counts + strings; exit 0/1/2
./docgen/opencheck-word.ps1 -Path out.docx [-Pdf]                        # open in hidden Word (COM), page count, optional PDF next to the docx
```

## File layout

```json
{
  "id": "ventas",
  "base": "03_Ventas",
  "set": "base",
  "orientation": "portrait",
  "title":    { "es": "Ventas", "ru": "Продажи" },
  "subtitle": { "es": "…", "ru": "…" },
  "source":   { "commit": "b1a4b0cf", "date": "2026-09-28" },
  "blocks": [ … ]
}
```

| Key | Req. | Meaning |
|---|---|---|
| `id` | yes | Stable identifier (free text). |
| `base` | yes | Output file stem: Unicode letters/digits plus `_ . -`, first a letter or digit (Cyrillic is fine: `90_Справочник_объектов`); no spaces, no `<>:"/\|?*`, no trailing `.`, not a Windows reserved name (CON, PRN, AUX, NUL, COM1–9, LPT1–9). `_<suffix>.docx` is appended per language. |
| `set` | no | Id of a documentation set of the config: output goes to `<outputRoot>/<set.dir>`. |
| `outDir` | no | Output directory, **relative to the content file** (legacy/explicit). Not together with `set`. |
| — | | Neither `set` nor `outDir`: the first set of the config. `--out` overrides everything. |
| `orientation` | no | `portrait` (default) or `landscape` for the whole document. |
| `title` | yes | Text. Title page + running header. |
| `subtitle` | no | Text. Title page. |
| `source` | no | `commit` and `date` printed on the title page. Missing fields default from the config: `source.commit` (else `git rev-parse --short=8 HEAD` of the worktree) and `date` (else today). |
| `blocks` | yes | Non-empty array of blocks (below). |

Keys starting with `_` or `$` are comments and ignored anywhere (`"_comment": "…"`).
Any other unknown key is an error — typos fail loudly.

## Text values

- **Per-language**: `{ "es": "…", "ru": "…" }` — every configured language key required, all strings;
  one empty while another is not is an error. A key of a language that is not configured is an error.
- **Language-neutral**: a plain string (or number) — identifiers, numbers, codes; used in every document.
- **Monolingual config** (no `languages.secondary`): a plain string or `{ "<primary>": "…" }`.

Inline markup inside any text (paragraphs, list items, table cells, notes, captions, headings):

| Markup | Result |
|---|---|
| `` `Document.Venta` `` | Consolas run |
| `**bold**` | bold run |
| `[text](https://…)` or `[text](file.html)` | external / relative hyperlink; relative targets may be Cyrillic (`[схема](бки-01.architecture.html)`) — written as is into the docx (Word resolves raw Unicode targets; only spaces and ``"<>^`{|}`` are percent-encoded) |
| `[text](#anchor)` | internal link to a heading with that `anchor` (must exist — validated) |
| `\n` | line break inside the same paragraph |
| `` \` `` `\*` `\[` `\]` `\\` | literal character |

No other markup (no italics inline; use `"italic": true` on a `p`).

## Blocks

Every block has `type`; any block may carry `"landscape": true|false` to override the document
orientation. Consecutive blocks with the same orientation share one Word section, so put
`"landscape": true` on a heading **and** its wide table to keep them on the same landscape page.

| `type` | Fields | Notes |
|---|---|---|
| `h1` `h2` `h3` | `text`, `anchor`? | Word Heading 1–3 (feed the TOC). `anchor`: `[A-Za-z0-9][A-Za-z0-9_.:-]*` (ASCII), unique, and unique as a Word bookmark (`a_` + slug cut to 30 chars + 8 hex of sha1 — validated); target of `[..](#anchor)`. Generators derive anchors from Cyrillic names as an ASCII slug + hash (see `reference.mjs` `safeAnchor`). Write numbering yourself ("3.2 …"). |
| `p` | `text`, `italic`? | Paragraph. |
| `bullets` / `numbered` | `items`: array of text or `{ "text", "children": [text] }` | One nesting level. Each `numbered` block restarts at 1. |
| `table` | `headers`: [text], `rows`: [[text]], `widths`?, `mono`? | Each row must have exactly `headers.length` cells. `widths`: per column, twips (number) or `"25%"` of the usable width; twips wider than the page are scaled down. Default: equal. `mono`: column indexes rendered in Consolas. Header row repeats on every page; zebra rows. |
| `note` | `kind`: `info`\|`warn`, `title`?, `lines`: [text] | Shaded box. Default title: UI strings `note` / `warn` of the language ("Nota"/"Примечание"/"Note", "Atención"/"Внимание"/"Warning"). |
| `diagram` | `href`, `png`?, `caption` | `png` (path **relative to the content file**) is embedded, scaled to page width; must exist and be a PNG. `href` is written as-is (relative to the **output docx**) as the "Interactive diagram" link; a missing target is a warning, not an error. Caption is auto-numbered with the `figure` UI string ("Figura N." / "Рисунок N." / "Figure N."). |
| `pagebreak` | — | Page break. |
| `toc` | `levels`? (`"1-3"` default) | Word TOC field; the document asks Word to update fields on open (answer "Yes"). |
| `glossary` | `rows`: [`{ "<lang>": term, …, "note"? }`] | One column per configured language (the document language first and bold) + optional note column. Column headers are the language names (UI `lang.<code>.Name`). |

## Generated per document

- Title page: title, subtitle, UI `langLabel` ("Versión en español" / "Русская версия" / "English version"), `source.commit` · `source.date`, `base`.
- Running header with the title; footer `page N of M` in the document language.
- Calibri 10 pt body, Consolas for code, header-row fill `E8EEF4`, zebra `F6F8FA`, warn fill `FDF3E7`, A4 with 2 cm margins.

Fixed UI strings are built in for `es`, `ru`, `en` and can be overridden (or a new language
added) with `uiStrings.<code>.<key>` in the config — see `lib/i18n.mjs` for the keys. A
configured language with neither built-in nor complete override strings stops the build with
exit 2 and the list of missing keys.

## Validation (exit 1)

All errors are collected and printed as `<json.path>: <message>`, e.g.

```
FAIL  content\03-ventas.json  (2 errors)
  x blocks[1].text.ru: missing
  x blocks[23].type: unknown block type "quote" (allowed: h1, h2, h3, p, bullets, numbered, table, note, diagram, pagebreak, toc, glossary)
```

Checked: JSON syntax; required keys; unknown keys; every per-language value anywhere has all
configured languages non-empty; unknown language keys; `set` exists (and not together with
`outDir`); unknown block types; table row arity, `widths`, `mono`; list nesting depth; `png`
exists and is a PNG; duplicate anchors; internal links to missing anchors.

## Conventions for content writers

- Identifiers (`Document.Venta`, register names) stay language-neutral strings or `` `code` ``.
- Keep `_`-prefixed files (e.g. `_sample.json`) for experiments: `--all` skips them.
- `<contentDir>/generated/` is written by generators (`reference.mjs`) — do not edit by hand.
- `examples/_sample.json` exercises every block type (bilingual es/ru); negative fixtures for the
  validator live in `tests/` (`neg-*.json`, all must exit 1 with an es/ru config).
