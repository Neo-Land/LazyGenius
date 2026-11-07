import pytest

from app.models import Claim, Deck, Slide, Summary, VisualSpec
from app.verifier import check_claim, extract_facts, verify_summary
from tests.conftest import GOOD_SUMMARY, HALLUCINATED_SUMMARY, FakeJudge


def test_grounded_summary_passes(sorting_deck):
    report = verify_summary(GOOD_SUMMARY, sorting_deck)
    assert report.passed, report.issues
    assert report.claims_supported == report.claims_total == 3


def test_catches_wrong_number_and_fake_slide(sorting_deck):
    report = verify_summary(HALLUCINATED_SUMMARY, sorting_deck)
    checks = {i.check for i in report.issues}
    assert not report.passed
    assert checks == {"exact_fact", "citation"}
    assert report.claims_supported == 1


def test_number_must_be_on_the_cited_slide_not_just_anywhere(sorting_deck):
    # 0.42 is real, but it's on slide 4, not slide 2
    issues = check_claim(Claim(text="Merge sort took 0.42 seconds.", slides=[2]), sorting_deck)
    assert issues and issues[0].check == "exact_fact"


def test_code_identifiers_must_match(sorting_deck):
    ok = check_claim(Claim(text="Halves are combined with `merge()`.", slides=[2]), sorting_deck)
    bad = check_claim(Claim(text="Halves are combined with `combine()`.", slides=[2]), sorting_deck)
    assert ok == [] and bad[0].check == "exact_fact"


def test_number_formatting_is_normalized(sorting_deck):
    claim = Claim(text="It sorted 1000000 integers.", slides=[4])  # slide says 1,000,000
    assert check_claim(claim, sorting_deck) == []


def test_judge_catches_unsupported_paraphrase(sorting_deck):
    claim = Claim(text="Quick sort is always faster than merge sort.", slides=[3])
    assert check_claim(claim, sorting_deck) == []  # no facts to string-match
    issues = check_claim(claim, sorting_deck, FakeJudge("always faster"))
    assert issues[0].check == "judge"


def test_extract_facts():
    assert extract_facts('Load factor 0.75 and "chaining" via `put()`') == ["0.75", "chaining", "put()"]


def _deck(*texts):
    return Deck(
        id="x", course="c", title="t", slides=[Slide(number=i + 1, text=t) for i, t in enumerate(texts)]
    )


def _grounded(claim: str, *slides: str) -> bool:
    cited = list(range(1, len(slides) + 1))
    return check_claim(Claim(text=claim, slides=cited), _deck(*slides)) == []


@pytest.mark.parametrize(
    "claim, slide",
    [
        ("Runs in `O(n²)` time.", "Worst case O(n^2)"),
        ("Runs in `O(n^2)` time.", "Worst case O(n²)"),
        ("Grows like `O(n^2)`.", "Grows like $O(n^{2})$"),
        ("About 10⁻³ of requests fail.", "About 10^-3 of requests fail"),
        ("Half is 1/2.", r"Half is $\frac{1}{2}$"),
        ("A latency of 5 ms.", "Latency: 5ms"),
        ("A latency of 5ms.", "Latency: 5 ms"),
        ("It took 2 seconds.", "Time: 2 sec"),
        ("It took 3.5 seconds.", "Time: 3.50 s"),
        ("Between 5 and 10 nodes.", "Use 5–10 nodes"),
        ("The low was -5 degrees.", "Low: −5 degrees"),
        ("Use the “file” mode.", "Use the ﬁle mode"),
        ("Latency was 5 ms.", "Latency (ms) | 5"),
        ("In CS2 we cover trees.", "Trees"),
    ],
)
def test_equivalent_forms_pass(claim, slide):
    assert _grounded(claim, slide)


@pytest.mark.parametrize(
    "claim, slide",
    [
        ("It took 4 seconds.", "It took 0.42 seconds"),  # digits inside another number
        ("There are 2 nodes.", "There are 12 nodes"),
        ("The low was 5 degrees.", "Low: -5 degrees"),  # sign matters
        ("The low was -5 degrees.", "Low: 5 degrees"),
        ("A latency of 5 ms.", "Latency: 5 s"),  # wrong unit
        ("Between 5 and 11 nodes.", "Use 5-10 nodes"),
        ('Called "merge" here.', "The merger step"),  # term inside a longer word
        ("It uses `sort`.", "It uses resort"),
        ("Up 50%.", "Took 50 ms"),
    ],
)
def test_wrong_facts_fail(claim, slide):
    assert not _grounded(claim, slide)


def test_multi_slide_citation_pools_evidence_from_cited_slides_only():
    deck = _deck("Latency is 5 ms", "Throughput is 9 rps", "Memory is 7 GB")
    assert check_claim(Claim(text="5 ms and 9 rps.", slides=[1, 2]), deck) == []
    assert check_claim(Claim(text="5 ms and 7 GB.", slides=[1, 2]), deck)[0].check == "exact_fact"


def test_one_bad_citation_fails_a_multi_slide_claim():
    deck = _deck("Latency is 5 ms")
    assert check_claim(Claim(text="5 ms.", slides=[1, 9]), deck)[0].check == "citation"


def _table(rows, slides=(1,)):
    data = {"columns": ["Algorithm", "Time"], "rows": rows}
    return VisualSpec(kind="table", title="Times", data=data, slides=list(slides))


def test_visual_with_a_wrong_number_fails():
    deck = _deck("Merge sort took 0.42 seconds")
    good = verify_summary(Summary(abstract=[], visuals=[_table([["Merge sort", "0.42 s"]])]), deck)
    bad = verify_summary(Summary(abstract=[], visuals=[_table([["Merge sort", "0.9 s"]])]), deck)
    assert good.passed
    assert not bad.passed and bad.issues[0].check == "exact_fact"
    assert bad.issues[0].claim == "[visual] Times"


def test_judge_also_reviews_visual_contents():
    deck = _deck("Merge sort")
    summary = Summary(abstract=[], visuals=[_table([["Merge sort", "fastest ever"]])])
    assert verify_summary(summary, deck, FakeJudge("fastest ever")).issues[0].check == "judge"


def test_citing_a_blank_slide_fails():
    deck = _deck("", "Real text")
    assert check_claim(Claim(text="A claim with no facts.", slides=[1]), deck)[0].check == "citation"


# Phase 1 review cases (docs/BUILD_PLAN.md). No judge: the deterministic layers alone should catch them.
# xfail(strict=True) keeps CI green until the fix lands, then forces removing the marker.
REVIEW_DECK = _deck(
    "Merge sort: worst case O(n log n). Uses 2 recursive calls. Lecture 3",
    "Quicksort worst case O(n^2) when pivot is bad",
    "Binary search requires a sorted list",
)


def _known_miss(claim, slide, why, name):
    return pytest.param(claim, slide, marks=pytest.mark.xfail(strict=True, reason=why), id=name)


@pytest.mark.parametrize(
    "claim, slide",
    [
        _known_miss("Merge sort's worst case is O(n^2).", 1, "2 matches '2 recursive calls'", "exponent"),
        _known_miss("Merge sort makes 3 recursive calls.", 1, "3 matches 'Lecture 3'", "lecture-number"),
        _known_miss("Quicksort's worst case is O(n log n).", 1, "names unchecked", "swapped-name"),
        _known_miss("Binary search does not require a sorted list.", 3, "negation ignored", "negation"),
    ],
)
def test_review_cases_are_caught(claim, slide):
    assert check_claim(Claim(text=claim, slides=[slide]), REVIEW_DECK)


def test_review_control_claim_passes():
    assert check_claim(Claim(text="Merge sort's worst case is O(n log n).", slides=[1]), REVIEW_DECK) == []
