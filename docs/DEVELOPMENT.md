# necto — Development Environment Setup (Windows)

This guide sets up **your machine to develop necto itself** (contributor setup).
It is *not* the end-user install — end users will run necto via `docker compose up`, documented separately at first release.

Everything below was verified against the winget catalog on this machine on the day it was written.
**Package versions current as of writing:** git 2.55.0.5 · uv 0.12.23 · Node.js LTS 24.20.0 · Docker Desktop 4.94.0 · GitHub CLI 2.102.0.

---

## What you'll install

| Tool | Purpose | Method | Admin needed |
|---|---|---|---|
| git | version control | winget (user scope) | ❌ |
| uv | Python env + package manager | winget (user scope) | ❌ |
| Python 3.12 | server/SDK runtime | **via uv** (no separate installer) | ❌ |
| Node.js LTS | web UI runtime (Phase 3) | winget (user scope) | ❌ |
| pnpm | JS package manager | npm (global) | ❌ |
| Docker Desktop | PostgreSQL for the database | winget (machine-wide) | ✅ UAC prompt |
| GitHub CLI | publishing (optional) | winget (user scope) | ❌ |
| VS Code extensions | editor ergonomics (recommended) | `code --install-extension` | ❌ |

> **Note:** Python is deliberately *not* a separate step — `uv` downloads and manages its own CPython 3.12, which is exactly what the project targets.

---

## Before you start

One-time winget hygiene so installs don't stall on source agreements:

```powershell
winget source update --accept-source-agreements
```

After **every** install below, close and reopen your terminal so PATH picks up the new tool.

---

## Step 1 — git

```powershell
winget install --id Git.Git -e --scope user --accept-source-agreements --accept-package-agreements
git --version
```

Expected: `git version 2.55.x.windows.1` (or newer). User-scope install lands in `%LOCALAPPDATA%\Programs\Git` — no UAC.

## Step 2 — uv

```powershell
winget install --id astral-sh.uv -e --scope user --accept-source-agreements --accept-package-agreements
uv --version
```

Expected: `uv 0.12.23` (or newer).

## Step 3 — Python 3.12 (via uv)

```powershell
uv python install 3.12
uv python list
```

Expected: a `cpython-3.12.*` entry in the list. uv keeps this Python entirely inside your user profile — no admin, no PATH pollution.

## Step 4 — Node.js LTS

```powershell
winget install --id OpenJS.NodeJS.LTS -e --scope user --accept-source-agreements --accept-package-agreements
node --version
```

Expected: `v24.20.0` (or newer). Reopen your terminal after this.

## Step 5 — pnpm

```powershell
npm install -g pnpm
pnpm --version
```

Expected: a `10.x` version. (User-scope Node installs global packages into your profile, so no admin is needed. Node 24 no longer bundles `corepack` reliably, so `npm -g` is the dependable path.)

## Step 6 — Docker Desktop (the long one, ~20–40 min)

Docker Desktop needs virtualization + WSL2, which this machine does **not** have yet. Do these in order:

**6a. Confirm virtualization is off.** Open Task Manager → Performance → CPU → look for *"Virtualization"*. If it says **Enabled**, skip to 6c.

**6b. Enable it in BIOS.** Reboot → press F2/Del at the manufacturer splash → find **SVM Mode** (AMD) or **Intel VT-x / Virtualization Technology** (Intel), usually under *Advanced → CPU Configuration* → set **Enabled** → save & exit.

**6c. Install WSL2.** Open PowerShell **as Administrator** and run:

```powershell
wsl --install
```

Reboot when it asks.

**6d. Install Docker Desktop.** ⚠️ This one is machine-wide and **will prompt for admin/UAC** — that's expected, approve it.

```powershell
winget install --id Docker.DockerDesktop -e --accept-source-agreements --accept-package-agreements
```

**6e. First launch.** Start Docker Desktop → accept the license → wait for the engine (whale icon turns green). If prompted, ensure **Settings → General → "Use the WSL 2 based engine"** is checked.

**6f. Verify.**

```powershell
docker --version
docker run --rm hello-world
```

Expected: the hello-world message ends with *"This message shows that your installation appears to be working correctly."*

## Step 7 — GitHub CLI (optional, for the publish phase)

```powershell
winget install --id GitHub.cli -e --scope user --accept-source-agreements --accept-package-agreements
gh --version
```

## Step 8 — VS Code extensions (recommended)

```powershell
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension charliermarsh.ruff
code --install-extension dbaeumer.vscode-eslint
code --install-extension esbenp.prettier-vscode
code --install-extension bradlc.vscode-tailwindcss
code --install-extension ms-azuretools.vscode-docker
code --install-extension tamasfe.even-better-toml
code --install-extension ms-playwright.playwright
```

## Step 9 — pre-commit (optional, run later inside the repo)

```powershell
uv tool install pre-commit
# then, inside the necto repo:
pre-commit install
```

---

## Verification checklist

Paste this into a **fresh** terminal after everything is installed — every line should print a version, no "not recognized" errors:

```powershell
git --version
uv --version
uv python list
node --version
pnpm --version
docker --version
docker run --rm hello-world
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| winget complains about msstore agreements | `winget source update --accept-source-agreements` |
| "not recognized as the name of a cmdlet" right after install | Close and reopen the terminal (PATH refresh) |
| Docker engine won't start | Check virtualization (6b) and that WSL2 backend is enabled (6e) |
| `pnpm` not found but Node is | You ran pnpm in the pre-install terminal; reopen and re-run `npm install -g pnpm` |
| `uv python list` shows nothing | Re-run `uv python install 3.12` |
