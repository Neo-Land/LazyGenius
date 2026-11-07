"""Deterministic fact matching for the verifier: normalizing text, finding expressions, numbers and
terms on slides, and checking that rare deck terms (names) sit on the slides holding a claim's facts."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from decimal import Decimal
from typing import NamedTuple

from .models import Deck

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
# A term on at most this share of a deck's slides (minimum 1) is a name, like "quicksort" or "bisection".
RARE_SHARE = 0.25
SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
DASHES = re.compile("[‐‑‒–—−]")


class Num(NamedTuple):
    value: Decimal
    unit: str | None  # canonical unit, or None when the number is bare
    raw: str
    start: int
    end: int


Sentence = tuple[int, str]  # (slide number, normalized sentence)


def norm(s: str) -> str:
    """Canonical form for comparing slide text with claims: unicode, LaTeX, dashes, thousands, spacing."""
    s = re.sub("[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+", lambda m: "^" + m.group(0).translate(SUPERSCRIPTS), s)
    s = DASHES.sub("-", unicodedata.normalize("NFKC", s)).replace("’", "'")
    s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", s)
    s = re.sub(r"[${}\\]", "", s)
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)
    s = re.sub(r"(?<=\d)\s+(?=[a-z%])", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip().lower()


def split_sentences(raw: str) -> list[str]:
    """Split slide text into lines and sentences. Runs before norm, which erases line breaks."""
    return [s for s in SENTENCE_END.split(raw) if s.strip()]


def find_numbers(normed: str) -> list[Num]:
    """Every standalone number with its unit and position."""
    out = []
    for m in NUMBER.finditer(normed):
        unit = UNIT.match(normed, m.end())
        name = unit.group(1) if unit else None
        value = Decimal(m.group(0).replace(",", ""))
        out.append(Num(value, UNIT_ALIASES.get(name, name), m.group(0), m.start(), m.end()))
    return out


def squash(expr: str) -> str:
    """Compare expressions without spacing: o(n log n) == o(nlogn)."""
    return expr.replace(" ", "")


def extract_facts(text: str) -> list[str]:
    """Things that must appear in the source: expressions, numbers outside them, "quoted" phrases, `code`."""
    normed = norm(text)
    numbers = [n.raw for n in find_numbers(EXPR.sub(" ", normed))]
    return EXPR.findall(normed) + numbers + QUOTED.findall(text) + CODE.findall(text)


def context_words(claim: str, num: Num) -> set[str]:
    """The nearest content word on each side of a number: not a stopword, a unit, or a number."""
    words = [m for m in WORD.finditer(claim) if m[0] not in STOPWORDS and not UNIT.fullmatch(m[0])]
    before = [m[0] for m in words if m.end() <= num.start]
    after = [m[0] for m in words if m.start() >= num.end]
    return set(before[-1:] + after[:1])


def number_slides(num: Num, claim: str, sentences: list[Sentence]) -> set[int]:
    """Slides that hold this number. A number with a unit needs that value with the same unit, or bare
    (a table column may hold the unit). A bare number needs one sentence holding both the value and
    one of its context words, so "3 recursive calls" can't borrow the 3 from "Lecture 3". A bare number
    with no context words (a lone table cell) only needs the value."""
    if num.unit:
        return {
            slide
            for slide, s in sentences
            if any(n.value == num.value and n.unit in (num.unit, None) for n in find_numbers(s))
        }
    context = context_words(claim, num)
    return {
        slide
        for slide, s in sentences
        if any(n.value == num.value for n in find_numbers(s))
        and (not context or context & set(WORD.findall(s)))
    }


def locate_facts(text: str, sentences: list[Sentence]) -> tuple[list[str], set[int]]:
    """Facts from text missing from the cited slides, and the slides where the found facts sit.
    Expressions compare whole, so the 2 in o(n^2) never matches alone. Numbers need matching context
    (see number_slides), judged per line of text so a visual's cells don't lend each other context.
    Terms match as whole words."""
    by_slide: dict[int, str] = {}
    for slide, s in sentences:
        by_slide[slide] = f"{by_slide.get(slide, '')} {s}"
    plain = [(slide, EXPR.sub(" ", s)) for slide, s in sentences]
    missing: list[str] = []
    found: set[int] = set()

    def place(fact: str, slides: set[int]) -> None:
        if slides:
            found.update(slides)
        else:
            missing.append(fact)

    for line in text.splitlines():
        claim = norm(line)
        for e in EXPR.findall(claim):
            place(e, {n for n, t in by_slide.items() if squash(e) in map(squash, EXPR.findall(t))})
        claim = EXPR.sub(" ", claim)
        for num in find_numbers(claim):
            place(num.raw, number_slides(num, claim, plain))
    for term in QUOTED.findall(text) + CODE.findall(text):
        pattern = rf"(?<!\w){re.escape(norm(term))}(?!\w)"
        place(term, {n for n, t in by_slide.items() if re.search(pattern, t)})
    return missing, found


def content_words(normed: str) -> list[str]:
    """Content words in order, without expressions, stopwords or units."""
    return [w for w in WORD.findall(EXPR.sub(" ", normed)) if w not in STOPWORDS and not UNIT.fullmatch(w)]


def deck_terms(deck: Deck) -> dict[int, set[str]]:
    """Each slide's words plus adjacent word pairs joined, so "quick sort" also reads as "quicksort"."""
    out = {}
    for slide in deck.slides:
        words = content_words(norm(slide.text))
        out[slide.number] = set(words) | {a + b for a, b in zip(words, words[1:], strict=False)}
    return out


def names_in(text: str, known: set[str]) -> list[str]:
    """Deck terms that text mentions, reading two words as one term when the deck has the pair."""
    names = []
    for line in text.splitlines():
        words, i = content_words(norm(line)), 0
        while i < len(words):
            pair = "".join(words[i : i + 2])
            if i + 1 < len(words) and pair in known:
                names.append(pair)
                i += 2
                continue
            if words[i] in known:
                names.append(words[i])
            i += 1
    return names


def misplaced_names(text: str, deck: Deck, fact_slides: set[int]) -> list[str]:
    """Rare deck terms in text, when none of them is on a fact slide (the anchor rule).
    A claim about the fact's slide shares some unusual word with it ("epsilon", "range"); a swapped
    name like "Quicksort ... O(n log n)" on the merge sort slide shares none. Rare alone isn't enough:
    on real decks, plain words like "example" sit on few slides. Common terms and words the deck never
    uses are left to the judge."""
    per_slide = deck_terms(deck)
    counts = Counter(t for terms in per_slide.values() for t in terms)
    cutoff = max(1, int(len(deck.slides) * RARE_SHARE))
    rare = list(dict.fromkeys(n for n in names_in(text, set(counts)) if counts[n] <= cutoff))
    anchored = any(name in per_slide[n] for name in rare for n in fact_slides)
    return [] if anchored else rare
