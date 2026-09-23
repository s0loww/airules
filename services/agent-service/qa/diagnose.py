"""Retrieval diagnosis: print the embedding retriever's top hits for given queries.

Usage: .venv/Scripts/python.exe qa/diagnose.py "query 1" "query 2" ...
Builds the same EmbeddingRetriever the service uses (one embedding batch, ~cents).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.kb import load_chunks, load_skills  # noqa: E402
from app.llm import LLM  # noqa: E402
from app.rag import EmbeddingRetriever, SkillsLexicalRetriever  # noqa: E402


def main() -> None:
    queries = sys.argv[1:]
    if not queries:
        print("usage: diagnose.py <query> [...]")
        return
    s = get_settings()
    llm = LLM(s)
    chunks = load_chunks(s.help_dir)
    retriever = EmbeddingRetriever(chunks, llm.embed)
    skills = load_skills(s.skills_dir)
    sk = SkillsLexicalRetriever(skills)

    out = []
    for q in queries:
        out.append(f"## {q}")
        qvec = llm.embed([q])[0]
        scored = sorted(
            ((EmbeddingRetriever._cosine(qvec, v), c) for v, c in zip(retriever._vectors, chunks)),
            key=lambda p: -p[0],
        )
        for score, c in scored[:8]:
            if c.lang != "es":
                continue
            out.append(f"  {score:.3f}  {c.topic_id}")
        hits = sk.retrieve(q, "es", s.skills_top_k)
        out.append(f"  skills: {[h.topic_id for h in hits]}")
        out.append("")
    Path(__file__).with_name("diagnose_out.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out).encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
