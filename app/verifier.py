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
from typing import NamedTuple, Protocol

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
# Slide text splits into lines and sentences; a dot inside 0.42 has no space after it, so it never splits.
SENTENCE_END = re.compile(r"\n|(?<=[.!?])\s+")
WORD = re.compile(r"[a-z]+")
STOPWORDS = frozenset(
    {"a", "an", "the", "is", "are", "was", "were", "be", "been", "of", "in", "on", "at", "to", "by"}
    | {"for", "with", "and", "or", "as", "it", "its", "that", "this"}
)
SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
DASHES = re.compile("[‐‑‒–—−]")


class Judge(Protocol):
    def supports(self, claim: str, evidence: str) -> tuple[bool, str]: ...


class Num(NamedTuple):
    value: Decimal
    unit: str | None  # canonical unit, or None when the number is bare
    raw: str
    start: int
    end: int


def _norm(s: str) -> str:
    """Canonical form for comparing slide text with claims: unicode, LaTeX, dashes, thousands, spacing."""
    s = re.sub("[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+", lambda m: "^" + m.group(0).translate(SUPERSCRIPTS), s)
    s = DASHES.sub("-", unicodedata.normalize("NFKC", s)).replace("’", "'")
    s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", s)
    s = re.sub(r"[${}\\]", "", s)
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)
    s = re.sub(r"(?<=\d)\s+(?=[a-z%])", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip().lower()


def _sentences(raw: str) -> list[str]:
    """Split slide text into lines and sentences. Runs before _norm, which erases line breaks."""
    return [s for s in SENTENCE_END.split(raw) if s.strip()]


def _numbers(normed: str) -> list[Num]:
    """Every standalone number with its unit and position."""
    out = []
    for m in NUMBER.finditer(normed):
        unit = UNIT.match(normed, m.end())
        name = unit.group(1) if unit else None
        value = Decimal(m.group(0).replace(",", ""))
        out.append(Num(value, UNIT_ALIASES.get(name, name), m.group(0), m.start(), m.end()))
    return out


def _squash(expr: str) -> str:
    """Compare expressions without spacing: o(n log n) == o(nlogn)."""
    return expr.replace(" ", "")


def extract_facts(text: str) -> list[str]:
    """Things that must appear in the source: expressions, numbers outside them, "quoted" phrases, `code`."""
    normed = _norm(text)
    numbers = [n.raw for n in _numbers(EXPR.sub(" ", normed))]
    return EXPR.findall(normed) + numbers + QUOTED.findall(text) + CODE.findall(text)


def _context(claim: str, num: Num) -> set[str]:
    """The nearest content word on each side of a number: not a stopword, a unit, or a number."""
    words = [m for m in WORD.finditer(claim) if m[0] not in STOPWORDS and not UNIT.fullmatch(m[0])]
    before = [m[0] for m in words if m.end() <= num.start]
    after = [m[0] for m in words if m.start() >= num.end]
    return set(before[-1:] + after[:1])


def _number_found(num: Num, claim: str, sentences: list[str]) -> bool:
    """A number with a unit needs that value with the same unit, or bare (a table column may hold the
    unit), anywhere on the cited slides. A bare number needs one sentence holding both the value and
    one of its context words, so "3 recursive calls" can't borrow the 3 from "Lecture 3". A bare number
    with no context words (a lone table cell) only needs the value somewhere."""
    if num.unit:
        seen = {n.unit for s in sentences for n in _numbers(s) if n.value == num.value}
        return num.unit in seen or None in seen
    context = _context(claim, num)
    return any(
        any(n.value == num.value for n in _numbers(s)) and (not context or context & set(WORD.findall(s)))
        for s in sentences
    )


def _missing_facts(text: str, sentences: list[str]) -> list[str]:
    """Facts from text absent from the cited slides' normalized sentences. Expressions compare whole,
    so the 2 in o(n^2) never matches alone. Numbers need matching context (see _number_found), judged
    per line of text so a visual's cells don't lend each other context. Terms match as whole words."""
    evidence = " ".join(sentences)
    have_exprs = {_squash(e) for e in EXPR.findall(evidence)}
    plain = [EXPR.sub(" ", s) for s in sentences]
    missing = []
    for line in text.splitlines():
        claim = _norm(line)
        missing += [e for e in EXPR.findall(claim) if _squash(e) not in have_exprs]
        claim = EXPR.sub(" ", claim)
        missing += [n.raw for n in _numbers(claim) if not _number_found(n, claim, plain)]
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
    sentences = [_norm(s) for n in slides for s in _sentences(deck.slide(n).text)]
    absent = _missing_facts(text, sentences)
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
