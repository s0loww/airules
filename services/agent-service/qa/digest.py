"""Dump a compact digest of every KB topic (id, title, tags, es headings, lead) so the
QA question set can be authored against what each topic actually says.

Usage: python qa/digest.py   (run from agent-service/; writes qa/digest.md)
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kb import load_chunks  # noqa: E402

# The tenant's knowledge base: first argument, else the historical sibling layout.
HELP_DIR = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[2] / "help")


def main() -> None:
    out = io.StringIO()
    chunks = [c for c in load_chunks(HELP_DIR) if c.lang == "es"]
    out.write(f"# KB digest — {len(chunks)} es topics\n\n")
    for c in chunks:
        headings = re.findall(r"^#{2,4}\s+(.+)$", c.text, re.MULTILINE)
        lead = re.sub(r"\s+", " ", c.text).strip()[:360]
        out.write(f"## {c.topic_id} | {c.title} | subsystem={c.subsystem}\n")
        out.write(f"tags: {', '.join(c.tags)}\n")
        if headings:
            out.write(f"headings: {' | '.join(headings)}\n")
        out.write(f"lead: {lead}\n\n")
    dest = Path(__file__).resolve().parent / "digest.md"
    dest.write_text(out.getvalue(), encoding="utf-8")
    print(f"wrote {dest} ({len(chunks)} topics)")


if __name__ == "__main__":
    main()
