"""The eval runner on a tiny deck, plus sanity checks on the committed golden and planted sets."""

import tomllib
from pathlib import Path

import pytest

from app.harness import summarize_deck
from app.llm import ExtractiveLLM
from app.models import Claim
from evals import decks as eval_decks
from evals.run import captured, run, score_planted, spent
from tests.conftest import GOOD_SUMMARY, HALLUCINATED_SUMMARY, FakeJudge, FakeLLM

EVALS = Path(eval_decks.__file__).parent
GOLDEN = {
    "reviewed": False,
    "point": [
        {"text": "Merge sort time", "slides": [2], "keywords": ["merge sort", "o(n log n)"]},
        {"text": "Not in the summary", "slides": [3], "keywords": ["pivot", "unrelated"]},
    ],
}
PLANTED = {
    "reviewed": False,
    "claim": [
        {
            "deck": "d1",
            "kind": "wrong_number",
            "text": "It took 0.9 seconds.",
            "slides": [4],
            "expect_fail": True,
        },
        {
            "deck": "d1",
            "kind": "paraphrase",
            "text": "Merge sort is best.",
            "slides": [2],
            "expect_fail": True,
        },
        {
            "deck": "d1",
            "kind": "control",
            "text": "It took 0.42 seconds.",
            "slides": [4],
            "expect_fail": False,
        },
    ],
}


def test_captured_needs_a_cited_slide_and_every_keyword():
    point = GOLDEN["point"][0]
    assert captured(point, [Claim(text="Merge sort is O(n log n).", slides=[2])])
    assert not captured(point, [Claim(text="Merge sort is O(n log n).", slides=[3])])
    assert not captured(point, [Claim(text="Merge sort is fast.", slides=[2])])


def test_planted_scores_recall_and_false_alarms(sorting_deck):
    score = score_planted(PLANTED, {"d1": sorting_deck}, FakeJudge())  # judge accepts all: one miss
    assert score["errors_caught"] == 1 and score["errors_total"] == 2 and score["recall"] == 0.5
    assert score["false_alarms"] == 0 and score["controls_total"] == 1
    assert score["wrong_verdicts"][0]["text"] == "Merge sort is best."


def test_run_counts_first_attempt_grounding_and_revisions(sorting_deck):
    llm = FakeLLM(summaries=[HALLUCINATED_SUMMARY, GOOD_SUMMARY])
    report = run({"d1": sorting_deck}, {"d1": GOLDEN}, PLANTED, llm, None, max_usd=1.0, revisions=2)
    assert report["totals"]["grounding_first_attempt"] == pytest.approx(1 / 3)
    assert report["totals"]["coverage"] == 0.5
    assert report["totals"]["revisions_per_deck"] == 1


def test_budget_stop_skips_remaining_decks(sorting_deck):
    llm = ExtractiveLLM()
    llm.usage = {"input_tokens": 10**7, "output_tokens": 0}
    report = run({"d1": sorting_deck}, {"d1": GOLDEN}, PLANTED, llm, None, max_usd=1.0, revisions=0)
    assert report["stopped_early"] and report["decks"] == [] and spent(llm, None) == 40.0


def test_summarize_works_with_extractive(sorting_deck):
    assert summarize_deck(sorting_deck, ExtractiveLLM()).trace


def test_committed_sets_are_complete_and_marked_unreviewed_until_neo_checks():
    goldens = [tomllib.loads(p.read_text()) for p in (EVALS / "golden").glob("*.toml")]
    assert sorted(p.stem for p in (EVALS / "golden").glob("*.toml")) == sorted(eval_decks.DECKS)
    assert all(g["point"] and all(p["keywords"] and p["slides"] for p in g["point"]) for g in goldens)
    planted = tomllib.loads((EVALS / "planted.toml").read_text())
    assert {c["deck"] for c in planted["claim"]} <= set(eval_decks.DECKS)
    assert all((c["kind"] == "control") != c["expect_fail"] for c in planted["claim"])


def test_fetch_rejects_a_changed_file(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_decks, "DECKS", {"a": ("a.pdf", "0" * 64)})
    (tmp_path / "a.pdf").write_bytes(b"different")
    with pytest.raises(ValueError, match="Checksum"):
        eval_decks.fetch_decks(tmp_path)
