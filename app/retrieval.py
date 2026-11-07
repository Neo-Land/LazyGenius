"""Keyword (BM25) search over a course's slides, on word stems so "sorting" finds "sort". No vector DB
needed to start; swap in embeddings later and compare retrieval quality with python -m evals.retrieval."""

from __future__ import annotations

import math
import re
from collections import Counter

from snowballstemmer import stemmer

from .models import Deck, Slide

TOKEN = re.compile(r"[a-z0-9]+")
STOP = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "and",
    "in",
    "is",
    "for",
    "on",
    "what",
    "how",
    "why",
    "does",
    "do",
    "are",
    "it",
    "with",
    "from",
    "explain",
    "about",
}


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


def stems(text: str) -> list[str]:
    """Tokens reduced to their Porter2 stems: "returning" and "return" both become "return".
    A fresh stemmer per call, because stemmer objects aren't thread-safe and building one is cheap."""
    return stemmer("english").stemWords(tokenize(text))


def search(
    decks: list[Deck], query: str, k: int = 6, k1: float = 1.5, b: float = 0.75
) -> list[tuple[Deck, Slide, float]]:
    docs = [(d, s, stems(s.text)) for d in decks for s in d.slides]
    if not docs:
        return []
    avg_len = sum(len(t) for *_, t in docs) / len(docs) or 1
    df = Counter(term for *_, toks in docs for term in set(toks))
    n = len(docs)

    scored = []
    for deck, slide, toks in docs:
        tf = Counter(toks)
        score = 0.0
        for q in set(stems(query)):
            if q not in tf:
                continue
            idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
            score += idf * tf[q] * (k1 + 1) / (tf[q] + k1 * (1 - b + b * len(toks) / avg_len))
        if score > 0:
            scored.append((deck, slide, score))
    return sorted(scored, key=lambda x: -x[2])[:k]
