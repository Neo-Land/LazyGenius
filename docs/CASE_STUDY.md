# Case study: LazyGenius

## Problem
AI summaries of lecture slides can invent numbers or cite the wrong slide, and a student has no quick way to
tell. A confident wrong note is worse than a missing one.

## Design
A harness around the model. The model only does judgment work and must return structured claims with slide
citations. Plain code checks each claim, cheapest check first, feeds failures back for a bounded number of
revisions, and drops what still fails. See [ARCHITECTURE.md](ARCHITECTURE.md) and [decisions/](decisions/).

## What failed along the way
Each of these looked fine until something tested it against reality.

- **Numbers matched as substrings.** The first verifier passed "4 seconds" on a slide saying "0.42 seconds", and
  every test was green. Writing edge-case tests first exposed it. Numbers now compare by value, sign, and unit.
- **Visuals skipped the check.** Tables and concept maps had their citations checked but not their contents,
  which broke the project's own rule. They now get the same checks as claims.
- **Footers counted as evidence.** Real MIT decks showed every slide ending in a page number, so a wrong "9" passed
  on page 9. Synthetic fixtures never would have revealed this. Footers are now removed during parsing.
- **Licensing surprise.** The plan was to commit open-license decks, but MIT excludes some images on certain slides
  from its license. The repo now stores links and checksums, and the demo removes those images.
- **Stale slide under a new label.** During hand testing, a citation briefly showed the old slide under the new
  slide number, which is misleading in an app built on trust. Unit tests had passed.

## Numbers
From an offline run over 5 MIT lectures, using draft test sets. See [EVALS.md](EVALS.md) for method and limits.

| Metric | Result |
|---|---|
| Mechanical errors caught by plain code | 29 / 29 |
| Errors of meaning caught by plain code | 0 / 11 (judge's job, not yet measured) |
| False alarms on true claims | 0 / 18 |
| Backend tests | 113, 97% line coverage |
| Live model metrics | not run yet |

## What's next
1. Run the live evals, then review the draft sets and report real grounding, coverage, and judge recall.
2. Catch misplaced numbers, which plain code currently misses completely.
3. OCR for scanned slides, and a comparison of embeddings against keyword search.
