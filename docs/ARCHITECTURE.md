# Architecture

## Flow
```
            ┌──────────── deterministic code ────────────┐   ┌─ model ─┐
LMS/upload ─► parsing.py ─► store.py ─► harness.py ─────────► llm.py
                                         │      ▲               │
                                         ▼      │ feedback      ▼
                                      verifier.py ◄──────── Summary / Answer (JSON)
                                         │
                                         ▼
                                  store.py ─► api.py ─► web/ (Phase 4)
```

## Modules
| Module | Responsibility | Deterministic? |
|---|---|---|
| `models.py` | Shared pydantic types (`Slide`, `Deck`, `Claim`, `VisualSpec`, `Summary`, `Answer`, reports) | yes |
| `parsing.py` | PDF/PPTX → numbered slides (text, tables, speaker notes) | yes |
| `verifier.py` | Citation, exact-fact, and judge checks per claim | layers 1–2 yes, 3 no |
| `facts.py` | Fact matching for the exact-fact layer: normalizing, numbers in context, expressions, names | yes |
| `llm.py` | Claude calls with forced tool use; `ClaudeJudge`; `ExtractiveLLM` for offline mode | no (offline mode yes) |
| `harness.py` | Generate → verify → revise loop; answers over retrieved slides | yes (orchestration) |
| `retrieval.py` | BM25 keyword search over a course's slides | yes |
| `store.py` | SQLite: decks, summaries, traces of every attempt, processed LMS file versions | yes |
| `pipeline.py` | Sync new/changed LMS files and ingest them | yes |
| `lms/canvas.py` | Canvas REST client (token auth, pagination, download) | yes |
| `api.py` | FastAPI endpoints for the frontend | yes |
| `__main__.py` | CLI: `ingest`, `ask` | yes |
| `config.py` | Settings; `validate_settings` fails fast at startup | yes |
| `logs.py` | JSON-lines log formatter | yes |

## Key invariants
1. Every `Claim` cites at least one slide (enforced by the model schema).
2. A claim is shown only if it passes the verifier; after `max_revisions`, failing claims are dropped.
3. Answers cite renumbered context slides that are mapped back to real `(deck, slide)` pairs, so
   the model can only cite slides it was shown.
4. Visuals go through the same checks as claims and are dropped if they still fail. Numbers pool
   across a visual's cells, so only the judge can catch a right number in the wrong cell.
5. LMS files are processed once per version (`source_version` = Canvas `updated_at`).

## Slide images
Ingest renders each slide to `data/images/<deck>/<n>.png` as a best-effort step (see ADR 0003). Every
summary records the model id and prompt version that produced it.

## Demo mode
`HARNESS_DEMO=true` refuses `/upload` and `/sync` and limits `/ask`. The demo Docker image seeds its database
at build time, with no API key by default. Limits are in memory, so the demo must run as one server.

## Canvas sync
Runs only on the owner's machine and never in CI. Files are processed once per version, and a course's
`last_synced` time updates after each check. See `docs/CANVAS.md`.

## Frontend
`web/` is a Next.js app that calls the API from the browser. Its types are generated from `web/openapi.json`,
and a backend test fails if that file is stale. See ADR 0005.

## Evals
`evals/` measures the harness and is never imported by `app/`. See `docs/EVALS.md`.

## Scanned slides and footers
Repeated footers and page numbers are removed at parsing so they can't count as evidence.
A slide with no extractable text is flagged `needs_ocr`. Citing it fails verification, and a fully
scanned deck skips the model call entirely and stores an empty summary.

## How facts are compared
Slide text and claims are normalized first (unicode, superscripts, LaTeX, dashes, thousands separators,
spacing). Numbers then compare by value and sign, so `4` never matches inside `0.42`, and `3.5` equals
`3.50`. A unit must match unless the slide shows the number bare, since a table header may hold it.
Quoted terms and `code` must match whole words.

## Endpoints
See `README.md` → Endpoints. Interactive docs at `/docs` when the server runs.
