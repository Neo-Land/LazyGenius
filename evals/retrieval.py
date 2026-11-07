"""Retrieval eval: recall@1, recall@5 and MRR for questions labeled with the slides that answer them.
Offline and free: python -m evals.retrieval
Your own courses, kept out of git: python -m evals.retrieval --decks data/cs101 --questions my_qs.toml
(deck ids are the file names without extension)."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from datetime import date
from pathlib import Path

from app.models import Deck
from app.parsing import SUPPORTED, parse_file
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


def load_decks(folder: Path | None) -> list[Deck]:
    """The MIT eval decks, or every slide file in a local folder (deck id = file name stem)."""
    if folder is None:
        fetch_decks()
        return [parse_file(DECKS_DIR / f"{name}.pdf", "evals", name) for name in DECKS]
    files = sorted(f for f in folder.iterdir() if f.suffix.lower() in SUPPORTED)
    return [parse_file(f, folder.name, f.stem) for f in files]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decks", type=Path, help="folder of your own slide files (default: MIT decks)")
    parser.add_argument("--questions", type=Path, default=ROOT / "retrieval.toml", help="labeled questions")
    args = parser.parse_args()
    decks = load_decks(args.decks)
    labeled = tomllib.loads(args.questions.read_text(encoding="utf-8"))
    report = {**score(labeled["q"], decks), "reviewed": labeled.get("reviewed", False)}
    report["date"] = date.today().isoformat()
    name = "retrieval" if args.decks is None else f"retrieval-{args.decks.name}"
    out = ROOT / "reports" / f"{name}-{report['date']}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
