# Setup & access — what Claude Code gets, and what it never gets

**Short answer:** download the zip, put it in a local folder, push it to a new GitHub repo
yourself, and run Claude Code inside that folder. Don't connect Claude Code to Canvas, your
school email, or your Drive. It only needs the repo and a GitHub token scoped to that repo.

## What Claude Code gets

| Access | Give it? | How | Why |
|---|---|---|---|
| The project folder | Yes | Run `claude` from inside `LazyGenius/` | It works only in this folder |
| GitHub (this repo only) | Yes | Fine-grained token, one repo (below) | Push branches, open PRs |
| Anthropic API key | No (default) | Lives in `.env`, which Claude Code is denied | Tests run offline with a fake model. You run live tests yourself |
| Canvas token | Never | Lives in `.env` only | It can read all your courses and grades |
| Real lecture files (`data/`) | Never | Denied in `.claude/settings.json`, gitignored | Professors' copyrighted material |
| Hosting (Vercel/Render) | Never | You connect them via their GitHub integrations | Deploys happen from merged `main`, not from Claude Code |
| `--dangerously-skip-permissions` | Never | — | Keeps every risky command behind your approval |

## One-time setup (≈20 minutes)

### 1. Local repo
```bash
unzip LazyGenius.zip && cd LazyGenius
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
pytest                                                   # should be all green
git init -b main && git add . && git commit -m "chore: initial scaffold"
```

### 2. GitHub repo (you do this, not Claude Code)
1. Create an empty repo `LazyGenius` (public is fine; no real slides are ever committed).
2. `git remote add origin git@github.com:<you>/LazyGenius.git && git push -u origin main`
3. **Branch protection** on `main` (Settings → Branches → Add rule):
   - Require a pull request before merging
   - Require status checks to pass: `backend (3.11)`, `backend (3.13)`, `frontend`, and `images`
   - Block force pushes and deletions
   - Include administrators, or a failing check won't stop an admin's merge
   - This means Claude Code cannot push to `main`. It merges its own PRs only after checks pass.

### 3. A GitHub token scoped to this repo only
GitHub → Settings → Developer settings → Fine-grained tokens → Generate:
- Repository access: **Only select repositories → LazyGenius**
- Permissions: Contents **Read & write**, Pull requests **Read & write**,
  Workflows **Read & write** (needed to edit `.github/workflows`), Actions **Read**, Metadata **Read**
- Expiration: 30–60 days

Then authenticate the `gh` CLI with it: `gh auth login --with-token < token.txt`, and delete `token.txt`.
(Using your normal `gh auth login` works too, but gives access to every repo you own.)

### 4. API key (for your own live runs)
- In the Anthropic Console, create a **separate key** for this project with a **monthly spend limit**.
- Put it in `.env` (copy from `.env.example`). Claude Code is denied from reading `.env`.
- Optional (Phase 3): add it as the GitHub Actions secret `ANTHROPIC_API_KEY` for the
  manually-triggered live eval workflow. Claude Code never sees secret values.

### 5. Verify the guardrails
Start `claude` in the repo and ask: *"show me the contents of .env"*. It should be refused.
If it prints the file, the deny rule isn't matching your Claude Code version; check
the [settings docs](https://docs.claude.com/en/docs/claude-code/settings) and fix `.claude/settings.json`.

Note: a `Read` deny doesn't block shell commands like `cat .env`. That's why Bash commands stay
on approval mode: **read every command before approving it**, and decline anything touching
`.env`, `data/`, or `git push` to `main`.

## Each session
```bash
cd LazyGenius && source .venv/bin/activate && git checkout main && git pull
claude
```
Kickoff prompt: *"Read CLAUDE.md and docs/PROJECT_PLAN.md. Tell me the current phase and the
next unchecked task, propose a plan, then start it on a new branch."*
