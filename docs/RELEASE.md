# Release checklist

Run everything from the repository root.

## 1. Pre-flight (all green locally)

```bash
cd server && uv run pytest -q && uv run ruff check .. && uv run ruff format --check ..
cd ../sdk && uv run pytest -q
cd ../web && pnpm test && pnpm build
cd ..
docker build -t necto-app:check .        # validates the Dockerfile
pre-commit run --all-files
```

Version bump (single source per package):

- `sdk/pyproject.toml` + `sdk/necto_sdk/_version.py` (`__version__`)
- `server/pyproject.toml` + `server/necto_server/__init__.py`
- `web/package.json`
- add a `CHANGELOG.md` entry

## 2. GitHub (needs your authentication once)

```bash
gh auth login                     # once per machine; choose HTTPS
git remote add origin https://github.com/<OWNER>/necto.git
git push -u origin main --tags
```

Then in the repo settings:

- **Actions → CI** runs on the push; wait for all five jobs (server, sdk, web, lint, docker).
- Add the CI badge to `README.md` once the workflow exists:
  `https://github.com/<OWNER>/necto/actions/workflows/ci.yml/badge.svg`.
- **Settings → Security → Private vulnerability reporting**: enable (SECURITY.md points there).

## 3. PyPI (one-time trusted publisher, no tokens stored)

1. On <https://pypi.org/manage/account/publishing/> add a trusted publisher:
   project `necto-sdk`, owner `<OWNER>`, repository `necto`, workflow `publish-sdk.yml`,
   environment `pypi`.
2. Create the `pypi` environment in the repo (Settings → Environments) — no secrets needed.

## 4. Release

```bash
git tag -a v0.1.0 -m "necto 0.1.0"
git push origin v0.1.0
```

Create the GitHub release from the tag (`gh release create v0.1.0 --notes-from-tag`). Publishing the
release triggers `publish-sdk.yml` → wheel + sdist go to PyPI.

## 5. Post-release smoke test

```bash
pip install necto-sdk
python -c "import necto_sdk; print(necto_sdk.__version__)"
docker compose up -d --build && curl -fsS http://localhost:8000/healthz
```
