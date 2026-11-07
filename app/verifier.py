"""Checks that every generated claim is grounded in the slides it cites.

Three layers, cheapest first:
  1. citation  - claim cites slides that exist (deterministic)
  2. exact_fact - expressions / numbers / quoted terms / `code` in the claim appear in cited slides, and
                  rare deck terms (names) sit on the slides holding those facts (deterministic)
  3. judge     - an LLM decides whether the cited slides support the paraphrase (probabilistic)
"""

from __future__ import annotations

from typing import Protocol

from .facts import (
    extract_facts,
    flips_negation,
    locate_facts,
    misplaced_names,
    norm,
    quotes,
    split_sentences,
)
from .models import Claim, Deck, Issue, Summary, VerificationReport, VisualSpec

__all__ = ["Judge", "check_claim", "check_visual", "extract_facts", "verify_claims", "verify_summary"]


class Judge(Protocol):
    def supports(self, claim: str, evidence: str) -> tuple[bool, str]: ...


def _check(
    label: str, text: str, slides: list[int], deck: Deck, judge: Judge | None, *, names: bool = True
) -> list[Issue]:
    """Run the citation, exact-fact, and judge layers, stopping at the first that fails."""
    missing = [n for n in slides if deck.slide(n) is None]
    if missing:
        return [Issue(claim=label, check="citation", detail=f"cites nonexistent slide(s) {missing}")]
    blank = [n for n in slides if not deck.slide(n).text.strip()]
    if blank:
        return [Issue(claim=label, check="citation", detail=f"cites slide(s) with no text {blank}")]

    raw_evidence = "\n".join(deck.slide(n).text for n in slides)
    sentences = [(n, norm(s)) for n in slides for s in split_sentences(deck.slide(n).text)]
    absent, fact_slides = locate_facts(text, sentences)
    if absent:
        return [Issue(claim=label, check="exact_fact", detail=f"not found on slides {slides}: {absent}")]
    has_facts = bool(fact_slides)
    fact_slides = fact_slides or set(slides)  # a claim with no facts names things on any cited slide
    misplaced = misplaced_names(text, deck, fact_slides) if names else []
    if misplaced:
        where = sorted(fact_slides)
        return [
            Issue(claim=label, check="exact_fact", detail=f"{misplaced} not on slides {where} with the facts")
        ]

    if judge:
        ok, why = judge.supports(text, raw_evidence)
        return [] if ok else [Issue(claim=label, check="judge", detail=why)]
    # No judge, so meaning is unchecked. Facts alone can't vouch for a claim with none, or for one that
    # flips its slide's negation; those pass only as a near-verbatim quote of a cited sentence.
    on_fact_slides = [(n, s) for n, s in sentences if n in fact_slides]
    if (not has_facts or flips_negation(text, on_fact_slides)) and not quotes(text, sentences):
        why = "has no checkable facts" if not has_facts else "flips a negation on its slide"
        return [Issue(claim=label, check="judge", detail=f"needs the judge (none ran): {why}, not a quote")]
    return []


def check_claim(claim: Claim, deck: Deck, judge: Judge | None = None) -> list[Issue]:
    """Check one claim against the slides it cites."""
    return _check(claim.text, claim.text, claim.slides, deck, judge)


def _flatten(value) -> list[str]:
    """Every string or number inside a visual's nested data."""
    if isinstance(value, dict):
        return [s for v in value.values() for s in _flatten(v)]
    if isinstance(value, list):
        return [s for v in value for s in _flatten(v)]
    return [str(value)]


def check_visual(visual: VisualSpec, deck: Deck, judge: Judge | None = None) -> list[Issue]:
    """Check a visual's title and contents like a claim, one cell per line. This cannot tell whether a
    right number sits in the wrong cell, and names are skipped because column headers like "Time" are
    generic; the judge sees the whole visual for both."""
    text = "\n".join([visual.title, *_flatten(visual.data)])
    return _check(f"[visual] {visual.title}", text, visual.slides, deck, judge, names=False)


def verify_claims(claims: list[Claim], deck: Deck, judge: Judge | None = None) -> VerificationReport:
    issues = [i for c in claims for i in check_claim(c, deck, judge)]
    bad = {i.claim for i in issues}
    return VerificationReport(
        passed=not issues,
        issues=issues,
        claims_total=len(claims),
        claims_supported=sum(c.text not in bad for c in claims),
    )


def verify_summary(summary: Summary, deck: Deck, judge: Judge | None = None) -> VerificationReport:
    """Verify an abstract and its visuals. Counts cover claims; visual failures only affect `passed`."""
    report = verify_claims(summary.abstract, deck, judge)
    report.issues += [i for v in summary.visuals for i in check_visual(v, deck, judge)]
    report.passed = not report.issues
    return report
