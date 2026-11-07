# LazyGenius Build Plan

Nov 6, 2026 · @Neo Landav

## Reality check

Your core pipeline is realistic and cheap to run. Three ideas are not, and charging classmates is the wrong move. The rule that keeps cost sane: **generate once per lecture, share with many readers**.

| Goal | Verdict | Why, or what to do instead |
| --- | --- | --- |
| Pick a course, pull the prof's files | Realistic, already built | `app/lms/canvas.py` lists courses and files and downloads them. It has never run against real MSU Canvas. |
| Give the prof's topic list, find where each topic is covered | Realistic and cheap | Mostly plain code (search over slides). At most one small-model call to turn the prof's study guide into a clean topic list. |
| Coverage report: how well the slides match the prof's study guide | Realistic, and your best feature | Per topic: which slides cover it, how strongly, and which topics have no slide support. |
| Study guide with visuals, every claim checked | Realistic | Visuals as structured data (tables, Mermaid diagrams, simple charts) the verifier can check. Not AI-generated images. |
| Handle courses that post weekly vs all at once | Realistic | Use Canvas Modules and file dates to tag each file with a week. See The product. |
| An agent that freely browses Canvas to find files | Too costly, too risky | Burns tokens on every sync, gives random results, and your token can read your grades. Plain code finds files; the model never touches Canvas. |
| A fresh guide per student, on demand | Too costly | Cost grows with every user. Cache guides per lecture and topic set so 30 classmates cost the same as 1. |
| Reading scanned or handwritten notes with vision models | Defer | Image input costs much more than text. List text-less slides as "needs OCR" for now. |
| Different models for different difficulty | Yes, but 3 tiers max | See Model routing. Most steps need no model at all. |

### Who pays for the API

**Don't charge classmates.** Payments mean Stripe, refunds, support, and selling a product built on your professors' material. It would also kill the adoption you need as proof.

**Do this instead:**

1. You pay to generate guides for your own courses. That's a normal personal cost.
2. Classmates in the same section read the cached guides and coverage reports. Reading costs you nothing.
3. Questions typed into the app are rate-limited per person (`AskLimiter` already exists) and capped per day.
4. Set a hard monthly spend limit in the Anthropic Console. Start at $10 a month.
5. Later, if demand outgrows your budget: let power users paste their own API key.

**Cost estimate, to confirm on your first live run:** a guide from a few decks with a mid-tier model should cost cents, not dollars. `scripts/smoke_live.py` logs token usage, so measure before trusting any estimate.

### Sharing guides with your class

Sharing your own study guide with classmates is normally fine. Two lines to stay behind:

- **Keep it class-gated, never public.** Guides are built from the professor's slides, which are their material. Don't host slide PDFs or slide images on a public page.
- **Check each course's policy** on sharing materials and on AI use, usually in the syllabus. Better: show the professor. A professor who endorses it is a huge resume line.

This is practical guidance, not legal advice.

## The product

LazyGenius turns "here's what the prof said is on the exam" into a checked study guide built only from that course's slides, plus a report of what the slides do and don't cover.

### The pipeline

&#91;embedded content: LazyGenius pipeline · 8 steps, 1 retry loop\]

Only the highlighted steps call a model. A claim that fails verification goes back to the writer at most twice, then is dropped.

1. **Sync.** Plain code pulls every lecture file from Canvas (Files and Modules), with its module name, post date and week. Already-seen files are skipped.
2. **Scope.** You tell it what to study, three ways:
   - paste the prof's study guide or topic list (best),
   - pick modules or weeks ("Exam 2 = weeks 5 to 9"),
   - pick files by hand.
3. **Extract topics.** If you pasted a study guide, a small model turns it into a clean topic list. You can edit the list before continuing.
4. **Map topics to slides.** Search finds the slides for each topic and scores how strong the match is. Plain code, no model.
5. **Coverage report.** Per topic: covered, weakly covered, or not found in the slides. Also lists slide topics the prof did *not* mention, which are likely lower priority.
6. **Write the guide.** One section per topic, written only from that topic's mapped slides, with visuals and practice questions.
7. **Verify.** The existing checker tests each claim against its cited slides. Claims that fail after 2 retries are dropped.
8. **Publish.** The guide is cached and shared with classmates in that course.

### Courses that post differently

| Course style | Problem | How LazyGenius handles it |
| --- | --- | --- |
| Posts everything on day one | Can't tell which files matter for this exam | Topic-driven scope: paste the prof's study guide, map topics to slides, ignore the rest. If the syllabus has a week-by-week schedule, tag each file with its week from the schedule. |
| Posts notes weekly | Guide goes stale as new lectures arrive | Sync on a schedule. Tag each file with the date it first appeared. When a new file lands, re-map only the topics it matches and rebuild only those sections. |
| Hides the Files tab, posts in Modules | Files API returns nothing | Read the Modules endpoint, which links each item to its file or page. Module names often say "Week 6", so use them as week tags. |
| Posts pages, not PDFs | No slide deck to parse | Treat each Canvas Page as a one-slide "deck" of text. Defer until a real course needs it. |
| No study guide from the prof | Nothing to scope against | Scope by weeks or modules, then let a small model propose a topic list from those slides for you to edit. |

**Re-run rule:** a guide is rebuilt only when its inputs change: a new file version, an edited topic list, or a new prompt version. Never on a timer by itself.

### How files get in

You never upload files one by one, and you never tell it a file is new. A scheduled sync finds new files on its own.

1. **Scheduled sync** (for example, every morning) asks Canvas for each course's files and modules.
2. **Only new or changed files** are downloaded. The store already compares versions with `is_current`.
3. **Parsing and indexing are plain code**, so syncing costs nothing in API fees.
4. **The database is the memory.** Slides, week tags and the search index are stored once and reused for every guide and question.
5. **The model runs only on request:** when you ask for a guide, or, optionally, to rebuild just the sections a new lecture affects.
6. **Manual upload stays as a fallback** for files that never touch Canvas, like a PDF a professor emails.

### Proving sync works for each course

Canvas courses are organized differently, so prove sync per course instead of assuming it:

- **Sync report after every run.** Per course: files found and where (Files, Modules, home page), files parsed and slides with text, files skipped and why, and a warning when a course returns zero files.
- **One-time manual check.** On a course's first sync, compare the report against what Canvas shows ("Canvas: 14 lecture files, LazyGenius: 14"). Record it in `docs/COURSE_CHECKS.md`.
- **Recorded-response tests.** Save real Canvas responses from each course, with names and IDs scrubbed, as test fixtures. Every new course layout becomes a permanent test.

### Who can do what

Classmates never connect their own Canvas in the first version. Each access level costs you more than the one before it.

| Level | They can | Cost to you | When |
| --- | --- | --- | --- |
| View | Read your guides and coverage reports for courses you share | Nothing | Phase 8 |
| View + ask | Also ask questions against the shared course index | Small: rate-limited, Haiku | Phase 8 |
| Request guides | Paste their own topic list for a shared course; requests queued and capped per day | Per request, capped | After Phase 8 numbers |
| Full use | Connect their own Canvas for any course | High unless they bring their own API key | Only with MSU-approved scoped OAuth |

Start with **view + ask**. It gets you real usage numbers at near-zero cost, and you never hold anyone else's Canvas token.

## Model routing and cost controls

Route by difficulty, but most of the pipeline should use no model at all. That, not clever routing, is what keeps cost low.

| Step | Model | Why |
| --- | --- | --- |
| Sync, parse slides, search, coverage scoring, citation and fact checks | None (plain code) | Deterministic, free, testable. Your interview story lives here. |
| Turn the prof's study guide into a topic list | Haiku (`claude-haiku-5-5`) | Short structured extraction. |
| Judge: does this slide support this paraphrase? | Haiku | Yes/no on a small input, run many times. |
| Answer questions in the web app | Haiku first | Cheap for the most frequent call. Escalate only if your evals show it fails. |
| Write study guide sections and visuals | Sonnet (`claude-sonnet-5-5`) | The one step where writing quality matters. |
| Anything else | Opus (`claude-opus-5-5`) only if an eval proves Sonnet fails | Default: never. |

Put each choice in `.env` (`MODEL_EXTRACT`, `MODEL_JUDGE`, `MODEL_WRITER`, `MODEL_ASK`) and read them in `app/config.py`. Then swapping a model is a config change you can measure.

### Cost controls, in order of impact

1. **Send only mapped slides.** Each guide section gets its topic's slides, never the whole course.
2. **Cache results.** Store guides keyed by file version + topic list + prompt version + model. The `summaries` table already tracks model and prompt version.
3. **Prompt caching.** When several topics share the same slides, cache the slide text block so repeat reads are discounted.
4. **Batch API for non-urgent runs.** Overnight rebuilds after a weekly sync go through the Message Batches API, which is discounted versus live calls.
5. **Hard caps.** `max_tokens` on every call, at most 2 revisions per claim (already the default), a daily dollar cap in the app, and a monthly limit in the Anthropic Console.
6. **Text first.** Never send slide images unless a slide has no extractable text.
7. **Measure.** Save input and output tokens per call (the API returns them) into the `traces` table. Add `python -m app cost --week` to print spend by step.

## Setup

You need almost no new tooling. The product needs zero MCP servers, because plain code talks to Canvas and the Anthropic API directly.

### Before your first Claude Code session

- [ ] Point your local clone at the renamed repo: `git remote set-url origin https://github.com/Neo-Land/LazyGenius.git`
- [ ] Python 3.11+, then `python -m venv .venv` and `pip install -r requirements.txt -r requirements-dev.txt`
- [ ] Node 20+ for `web/` (`cd web && npm install`)
- [ ] GitHub CLI signed in: `gh auth login` (PRs and CI checks from the terminal)
- [ ] LibreOffice, only if your profs post PowerPoints (renders `.pptx` slides)
- [ ] Anthropic API key from the Console, **with a monthly spend limit set first**, saved in `.env`
- [ ] Check that MSU Canvas lets you make a token: Account, then Settings, then **New Access Token**. If the button is missing, you'll need OAuth later (Phase 8).
- [ ] `pytest -q` passes (113 tests today)

### Tools, and whether you need them

| Tool | Needed? | Use |
| --- | --- | --- |
| `gh` CLI | Yes | PRs, CI status, issues from the terminal |
| Anthropic API (`anthropic` Python SDK) | Yes | All model calls, token usage, Batches API |
| Your own Canvas client (`app/lms/canvas.py`) | Yes | Extend it; don't replace it |
| canvas-cli (jjuanrivvera) | Optional, local only | Explore how your profs organize files. Never a dependency of the app. |
| Playwright | Already in `web/` | Browser tests; Claude Code runs them from the terminal |
| PostHog | Phase 8 | Usage analytics: weekly actives, guides opened, questions asked |
| Supabase (Auth + Postgres) | Phase 8 | Sign-in limited to `@montclair.edu` emails; replaces SQLite once several people use it. You've used it in Gamify.Life. |
| Hosting: Vercel (web) + Fly.io or Render (API) | Phase 8 | Free or near-free tiers are enough for a class |
| MCP servers | Not needed | Optional dev aid only, such as a docs-lookup MCP. Never in the product. |

### Rename cleanup (Phase 0)

Search the repo for `lecture-harness` and `Lecture Harness` and update: README title and CI badge URL, `pyproject.toml` name, Docker image names in `docker-compose.yml` and the release workflow, and `CLAUDE.md`. GitHub redirects the old URL, but links in your resume and portfolio should use the new one.

## Ground rules for working with Claude Code

The old plan let Claude Code write everything and merge its own PRs. This time the git history has to show you thinking, because interviewers will read it.

**Main focus:** a working product with clear, readable code. Polish, extra features and long docs come after.

**You write, Claude reviews:** the core logic you'll be grilled on.

- verifier fact matching
- search and stemming
- topic-to-slide scoring
- coverage report logic
- cost and caching keys

**Claude writes, you review line by line:** plumbing.

- API routes, UI components, config
- Docker and CI
- test scaffolding and fixtures

**Always:**

1. Start each task in plan mode. Ask Claude to explain the approach and tradeoffs before any code.
2. **Commit steadily, never in big dumps.** Commit each small piece as soon as it is concise, works, and its tests pass: one concern per commit, aiming under \~200 changed lines. Claude may commit after you approve the diff; you edit the message so it says what you actually did.
3. **Document as you go, briefly.** Update the README, `docs/`, or the CHANGELOG in the same commit as the code they describe: a few lines, not essays. No separate doc-rewrite passes; they burn usage for little value.
4. **You** merge every PR, after reading the diff.
5. No feature is done without a test and, where it applies, an eval number.
6. End each phase with a short decision record you write yourself in `docs/decisions/`.
7. If you can't explain a line, you don't merge it.

Paste this into `CLAUDE.md`, replacing the old workflow rules, so every Claude Code session follows it:

```markdown
## How we work (Neo's rules)
- Main focus: a working product with clear, readable code. No extra features or polish until asked.
- Neo writes core logic: verifier, retrieval, topic mapping, coverage, caching. For these, review and suggest; do not write the implementation unless Neo asks for a specific piece.
- You may write plumbing (routes, UI, config, CI, fixtures).
- Start every task by explaining the plan and the tradeoffs. Wait for approval before editing.
- Commit steadily: one small concern per commit (aim under ~200 changed lines), only when the code is concise, correct and tests pass. Show Neo the diff and a draft message; commit only after he approves. Never merge PRs.
- Document as you go: update README, docs/ or CHANGELOG in the same commit, a few lines at most. No standalone doc rewrites.
- Every change ships with tests. Report eval numbers when retrieval, verification or mapping changes.
- Never let the model read Canvas or decide which files to fetch; plain code does that.
- Canvas: only the allowlisted read-only endpoints in docs/BUILD_PLAN.md (Data boundaries). Never touch grades, submissions, enrollments or users. Never read .env.
- Never send slide images to a model unless the slide has no text.
```

## Data boundaries and guardrails

LazyGenius may touch only course lists, files, modules and course home pages. Everything else, grades above all, is blocked in code, checked in tests, and kept out of storage. Build this before Phase 4's first real sync.

**Why code has to enforce it:** a Canvas personal access token isn't scoped. It can read everything you can, grades included. Only OAuth tokens from a scoped developer key are limited by Canvas itself, and only school admins can create those keys ([Canvas docs](https://canvas.wisc.edu/doc/api/file.developer_keys.html)). Until then, your code is the only fence.

### Allowed vs blocked

| Allowed (GET only) | Endpoint |
| --- | --- |
| Your active course list | `/api/v1/courses` |
| A course's files | `/api/v1/courses/:id/files` |
| A single file and its download | `/api/v1/files/:id`, then the file host it redirects to |
| Modules and their items | `/api/v1/courses/:id/modules` |
| Course home page | `/api/v1/courses/:id/front_page` |
| Optional, off by default: syllabus text | `/api/v1/courses/:id?include[]=syllabus_body` |

**Blocked, always:** grades, submissions, assignments, enrollments, users and profiles, conversations and inbox, discussions, quizzes, calendar, analytics, and any `include[]` that adds scores. Also blocked: every POST, PUT and DELETE. LazyGenius never writes to Canvas.

### Six layers of guardrails

1. **One gate for every request.** All Canvas traffic goes through one function that checks method + path against an allowlist and raises `BlockedEndpoint` otherwise. No other module imports `httpx` for Canvas.

   ```python
   ALLOWED = [
       r"^/api/v1/courses$",
       r"^/api/v1/courses/\d+/files$",
       r"^/api/v1/files/\d+$",
       r"^/api/v1/courses/\d+/modules$",
       r"^/api/v1/courses/\d+/front_page$",
   ]
   BLOCKED_PARAMS = {"total_scores", "current_grading_period_scores", "grades"}
   ```
2. **Keep only allowlisted fields.** Every response is parsed into a strict Pydantic model listing only the fields you need (id, name, file name, URL, dates, module name). Anything else, including any grade field, is dropped before it touches memory or the database.
3. **The token is never stored by the app.** It lives in `.env` on your machine (later, the OS keychain), never in SQLite, Postgres, logs, traces or error messages. The HTTP client strips the `Authorization` header from every log line. LazyGenius never stores classmates' tokens; their access is the view levels only.
4. **Claude Code can't see the token or widen access.**
   - `.claude/settings.json` denies reading secrets:

     ```json
     {"permissions": {"deny": ["Read(./.env)", "Read(./.env.*)", "Bash(cat .env*)"]}}
     ```
   - A skill at `.claude/skills/canvas-boundary/SKILL.md` that Claude Code loads whenever it touches `app/lms/`. It states the allowlist, the blocked list, and the rule "never add an endpoint without Neo's approval and a test".
   - A `PreToolUse` hook that rejects any edit adding blocked words such as `/grades`, `/submissions`, `/enrollments` or `total_scores` under `app/`.
5. **Tests that fail loudly.**
   - Every blocked endpoint raises `BlockedEndpoint`.
   - A fake Canvas response full of grade fields produces a database with zero grade values.
   - The token never appears in logs, traces or the database after a full sync.
   - A CI check runs `gitleaks` so a token can never be committed.
6. **Scoped OAuth later (Phase 8).** When you ask MSU IT for a developer key, request only the five allowed scopes in `url:GET|<path>` form. Then Canvas itself refuses grades, even if your code had a bug.

**Done when:** all six layers exist, their tests pass in CI, and the README has a short "What LazyGenius can and can't read" section. That section is also a strong interview story.

## Build plan

Nine phases over about 12 weeks. Aim to finish Phases 0 to 5 before your finals so you study with it yourself. Each phase ends with tests green, a tag, and a CHANGELOG entry.

### Phase 0: Rename and reset (1 evening)

- [ ] Rename cleanup from Setup
- [ ] Replace the workflow rules in `CLAUDE.md` with Ground rules
- [ ] Mark `docs/PROJECT_PLAN.md` as superseded by this plan
- [ ] README: say plainly that the eval sets are unreviewed drafts until Phase 7

Done when: CI is green on the renamed repo.

### Phase 1: Make the verifier honest (week 1, you write)

- [ ] Add failing tests for the 5 cases found in review: wrong exponent O(n^2), "3 recursive calls" passing on "Lecture 3", swapped algorithm names, negation, plus one true control
- [ ] Match numbers in context: compare whole expressions such as `O(n^2)` as one unit, and require a number's nearby words to match the slide
- [ ] Route claims with no checkable facts (no numbers, quotes or code) to the judge, and flag negations ("not", "never") for it

The 5 cases, all passing today with no judge (they should be caught, except the last):

```text
Slides:
  1: "Merge sort: worst case O(n log n). Uses 2 recursive calls. Lecture 3"
  2: "Quicksort worst case O(n^2) when pivot is bad"
  3: "Binary search requires a sorted list"

Should be CAUGHT:
  "Merge sort's worst case is O(n^2)."            cites [1]  (2 matches "2 recursive calls")
  "Merge sort makes 3 recursive calls."           cites [1]  (3 matches "Lecture 3")
  "Quicksort's worst case is O(n log n)."         cites [1]  (no numbers, swapped name)
  "Binary search does not require a sorted list." cites [3]  (negation)
Should PASS:
  "Merge sort's worst case is O(n log n)."        cites [1]

Also for Phase 2: searching "sorting algorithms" and "recursion" returns no slides (no stemming).
```

Done when: all 5 new tests pass, the old 113 still pass, and an ADR explains the matching rule.

### Phase 2: Fix search (week 1 to 2, you write)

- [ ] Write 30 real questions from your own courses, each labeled with the slide that answers it
- [ ] Measure recall@5 before changes
- [ ] Add stemming (for example, the `snowballstemmer` package) so "sorting" finds "sort"
- [ ] Optional: add embeddings and fuse with BM25; keep it only if recall improves

Done when: recall@5 before and after is recorded in `docs/EVALS.md`.

### Phase 3: First live run and cost logging (week 2)

- [ ] Model names in `.env` per Model routing
- [ ] Save input and output tokens per call into `traces`; add `python -m app cost`
- [ ] Run on 3 to 5 decks from your own courses; paste the results into `docs/RESULTS.md`, failures included

Done when: you know the real cost of one guide.

### Phase 4: Real Canvas (week 3)

**Gate:** all six layers of Data boundaries and guardrails pass in CI before the first real sync.

- [ ] Run `sync` on all your current courses and write down where each prof actually puts slides
- [ ] Add the Modules endpoint (`/api/v1/courses/:id/modules?include[]=items`)
- [ ] Store per file: module name, week tag, first-seen date
- [ ] Detect a syllabus file and keep it out of the slide index

* [ ] Sync report after every run: files found per source, parsed, skipped with reason, zero-file warning
* [ ] First-sync manual check per course, recorded in `docs/COURSE_CHECKS.md`
* [ ] Scrubbed real Canvas responses saved as test fixtures, one set per course layout
* [ ] Scheduled daily sync on your machine (cron), plus manual upload kept as a fallback

Done when: every one of your courses syncs and every lecture file has a week tag or is marked "unknown".

### Phase 5: Topic scope and coverage report (weeks 3 to 5, you write the scoring)

- [ ] Input: paste a study guide, pick weeks or modules, or pick files
- [ ] Topic extraction with Haiku into an editable list (stored per course and exam)
- [ ] Map each topic to slides with a score; thresholds for covered, weak, and not found
- [ ] Coverage report page, plus "in the slides but not in the prof's list"

Done when: on a real study guide from one of your classes, you hand-check every topic's mapping and record the accuracy.

### Phase 6: Study guide generation (weeks 5 to 7)

- [ ] One section per topic, written only from mapped slides, verified before display
- [ ] Visuals as checked data: comparison tables, Mermaid flows, simple charts
- [ ] 3 practice questions per topic, each answer citing its slide
- [ ] A "not found in slides" section listing uncovered topics
- [ ] Export to PDF and Markdown
- [ ] Weekly courses: when a new file arrives, rebuild only the sections it affects

* [ ] Optional auto-rebuild: after a scheduled sync finds a new lecture, rebuild only the guide sections it maps to, through the Batch API

Done when: you use it to study for a real exam.

### Phase 7: Honest evaluation (weeks 6 to 8, alongside Phase 6)

- [ ] Hand-label at least 100 claims from real guides as true or false
- [ ] Per checker layer: errors caught, errors missed, true claims wrongly dropped
- [ ] Topic-mapping accuracy from Phase 5 and recall@5 from Phase 2
- [ ] Replace the README's draft numbers with these

Done when: every number in the README comes from your labels.

### Phase 8: Class beta (weeks 8 to 12)

- [ ] Deploy: web on Vercel, API on Fly.io or Render, guides cached
- [ ] Supabase sign-in limited to `@montclair.edu`; each guide visible only to its course's members
- [ ] PostHog events: guide opened, topic expanded, question asked, return visit
- [ ] Feedback button on every guide section ("wrong", "missing", "helpful")
- [ ] Invite 5 classmates, then 30; fix what they hit each week
- [ ] If MSU blocks personal tokens: request an OAuth developer key from MSU IT

* [ ] Access levels "view" and "view + ask" only, per Who can do what; no classmate Canvas tokens

Done when: you can state weekly active users and 4-week retention.

### Phase 9: Later, only after Phase 8 numbers

- Bring-your-own API key for power users
- Scheduled weekly sync with a "new lecture, guide updated" email
- OCR for scanned slides

* "Request guides" level: classmates submit topic lists for shared courses, queued and capped per day
* "Full use" level, only with MSU-approved scoped OAuth and bring-your-own key

## Starter prompts for Claude Code

Open Claude Code in the repo root and paste one of these per phase. Each one keeps you as the author of the core logic.

**Phase 0**

```text
Read CLAUDE.md and docs/. The repo was renamed from lecture-harness to LazyGenius. List every file that still uses the old name and propose the exact edits. Don't edit yet. Then replace the workflow section of CLAUDE.md with the rules I'll paste next.
```

**Phase 1**

```text
Plan mode. Write failing tests in tests/test_verifier.py for these 5 cases: [paste the 5 cases]. Don't change app/verifier.py. Then explain why each one passes today and give me 2 or 3 options for context-aware number matching, with tradeoffs. I'll write the implementation; you'll review it.
```

**Phase 2**

```text
Help me build a retrieval eval: a TOML file of questions, each with the slide that answers it, and a recall@5 script in evals/. Write the script; I'll write the questions. Run it and report the baseline before I change app/retrieval.py.
```

**Phase 3**

```text
Add per-step model config (MODEL_EXTRACT, MODEL_JUDGE, MODEL_WRITER, MODEL_ASK) in app/config.py, and save input/output token counts from each API response into the traces table. Add a `python -m app cost` command. Keep each change under 200 lines and show me the diff before committing.
```

**Phase 4**

```text
Extend app/lms/canvas.py to read course modules with items, and store module name, week tag and first-seen date per file. Write tests against recorded responses first. Don't add any model calls. I'll run it against real Canvas myself.
```

**Phase 5**

```text
Plan mode. Design the data model and API for: a topic list per course and exam, topic-to-slide mappings with scores, and a coverage report. Propose the schema and endpoints only. I'll write the scoring function; you build the routes and the report page around it.
```

**Phase 6**

```text
Design a study-guide generation step: one section per topic, built only from that topic's mapped slides, verified by the existing checker, with visuals as checked data and practice questions that cite slides. Show me the prompt and the output schema first, and how caching keys work, before any code.
```

**Phase 7**

```text
Build a labeling tool for real guide output: a CLI or small page that shows one claim beside its cited slides and lets me mark it true or false. Save labels to evals/labels/. Then write a report script: per checker layer, errors caught, errors missed, true claims wrongly dropped. I do all the labeling; don't pre-fill any labels.
```

**Phase 8**

```text
Plan the class beta deploy: Vercel for web/, Fly.io or Render for the API, Supabase auth limited to @montclair.edu, per-course access to guides, and PostHog events. Give me a step-by-step checklist and what each step costs, then do one step at a time with my approval.
```

**Phase 9** (only after Phase 8 has real usage numbers)

```text
Plan mode. Using the PostHog data and feedback from the beta, propose which Phase 9 item to build first: the request-guides queue, bring-your-own API key, or weekly update emails. For the one I pick, design it with the Data boundaries rules unchanged: no stored classmate Canvas tokens. Show the plan and cost per user before any code.
```
