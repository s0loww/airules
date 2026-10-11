"""Anonymise captured fixtures before they enter the repository.

`capture.py` writes raw server responses into `fixtures.local/` (gitignored):
those carry a real customer configuration -- object prefixes, the configuration
name, and full method bodies including internal hostnames. None of that belongs
in a public distribution.

This step maps identifying tokens to neutral ones and drops code bodies, while
leaving the *format* untouched -- and format is the only thing the parsers are
tested against. Counts are preserved, so the invariants in `test_parsers.py`
stay meaningful.

    python capture.py       # fixtures.local/  (real, local only)
    python anonymise.py     # fixtures/        (neutral, committed)
    python test_parsers.py --update
"""
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "fixtures.local")
DST = os.path.join(HERE, "fixtures")

# Ordered: longer keys first so a prefix never eats a longer match.
MAP = (
    ("БалтийскийЛизинг", "ДемоКонфигурация"),
    ("Project_BKI_Extension", "Demo_Extension"),
    ("КонтурБКИ", "ДемоРасширение"),
    ("Project_BL_Extension", "Demo_Base_Extension"),
    ("УправлениеЛизингом", "ДемоУправление"),
    ("mail2.nomos.fil", "smtp.example.invalid"),
    ("web_SAP", "web_ERP"),
    ("БЛ_", "ДЕМО_"),
    ("бл_", "демо_"),
    ("иас_", "инт_"),
    ("лиз_", "лз_"),
)

# Fields whose value is source code: replaced wholesale, never mapped.
# `document` is a code chunk in codesearch and a raw metadata line in
# metadatasearch -- either way customer text, never format.
BODY_FIELDS = ("body", "document")
BODY_STUB = "Процедура Заглушка()\n\t// тело вырезано при анонимизации\nКонецПроцедуры"


def map_text(text):
    for old, new in MAP:
        text = text.replace(old, new)
    return text


def strip_bodies(obj):
    if isinstance(obj, dict):
        return {k: (BODY_STUB if k in BODY_FIELDS and isinstance(v, str) else strip_bodies(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_bodies(x) for x in obj]
    return obj


def leaks(text):
    """Anything identifying that survived the mapping."""
    found = set()
    for pat in (r"Балтийск\w*", r"nomos\w*", r"mail\d*\.[a-z.]+",
                r"\bБЛ_\w+", r"\bбл_\w+", r"\bиас_\w+", r"\bлиз_\w+", r"\bweb_SAP\w*"):
        found.update(re.findall(pat, text))
    return sorted(found)


def main():
    if not os.path.isdir(SRC):
        print("fixtures.local/ missing -- run capture.py against the live servers first")
        return 1
    os.makedirs(DST, exist_ok=True)
    residual = {}
    for name in sorted(os.listdir(SRC)):
        raw = io.open(os.path.join(SRC, name), encoding="utf-8").read()
        if name.endswith(".json"):
            out = json.dumps(strip_bodies(json.loads(raw)), ensure_ascii=False)
            out = map_text(out)
        else:
            out = map_text(raw)
        with io.open(os.path.join(DST, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
        rest = leaks(out)
        if rest:
            residual[name] = rest
        print("  " + name + ("  LEAK: " + ", ".join(rest[:4]) if rest else ""))
    if residual:
        print()
        print("анонимизация неполная — расширить MAP и повторить")
        return 1
    print()
    print("чисто: идентифицирующих токенов не осталось")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
