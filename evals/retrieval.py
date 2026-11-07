"""Retrieval eval: recall@1, recall@5 and MRR for questions labeled with the slides that answer them.
Offline and free: python -m evals.retrieval"""

from __future__ import annotations

import json
import sys
import tomllib
from datetime import date
from pathlib import Path

from app.models import Deck
from app.parsing import parse_file
from app.retrieval import search

from .decks import DECKS, DECKS_DIR, fetch_decks

ROOT = Path(__file__).parent


def rank_of(question: dict, decks: list[Deck], k: int) -> int | None:
    """1-based rank of the first labeled slide in the top k results, or None if none is there."""
    for rank, (deck, slide, _) in enumerate(search(decks, question["question"], k=k), start=1):
        if deck.id == question["deck"] and slide.number in question["slides"]:
            return rank
    return None


def score(questions: list[dict], decks: list[Deck], k: int = 5) -> dict:
    """Recall@1, recall@k, mean reciprocal rank, and the questions that missed the top k."""
    ranks = [rank_of(q, decks, k) for q in questions]
    n = max(len(questions), 1)
    return {
        "questions": len(questions),
        "recall_at_1": sum(r == 1 for r in ranks) / n,
        f"recall_at_{k}": sum(r is not None for r in ranks) / n,
        "mrr": sum(1 / r for r in ranks if r) / n,
        "misses": [q["question"] for q, r in zip(questions, ranks, strict=True) if r is None],
    }


def main() -> int:
    fetch_decks()
    decks = [parse_file(DECKS_DIR / f"{name}.pdf", "evals", name) for name in DECKS]
    labeled = tomllib.loads((ROOT / "retrieval.toml").read_text(encoding="utf-8"))
    report = {**score(labeled["q"], decks), "reviewed": labeled["reviewed"], "date": date.today().isoformat()}
    out = ROOT / "reports" / f"retrieval-{report['date']}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
