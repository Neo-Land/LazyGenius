# Evaluation

**Status:** verifier numbers below are real but offline. There are **no live model numbers yet**, and the
golden and planted sets are Claude's drafts until Neo reviews them. Don't quote these as final.

## Results

### Verifier on planted claims (offline, 2026-10-30, no judge)
Over 5 MIT lecture decks (see `evals/SOURCES.md`).

| Kind of claim | Flagged | What it means |
|---|---|---|
| Wrong number | 12 / 12 | number isn't on the cited slide |
| Digit fragment | 3 / 3 | `4` when the slide says `40` |
| Fact from the wrong slide | 5 / 5 | true fact, wrong citation |
| Nonexistent slide | 3 / 3 | invented citation |
| Wrong term or code | 6 / 6 | renamed function or term |
| **Misplaced number** | **0 / 5** | number is on the slide, but attached to the wrong thing |
| **Unsupported paraphrase** | **0 / 6** | no checkable fact, wrong meaning |
| True control claims (false alarms) | 0 / 18 | correct claims wrongly rejected |

Overall recall is 29 / 40 (72.5%): every mechanical error and no errors of meaning. The last two kinds are
what the AI judge is for, and whether it catches them is **unmeasured** until a live run.

### Retrieval (offline, 2026-11-07)
30 student-style questions over the 5 MIT decks (`evals/retrieval.toml`, Claude's unreviewed draft), each
labeled with the slides that answer it. Search runs over all 5 decks at once, as it would over a course.

| Search | Recall@1 | Recall@5 | MRR |
|---|---|---|---|
| BM25, exact words (baseline) | 20 / 30 | 26 / 30 | 0.748 |

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
python -m evals.retrieval                   # free, retrieval recall@5
python -m evals.run --live --max-usd 1      # costs money, run by Neo
```
Or run the **Eval** workflow from the repo's Actions tab, after adding the `ANTHROPIC_API_KEY` secret for
live mode. The budget stop is checked between decks, so a run can pass it by about one deck.
