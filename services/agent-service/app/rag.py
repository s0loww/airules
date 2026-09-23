"""Retrieval over the help KB.

Two interchangeable retrievers:
  - LexicalRetriever   : BM25 over accent-folded tokens. No network, zero cost. Good default
                         for a small KB and the only one used in tests.
  - EmbeddingRetriever : cosine over OpenAI embeddings. Better at paraphrase / bilingual
                         queries; needs an API key (computed once at startup).

Both prefer chunks in the caller's language and drop hits below a small relevance floor so an
off-topic question yields *no* context (the model is then told to say it doesn't know).
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Callable, List, Protocol

from .kb import Chunk

_TOKEN = re.compile(r"[a-z0-9]+")

# Common function words (es + en), accent-folded. Removing them keeps lexical retrieval from
# matching on "how/do/the/de/la/que…", so a genuinely off-topic question retrieves nothing and
# the model is told there is no supporting context (rather than answering from a weak match).
_STOPWORDS = frozenset(
    """
    de la el los las un una unos unas y o u a en que como por para con se su sus lo al del es
    son este esta esto estos estas mi me le les yo tu te nos ese esa eso si no ya muy mas mas
    cual cuales cuando donde quien sobre entre desde hasta cada
    the a an of to in on for with is are was were be been do does did how what when where who
    why which this that these those my me you your it its can could would should will i and or
    """.split()
)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN.findall(_fold(text)) if t not in _STOPWORDS]


class Retriever(Protocol):
    def retrieve(self, query: str, lang: str, k: int) -> List[Chunk]: ...


def _pick(chunks: List[Chunk], scores: List[float], lang: str, k: int, floor: float) -> List[Chunk]:
    order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    same = [i for i in order if chunks[i].lang == lang and scores[i] > floor]
    picked = same[:k]
    if not picked:
        picked = [i for i in order if scores[i] > floor][:k]
    return [chunks[i] for i in picked]


class LexicalRetriever:
    def __init__(self, chunks: List[Chunk], floor: float = 0.0) -> None:
        from rank_bm25 import BM25Okapi

        self.chunks = chunks
        self.floor = floor
        corpus = [tokenize(c.search_text) for c in chunks] or [[""]]
        self._bm25 = BM25Okapi(corpus)

    def retrieve(self, query: str, lang: str, k: int) -> List[Chunk]:
        if not self.chunks:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = list(self._bm25.get_scores(tokens))
        return _pick(self.chunks, scores, lang, k, self.floor)


class SkillsLexicalRetriever:
    """Trigger-weighted keyword overlap for the (tiny) skills corpus.

    BM25 misbehaves here: with 2-3 documents, any term present in most of them gets a
    NEGATIVE idf, dragging whole scores below zero and under the relevance floor. Skill
    routing is deliberately trigger-driven, so a transparent scorer fits better: 3 points
    per query token matching a curated trigger, 1 per token matching the body/description.
    """

    def __init__(self, chunks: List[Chunk]) -> None:
        self.chunks = chunks
        self._tags = [frozenset(tokenize(" ".join(c.tags))) for c in chunks]
        self._words = [frozenset(tokenize(f"{c.title}\n{c.text}")) for c in chunks]

    def retrieve(self, query: str, lang: str, k: int) -> List[Chunk]:
        tokens = set(tokenize(query))
        if not tokens or not self.chunks:
            return []
        scored = []
        for i, chunk in enumerate(self.chunks):
            score = 3 * len(tokens & self._tags[i]) + len(tokens & self._words[i])
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda pair: -pair[0])
        return [self.chunks[i] for _, i in scored[:k]]


class EmbeddingRetriever:
    def __init__(
        self,
        chunks: List[Chunk],
        embed_fn: Callable[[List[str]], List[List[float]]],
        floor: float = 0.15,
    ) -> None:
        self.chunks = chunks
        self.embed_fn = embed_fn
        self.floor = floor
        self._vectors: List[List[float]] = (
            embed_fn([c.search_text for c in chunks]) if chunks else []
        )

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def retrieve(self, query: str, lang: str, k: int) -> List[Chunk]:
        if not self.chunks:
            return []
        qvec = self.embed_fn([query])[0]
        scores = [self._cosine(qvec, v) for v in self._vectors]
        return _pick(self.chunks, scores, lang, k, self.floor)
