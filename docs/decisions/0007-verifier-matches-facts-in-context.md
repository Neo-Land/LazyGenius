# 0007 — The verifier matches facts in context, and drops what it can't check

- **Status:** accepted
- **Date:** 2026-11-07

## Context
A review found 4 wrong claims that passed the verifier with no judge. The exact-fact layer treated a slide as
a bag of numbers: `O(n^2)` matched the 2 in "2 recursive calls", and "3 recursive calls" matched "Lecture 3".
A swapped algorithm name, or a negation, passed because the claim had no numbers at all.

## Options considered
1. Same-sentence matching only: simple, but "Lecture 3" is a sentence too, so it doesn't fix the 3.
2. Number plus a neighbouring word from the same slide sentence: fixes the 3, but needs exemptions for units
   and table cells.
3. Names: every rare deck term must be on the fact's slide (36/40 caught, but 5/18 true claims rejected on
   real decks) versus an anchor rule, where at least one rare term must be (32/40, 0/18).
4. No judge: let fact-less claims pass, mark them "unverified", or drop them unless they quote the slide.

## Decision
- Expressions like `O(n^2)` are one fact, compared whole.
- A bare number needs one slide sentence holding the value and one of its neighbouring words. Numbers with
  units keep the old rule, and numbers with only stopwords around them need the value anywhere.
- Names use the anchor rule: rare deck terms (on at most 25% of slides) fail a claim only when none of them
  is on a slide holding its facts. Visuals skip this check.
- With no judge, a claim with no checkable facts, or one that flips its slide's negation, passes only as a
  near-verbatim quote of a cited sentence.

## Consequences
- Offline eval: deterministic layers catch 32/40 planted errors (29 before) with 0/18 false alarms. With no
  judge, 37/40 are caught and 2/18 true claims with nothing checkable are dropped.
- Known misses: swapped percentages (units skip context), generic context words ("evaluates"), and a common
  phrase that anchors a swapped name. Each is a test or an eval row, not a hidden gap.
- The 25% cutoff was tuned on one course. Re-check false alarms when real course decks arrive (Phase 3-4).
- Matching moved to `app/facts.py`; `app/verifier.py` keeps the layers.
