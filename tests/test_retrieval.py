import tomllib
from pathlib import Path

from app.retrieval import search
from evals.retrieval import rank_of, score


def test_search_ranks_the_matching_slide_first(sorting_deck):
    _, slide, _ = search([sorting_deck], "pivot worst case")[0]
    assert slide.number == 3


def test_search_with_no_matching_words_returns_nothing(sorting_deck):
    assert search([sorting_deck], "photosynthesis") == []


def test_rank_and_score(sorting_deck):
    questions = [
        {"deck": "d1", "question": "pivot worst case", "slides": [3]},
        {"deck": "d1", "question": "divide and conquer", "slides": [2]},
        {"deck": "d1", "question": "photosynthesis", "slides": [1]},
    ]
    assert rank_of(questions[0], [sorting_deck], k=5) == 1
    result = score(questions, [sorting_deck], k=5)
    assert result["recall_at_5"] == 2 / 3 and result["recall_at_1"] == 2 / 3
    assert result["misses"] == ["photosynthesis"]


def test_retrieval_set_is_well_formed():
    labeled = tomllib.loads((Path("evals") / "retrieval.toml").read_text(encoding="utf-8"))
    assert len(labeled["q"]) == 30
    assert all(q["question"] and q["slides"] and q["deck"].startswith("mit6_0001_") for q in labeled["q"])
