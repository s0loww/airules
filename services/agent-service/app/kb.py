"""Load the help/ knowledge base into retrievable chunks.

`index.yaml` is the source of truth for topic metadata; each referenced markdown file holds
a bilingual body split by `<!-- lang:es -->` / `<!-- lang:en -->` markers. One chunk is
produced per (topic, language).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List

import yaml

_LANG_MARKER = re.compile(r"<!--\s*lang:([a-z]{2})\s*-->", re.IGNORECASE)


@dataclass
class Chunk:
    topic_id: str
    title: str
    subsystem: str
    lang: str
    tags: List[str] = field(default_factory=list)
    text: str = ""

    @property
    def search_text(self) -> str:
        return f"{self.title}\n{' '.join(self.tags)}\n{self.text}"


def _split_by_lang(body: str, primary_lang: str = "es") -> Dict[str, str]:
    """Split a markdown body into {lang: text} using the lang markers.

    Anything before the first marker (e.g. a shared `# Title`) is ignored for retrieval.
    A body without markers is in the tenant's primary language.
    """
    sections: Dict[str, str] = {}
    matches = list(_LANG_MARKER.finditer(body))
    if not matches:
        # No markers — the whole body is in the primary language.
        text = body.strip()
        return {primary_lang: text} if text else {}
    for i, m in enumerate(matches):
        lang = m.group(1).lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[start:end].strip()
        if text:
            sections[lang] = text
    return sections


def load_chunks(help_dir: str, primary_lang: str = "es") -> List[Chunk]:
    index_path = os.path.join(help_dir, "index.yaml")
    with open(index_path, "r", encoding="utf-8") as fh:
        index = yaml.safe_load(fh) or {}

    chunks: List[Chunk] = []
    for topic in index.get("topics", []):
        topic_id = topic.get("id")
        rel = topic.get("file")
        if not topic_id or not rel:
            continue
        path = os.path.join(help_dir, rel)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                body = fh.read()
        except FileNotFoundError:
            continue
        sections = _split_by_lang(body, primary_lang)
        tags = [str(t) for t in topic.get("tags", [])]
        subsystem = topic.get("subsystem", "")
        for lang, text in sections.items():
            title = (topic.get(f"title_{lang}") or topic.get(f"title_{primary_lang}")
                     or topic.get("title") or topic_id)
            chunks.append(
                Chunk(
                    topic_id=topic_id,
                    title=title,
                    subsystem=subsystem,
                    lang=lang,
                    tags=tags,
                    text=text,
                )
            )
    return chunks


_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def load_skills(skills_dir: str) -> List[Chunk]:
    """Load agent-skills/*.md (model-facing playbooks) as retrievable chunks.

    Each file carries YAML frontmatter (name, description, triggers); the body is the
    instruction text injected into the prompt when the skill matches the user's question.
    Files without valid frontmatter (e.g. README.md) are skipped. Missing dir -> [].
    """
    chunks: List[Chunk] = []
    if not skills_dir or not os.path.isdir(skills_dir):
        return chunks
    for entry in sorted(os.listdir(skills_dir)):
        if not entry.endswith(".md"):
            continue
        path = os.path.join(skills_dir, entry)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            continue
        m = _FRONTMATTER.match(raw)
        if not m:
            continue
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        name = str(meta.get("name") or "").strip()
        if not name:
            continue
        description = str(meta.get("description") or "").strip()
        triggers = str(meta.get("triggers") or "").split()
        body = raw[m.end():].strip()
        if not body:
            continue
        # lang="en" by convention (internal tooling); the retriever falls back across
        # languages, so Spanish questions still match via triggers/embeddings.
        chunks.append(
            Chunk(
                topic_id=name,
                title=description,
                subsystem="skill",
                lang="en",
                tags=triggers,
                text=body,
            )
        )
    return chunks


def title_map(chunks: List[Chunk], lang: str) -> Dict[str, str]:
    """topic_id -> title in the requested language (falling back to any language)."""
    result: Dict[str, str] = {}
    for c in chunks:
        if c.topic_id not in result or c.lang == lang:
            result[c.topic_id] = c.title
    return result
