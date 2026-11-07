# Project Plan — Lecture Harness

> **Superseded (2026-11-07) by [`BUILD_PLAN.md`](BUILD_PLAN.md).** Kept as a record of the
> original build under the old name. Don't work from this file.

**Goal:** a portfolio-ready agent harness that turns lecture slides into verified abstracts and
visuals, with a web UI for per-course questions, backed by measured accuracy numbers.

**Current phase:** Phase 7. All code is done. Remaining tasks are Neo's: live runs, reviewing the eval sets,
a real Canvas sync, connecting hosts, and the portfolio site.

## How every phase runs
- Work happens on branches, one PR per task group, merged by Claude Code after green CI (Neo's decision, 2026-10-30).
- Each phase ends with: all tasks ticked, docs updated, CI green on `main`, a git tag
  (`v0.<phase>.0`), and a "Phase N" entry in `CHANGELOG.md`.
- Expect **3–6 pushes per phase** (push at the end of every task, not once at the end).
- Definition of done for any task: tests written/updated → lint + tests + coverage pass locally →
  docs updated per `CLAUDE.md` → PR opened with the template filled in.

---

## Phase 0 — Repo, CI, and guardrails
**Branch:** `ci/phase0-setup` · **Tag:** `v0.0.0`
- [x] Neo: create GitHub repo, push scaffold, set branch protection (see `SETUP_ACCESS.md`)
- [x] Add `ruff` config to `pyproject.toml`; fix all lint/format issues
- [x] Add `pytest-cov`; make CI enforce coverage ≥ 85%
- [x] Confirm `.github/workflows/ci.yml` runs on PRs and pushes to `main` (Python 3.11 + 3.13)
- [x] Add Dependabot config for pip and GitHub Actions (weekly)
- [x] Add CI status badge to `README.md`
- [x] Docs: verify `ARCHITECTURE.md` matches the code; write ADR 0002 (FastAPI + SQLite + BM25 to start)

**Done when:** a PR shows the `backend (3.11)` and `backend (3.13)` checks passing and `main` is protected.

## Phase 1 — Harden the backend
**Branches:** `feat/phase1-verifier-edge-cases`, `feat/phase1-robustness`, `feat/phase1-cli`
- [x] Verifier edge cases, each with a test first:
  superscripts/unicode (`O(n²)` vs `O(n^2)`), units (`5 ms` vs `5ms`), ranges, negative numbers,
  numbers inside words (`CS2`), LaTeX-ish formulas, multi-slide citations
- [x] Verify facts inside `VisualSpec.data` (numbers, terms) against cited slides, not just the citations
- [x] Unit test for `Store` (round trips, `is_current`, course listing)
- [x] Config validation on startup with clear errors (missing key, bad data dir)
- [x] Structured logging (JSON lines) for every harness attempt: deck, attempt, supported/total
- [x] Handle scanned PDFs: detect slides with no text and mark them `needs_ocr` (don't crash)
- [x] CLI: `python -m app ingest <file> --course "CS 2"` and `python -m app ask ...`
- [x] Persist harness traces (every attempt + verifier report) for debugging and evals
- [x] Docs: README CLI section, ARCHITECTURE update, CHANGELOG

**Done when:** coverage ≥ 85%, CLI works offline against fixtures.

## Phase 2 — Slide images + first real model run
**Branches:** `feat/phase2-slide-images`, `feat/phase2-live-smoke`
- [x] Render each slide to PNG at ingest (PyMuPDF `get_pixmap`; PPTX via LibreOffice
      if installed, otherwise text-only fallback). Endpoint: `GET /decks/{id}/slides/{n}/image`
- [x] `scripts/smoke_live.py`: runs one open-license deck through the real model and prints the
      verification report. **Neo runs this himself** with his key; Claude Code only writes it.
- [x] Prompt/version tracking: store model id + prompt version with every summary
- [x] Docs: ADR on image rendering, `docs/RESULTS.md` instructions
- [ ] Neo: run `scripts/smoke_live.py` and paste the result into `docs/RESULTS.md`

**Done when:** one real lecture produces a passing, verified summary end to end.

## Phase 3 — Evaluation suite (your resume numbers)
**Branches:** `feat/phase3-golden-set`, `feat/phase3-eval-runner`, `ci/phase3-eval-workflow`
- [x] Golden set: 5 decks from MIT OpenCourseWare (CC BY-NC-SA), downloaded with checksums rather than
      committed (see ADR 0004), with a `SOURCES.md` attribution file
- [x] For each deck, `evals/golden/<deck>.toml`: key points + slide numbers, drafted by Claude
- [ ] Neo: review the golden and planted sets, then set `reviewed = true` in each file
- [x] Planted-error set: summaries with known mistakes, to measure what the verifier catches
- [x] `python -m evals.run` computing:
      grounding rate (claims passing), coverage (golden points captured),
      verifier recall on planted errors, revisions per deck, cost per deck
- [x] Offline mode (fake model, runs in normal CI) + live mode
- [x] `.github/workflows/eval.yml`: **manual trigger only** (`workflow_dispatch`), uses the
      `ANTHROPIC_API_KEY` secret, uploads the report as an artifact
- [x] Docs: `docs/EVALS.md` (method, offline results, how to reproduce), ADR on metrics
- [ ] Neo: run `python -m evals.run --live --max-usd 1` and add the numbers to `docs/EVALS.md`

**Done when:** `EVALS.md` has real numbers from a live run.

## Phase 4 — Frontend (Next.js)
**Branches:** `feat/phase4-web-scaffold`, `feat/phase4-lecture-page`, `feat/phase4-ask`, `ci/phase4-frontend`
- [x] `web/`: Next.js (App Router) + TypeScript; typed API client generated from FastAPI's OpenAPI
- [x] Course sidebar → lecture list → lecture page: abstract with citation chips,
      visuals rendered from `VisualSpec` (native tables and timelines, Mermaid for concept maps), slide viewer
- [x] Clicking a citation opens that slide image
- [x] Ask box scoped to a course; shows "not covered in the slides" for insufficient evidence
- [x] Verification badge per lecture (e.g. "12/12 claims verified, 1 revision")
- [x] Tests: component tests (Vitest + Testing Library) and one Playwright smoke test against a mocked API
- [x] CI: add `frontend` job (lint, typecheck, test, build); add it to required checks
- [x] Accessibility: keyboard navigation, alt text for slide images, color contrast
- [x] Docs: README run instructions for both apps, ARCHITECTURE diagram update, ADR on frontend choices

**Done when:** you can upload a deck, read the verified lecture page, and ask a cited question in the browser.

## Phase 5 — Canvas sync for real
**Branches:** `feat/phase5-canvas-tests`, `feat/phase5-scheduled-sync`
- [ ] Neo checks whether Montclair allows Canvas personal access tokens
- [x] Tests for `CanvasClient` with `httpx.MockTransport`: pagination, filtering, download, 401/403 handling
- [x] "Sync now" button in the UI + last-synced time per course
- [x] Optional scheduled sync (local cron/launchd instructions; never in public CI)
- [x] Course name mapping/ignore list in config
- [x] Docs: `docs/CANVAS.md` (how to get a token, what the app reads, how to revoke it)

- [ ] Neo: run a real sync on his machine (needs the token check above)

**Done when:** Neo runs sync on his own machine and new lectures appear verified. Token never leaves `.env`.

## Phase 6 — Packaging and deployment (CD)
**Branches:** `feat/phase6-docker`, `ci/phase6-release`
- [x] `Dockerfile` (backend) + `docker-compose.yml` (backend + web)
- [x] **Demo mode:** public deployment serves only the open-license eval decks, read-only;
      `/upload` and `/sync` disabled; rate-limited `/ask` with a daily spend cap
- [x] Release workflow: on tag `v*`, run full CI, build images, publish a GitHub Release with notes from `CHANGELOG.md`
- [ ] Neo: deploy: web on Vercel, API on Render/Fly (Neo connects these via their GitHub integrations;
      deploys only from `main`/tags)
- [x] Docs: `docs/DEPLOYMENT.md`, ADR on hosting, security notes in README

**Done when:** a public demo URL works and `v1.0.0` is released.

## Phase 7 — Portfolio polish
**Branch:** `docs/phase7-case-study`
- [x] README: screenshot, architecture diagram, eval results table, "how accuracy is enforced"
- [x] `docs/CASE_STUDY.md`: problem, design, what failed, numbers, what's next
- [x] Resume bullets drafted (in the Phase 7 PR description for Neo to edit); update after live evals
- [ ] Add the project to the portfolio site (waiting on Neo's go-ahead)

**Done when:** a recruiter can understand it from the README in 60 seconds.

---

## Stretch ideas (only after v1.0.0)
Embeddings vs BM25 comparison in evals · OCR for scanned slides · flashcards/quiz generation from
verified claims · multi-LMS adapters (Blackboard/Moodle) · per-claim confidence scores.
