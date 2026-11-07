"""Checks that every generated claim is grounded in the slides it cites.

Three layers, cheapest first:
  1. citation  - claim cites slides that exist (deterministic)
  2. exact_fact - numbers / quoted terms / `code` in the claim appear in cited slides (deterministic)
  3. judge     - an LLM decides whether the cited slides support the paraphrase (probabilistic)
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Protocol

from .models import Claim, Deck, Issue, Summary, VerificationReport, VisualSpec

NUMBER = re.compile(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?")
UNIT = re.compile(
    r"\s*(%|percent|[kmg]?hz|[kmgt]b|ns|us|μs|ms|milliseconds?|s|secs?|seconds?|mins?|minutes?|h|hrs?|hours?)(?![a-z])"
)
UNIT_ALIASES = {
    "percent": "%",
    "μs": "us",
    "millisecond": "ms",
    "milliseconds": "ms",
    "sec": "s",
    "secs": "s",
    "second": "s",
    "seconds": "s",
    "mins": "min",
    "minute": "min",
    "minutes": "min",
    "hr": "h",
    "hrs": "h",
    "hour": "h",
    "hours": "h",
}
QUOTED = re.compile(r"[\"“]([^\"”]{2,60})[\"”]")
CODE = re.compile(r"`([^`]{1,60})`")
# Asymptotic notation such as o(n^2) or θ(n log n), one level of nested parentheses, on normalized text.
EXPR = re.compile(r"(?<!\w)[oθω]\((?:[^()]|\([^()]*\))*\)")
SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
DASHES = re.compile("[‐‑‒–—−]")


class Judge(Protocol):
    def supports(self, claim: str, evidence: str) -> tuple[bool, str]: ...


def _norm(s: str) -> str:
    """Canonical form for comparing slide text with claims: unicode, LaTeX, dashes, thousands, spacing."""
    s = re.sub("[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+", lambda m: "^" + m.group(0).translate(SUPERSCRIPTS), s)
    s = DASHES.sub("-", unicodedata.normalize("NFKC", s)).replace("’", "'")
    s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", s)
    s = re.sub(r"[${}\\]", "", s)
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)
    s = re.sub(r"(?<=\d)\s+(?=[a-z%])", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip().lower()


def _numbers(normed: str) -> list[tuple[Decimal, str | None, str]]:
    """(value, canonical unit or None, original text) for every standalone number."""
    out = []
    for m in NUMBER.finditer(normed):
        unit = UNIT.match(normed, m.end())
        name = unit.group(1) if unit else None
        out.append((Decimal(m.group(0).replace(",", "")), UNIT_ALIASES.get(name, name), m.group(0)))
    return out


def _squash(expr: str) -> str:
    """Compare expressions without spacing: o(n log n) == o(nlogn)."""
    return expr.replace(" ", "")


def extract_facts(text: str) -> list[str]:
    """Things that must appear in the source: expressions, numbers outside them, "quoted" phrases, `code`."""
    normed = _norm(text)
    numbers = [n[2] for n in _numbers(EXPR.sub(" ", normed))]
    return EXPR.findall(normed) + numbers + QUOTED.findall(text) + CODE.findall(text)


def _missing_facts(text: str, evidence: str) -> list[str]:
    """Facts from text absent from normalized evidence. Expressions compare whole, so the 2 in o(n^2)
    is never matched alone. Numbers compare by value, terms as whole words.
    A number with a unit passes if the slide has it bare (a table column may hold the unit), but not
    if the slide only has it with a different unit."""
    claim = _norm(text)
    have_exprs = {_squash(e) for e in EXPR.findall(evidence)}
    missing = [e for e in EXPR.findall(claim) if _squash(e) not in have_exprs]
    have = _numbers(EXPR.sub(" ", evidence))
    for value, unit, raw in _numbers(EXPR.sub(" ", claim)):
        units = {u for v, u, _ in have if v == value}
        if not units or (unit and unit not in units and None not in units):
            missing.append(raw)
    for term in QUOTED.findall(text) + CODE.findall(text):
        if not re.search(rf"(?<!\w){re.escape(_norm(term))}(?!\w)", evidence):
            missing.append(term)
    return missing


def _check(label: str, text: str, slides: list[int], deck: Deck, judge: Judge | None) -> list[Issue]:
    """Run the citation, exact-fact, and judge layers, stopping at the first that fails."""
    missing = [n for n in slides if deck.slide(n) is None]
    if missing:
        return [Issue(claim=label, check="citation", detail=f"cites nonexistent slide(s) {missing}")]
    blank = [n for n in slides if not deck.slide(n).text.strip()]
    if blank:
        return [Issue(claim=label, check="citation", detail=f"cites slide(s) with no text {blank}")]

    raw_evidence = "\n".join(deck.slide(n).text for n in slides)
    absent = _missing_facts(text, _norm(raw_evidence))
    if absent:
        return [Issue(claim=label, check="exact_fact", detail=f"not found on slides {slides}: {absent}")]

    if judge:
        ok, why = judge.supports(text, raw_evidence)
        if not ok:
            return [Issue(claim=label, check="judge", detail=why)]
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
    """Check a visual's title and contents like a claim. Numbers pool across cells, so this cannot
    tell whether a right number sits in the wrong cell; the judge sees the whole visual for that."""
    text = "\n".join([visual.title, *_flatten(visual.data)])
    return _check(f"[visual] {visual.title}", text, visual.slides, deck, judge)


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
