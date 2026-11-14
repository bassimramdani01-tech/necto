# Command prompt for GitHub Copilot -- push necto and go live

Copy everything inside the block below into GitHub Copilot (agent / CLI mode, not inline
completion) with this repository open. It is safe by construction: it verifies, never
force-pushes, never prints credentials, and stops for you at every human-only step
(GitHub login, PyPI login).

---

```text
You are the release engineer for this repository: necto, an open-source visualiser for
multi-agent AI systems (Python 3.12 FastAPI server + zero-dependency Python SDK + React/Vite
web UI, all shipped with Docker; 84 server, 64 SDK and 31 web tests).

Goal: push the local repository to GitHub, make CI green, and publish the first release v0.1.0.

HARD RULES
- Do not change product behaviour or tests. Only fix CI/environment configuration if a workflow
  is wrong, and explain each such fix in the commit message.
- Never force-push, never rewrite history, never print tokens or credentials, never commit .env.
- Stop and ask me for anything that needs my interactive login or my approval.
- Work on main only; do not create release branches.

STEP 0 -- repository sanity (fix nothing here, just report)
  git status --short                     # must be empty (clean tree)
  git branch --show-current              # must be: main
  git log --oneline -5
  git tag                                # must include phase-1-complete, backend-v0.1.0,
                                         # sdk-v0.1.0, web-v0.1.0, v0.1.0-rc1
  git ls-files | findstr /I ".env .tools node_modules .venv dist"   # Windows
  (or: git ls-files | grep -Ei '(\.env$|\.tools/|node_modules|\.venv|dist/)')
  Expected: no output (nothing sensitive or generated is tracked).
  If .env exists locally it must stay untracked; do not add it.

STEP 1 -- preflight: everything must pass before pushing
  cd server
  uv sync --frozen
  uv run --no-sync alembic upgrade head
  uv run --no-sync pytest -q                       # expect: 84 passed
  uv run ruff check .. && uv run ruff format --check ..   # expect: clean
  cd ../sdk
  uv sync --group frameworks
  uv run pytest -q                                 # expect: 64 passed, 1 skipped
  cd ../web
  pnpm install --frozen-lockfile --allow-build=esbuild
  pnpm test                                        # expect: 31 passed
  pnpm build                                       # expect: dist/ built
  cd ..
  uvx ruff check . && uvx ruff format --check .    # expect: clean
  docker build -t necto-app:preflight .            # expect: image builds
  If any step fails, STOP and paste the output to me. Do not weaken a test or delete a check.

STEP 2 -- authenticate and create the GitHub repository
  gh auth status || gh auth login --web --git-protocol https
  gh repo create <OWNER>/necto --public --source=. --remote=origin --push=false \
      --description "Open-source visualiser for multi-agent AI systems: a live, explorable graph of agents, models, tools, handoffs and cost."
  If the repository already exists:
      git remote add origin https://github.com/<OWNER>/necto.git   (or git remote set-url)

STEP 3 -- push main and tags
  git push -u origin main
  git push --tags
  git ls-remote --heads origin                     # confirm main points at HEAD

STEP 4 -- make CI green (5 jobs: server, sdk, web, lint, docker)
  gh run list --limit 5
  gh run watch <run-id> --exit-status
  If a job fails:
      gh run view <run-id> --log-failed
      Fix only .github/workflows/*.yml (version pins, service env, cache paths).
      Commit, push, and wait again.
  Do not edit product code or tests to silence a failure; report to me if you believe the
  workflow cannot pass without a real change.

STEP 5 -- repository settings and docs
  gh repo edit --enable-issues=true --enable-wiki=false
  Enable Private vulnerability reporting if the API allows it:
      gh api -X PUT repos/<OWNER>/necto/private-vulnerability-reporting
  Add the CI badge to README.md next to the existing badges:
      ![CI](https://github.com/<OWNER>/necto/actions/workflows/ci.yml/badge.svg)
  Commit as: docs: add CI badge

STEP 6 -- PyPI trusted publisher (STOP -- human step)
  Ask me to configure it at https://pypi.org/manage/account/publishing/ with:
      PyPI project name: necto-sdk
      Owner: <OWNER>
      Repository: necto
      Workflow: publish-sdk.yml
      Environment: pypi
  Do not attempt to log in to PyPI yourself. Wait for my confirmation.

STEP 7 -- first release
  git tag -a v0.1.0 -m "necto 0.1.0"
  git push origin v0.1.0
  gh release create v0.1.0 --title "necto 0.1.0" --notes-from-tag
  Then: gh run list --workflow publish-sdk.yml --limit 1
  Watch it; confirm https://pypi.org/project/necto-sdk/ shows 0.1.0.

STEP 8 -- final report to me
  Give me:
  - repository URL
  - CI run URL with the status of all five jobs
  - release URL and PyPI URL
  - every deviation from this plan, with its reason
```

---

## If you would rather push it yourself (no Copilot)

```powershell
# 1. verify
cd server; uv sync --frozen; uv run --no-sync pytest -q; cd ..
cd sdk; uv sync --group frameworks; uv run pytest -q; cd ..
cd web; pnpm install --frozen-lockfile --allow-build=esbuild; pnpm test; pnpm build; cd ..
uvx ruff check .; uvx ruff format --check .

# 2. create + push
gh auth login --web --git-protocol https
gh repo create <OWNER>/necto --public --source=. --remote=origin --push=false
git push -u origin main
git push --tags

# 3. release (after CI is green and the PyPI trusted publisher exists)
git tag -a v0.1.0 -m "necto 0.1.0"
git push origin v0.1.0
gh release create v0.1.0 --title "necto 0.1.0" --notes-from-tag
```
