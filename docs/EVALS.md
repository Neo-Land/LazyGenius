# Evaluation

**Status:** verifier numbers below are real but offline. There are **no live model numbers yet**, and the
golden and planted sets are Claude's drafts until Neo reviews them. Don't quote these as final.

## Results

### Verifier on planted claims (offline, 2026-11-07)
Over 5 MIT lecture decks (see `evals/SOURCES.md`). Two modes: **deterministic layers** alone (a judge
that accepts everything, so only citation and exact-fact checks can reject), and **no judge**, the strict
offline mode where a claim with nothing checkable, or one that flips its slide's negation, must be a
near-verbatim quote or it is dropped.

| Kind of claim | Deterministic layers | No judge | What it means |
|---|---|---|---|
| Wrong number | 12 / 12 | 12 / 12 | number isn't on the cited slide |
| Digit fragment | 3 / 3 | 3 / 3 | `4` when the slide says `40` |
| Fact from the wrong slide | 5 / 5 | 5 / 5 | true fact, wrong citation |
| Nonexistent slide | 3 / 3 | 3 / 3 | invented citation |
| Wrong term or code | 6 / 6 | 6 / 6 | renamed function or term |
| Misplaced number | 2 / 5 | 2 / 5 | number is on the slide, but attached to the wrong thing |
| Unsupported paraphrase | 1 / 6 | 6 / 6 | no checkable fact, wrong meaning |
| **Errors caught** | **32 / 40** | **37 / 40** | 29 / 40 before Phase 1 |
| True controls rejected | 0 / 18 | 2 / 18 | correct claims dropped |

The deterministic layers add no false alarms. The 2 controls dropped with no judge ("break exits only the
innermost loop", "Bisection converges on the order of log2N steps") have nothing checkable and aren't
quotes, so without a judge they can't be verified: that's the cost of "verified or dropped". Whether the
real judge accepts them and catches the paraphrases is **unmeasured** until a live run. Still missed:
swapped percentages (numbers with units skip the context check) and code results whose context word is
generic or split onto another line.

The name check was tuned here: "a rare deck term must be on the fact's slide" caught 36 / 40 but raised
false alarms to 5 / 18 (plain words like "example" sit on few slides), so it only fires when *none* of a
claim's rare terms is on a fact slide.

### Full pipeline
Offline mode only quotes slides, so it proves the pipeline runs and nothing about quality. Its 100%
grounding is guaranteed by construction, and its 10% coverage is not a model score. Live numbers:

| Metric | Live result |
|---|---|
| Grounding on first attempt | not run |
| Coverage of golden points | not run |
| Recall with the judge | not run |
| Revisions per deck | not run |
| Cost per deck | not run |

## Metrics
- **Grounding:** share of claims passing the verifier on the first attempt, before any revision.
- **Coverage:** share of golden points captured. A point counts if one claim cites one of its slides and
  contains all its keywords. This undercounts claims worded differently.
- **Verifier recall:** share of planted errors flagged, reported by kind.
- **False alarms:** true control claims wrongly rejected.
- **Cost:** estimated from token counts, using deliberately high prices in `evals/run.py`.

## Limits
- The sets were written by the same author as the verifier, which flatters the score until reviewed.
- One course and 40 planted errors is a small sample.

## Reproduce
```bash
python -m evals.run                         # free, downloads the decks
python -m evals.run --live --max-usd 1      # costs money, run by Neo
```
Or run the **Eval** workflow from the repo's Actions tab, after adding the `ANTHROPIC_API_KEY` secret for
live mode. The budget stop is checked between decks, so a run can pass it by about one deck.
