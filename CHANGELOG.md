# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]
### Added
- Retrieval eval (`python -m evals.retrieval`): 30 labeled questions, recall@1, recall@5 and MRR.

### Changed
- Renamed the project from Lecture Harness to LazyGenius (README, package names, Docker images, UI title, docs).

### Fixed
- Search matches word forms (Porter2 stems): "sorting" finds "sort". Recall@5 26/30 → 29/30.
- Reverted a dependency update that broke clean frontend installs. Required checks now apply to admins.

## [0.6.0] — 2026-10-31
### Added
- Plain-English explanation, case study, and a rewritten README.

### Added
- Docker images and `docker-compose.yml`.
- Demo mode: read-only, open-license slides only, rate-limited questions with a daily cap.
- Release workflow: tags run full CI, build images, and publish notes from this changelog.

### Changed
- Questions are limited to 500 characters.

### Added
- Canvas: "Sync with Canvas" button, `python -m app sync`, last-synced times, a course ignore list,
  and friendly course names. One unreadable file no longer stops a sync.

### Added
- Web app: course list, lecture page with citations beside the slide, visuals, ask box, and upload.
- Typed API responses and a generated TypeScript client.

### Fixed
- PDF bullet-font characters no longer appear in slide text.
- Course names containing a slash now work.

### Added
- Evaluation suite: 5 MIT OCW decks, draft golden sets, a planted-error set, `python -m evals.run`,
  and a manual GitHub workflow with a budget stop.

### Fixed
- Footers and page numbers no longer count as evidence for claims.

### Added
- Slide images rendered at ingest, served at `GET /decks/{id}/slides/{n}/image`.
- Model id and prompt version stored with every summary; token usage tracked per client.
- `scripts/smoke_live.py` for one real-model run (run by Neo, costs money).

## [0.1.0] — 2026-10-30
### Added
- CLI: `python -m app ingest` and `ask`, with an `--offline` mode that needs no API key.
- Startup config validation, JSON-lines logging, and stored traces of every harness attempt.
- Scanned slides are flagged `needs_ocr` instead of being sent to the model.
- CI status badge, `/health` in the README endpoint table, ADR 0002 (FastAPI + SQLite + BM25).

### Changed
- Claude Code merges its own PRs once required checks pass; live API runs stay with Neo.

### Fixed
- Verifier compared numbers as substrings, so "4 seconds" passed on a slide saying "0.42 seconds".
  Numbers now compare by value, sign, and unit; terms match whole words.
- Verifier now handles superscripts, unicode ligatures and dashes, simple LaTeX, and `5 ms` vs `5ms`.
- Facts inside visuals are now verified, and citations of blank slides fail.
- Missing or corrupt files give a clear error instead of a raw library crash.

## [0.0.0] — 2026-10-30
### Added
- Backend scaffold: PDF/PPTX parsing, layered verifier, generate→verify→revise harness,
  BM25 retrieval, SQLite store, Canvas client, FastAPI endpoints.
- 25 offline tests (fake model, mocked Canvas API); 90% coverage.
- CI (ruff + pytest with 85% coverage gate, Python 3.11/3.13), Dependabot, PR template,
  Claude Code permission rules.
- Project docs: `CLAUDE.md`, project plan, architecture, setup/access guide, ADR 0001.
