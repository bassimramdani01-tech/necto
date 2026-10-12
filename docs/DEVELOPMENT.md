# necto — Development Environment Setup (Windows)

**Status on this machine: ✅ set up.** Everything except Docker Desktop is installed and verified.

---

## 1. What is already installed

Tools were installed **portably into your user profile** (no admin rights) because winget installers
that need elevation could not complete unattended. They are all on your **user PATH**.

| Tool | Version | Location | PATH |
|---|---|---|---|
| git | 2.55.0.windows.5 | `C:\Program Files\Git\cmd` | ✅ machine PATH |
| uv | 0.13.0 | `%LOCALAPPDATA%\Programs\necto-tools\uv` | ✅ user PATH |
| Python | 3.12.15 (uv-managed) | `%APPDATA%\uv\python\cpython-3.12.15-windows-x86_64-none` | via `uv` |
| Node.js | v24.20.0 | `%LOCALAPPDATA%\Programs\necto-tools\node` | ✅ user PATH |
| pnpm | 12.11.2 | same as Node | ✅ |
| GitHub CLI | 2.102.0 | `%LOCALAPPDATA%\Programs\necto-tools\gh` | ✅ |
| pre-commit | 4.6.2 | `%USERPROFILE%\.local\bin` | ✅ |
| PostgreSQL | 16.4 (portable stand-in) | `%LOCALAPPDATA%\Programs\necto-tools\pgsql` | not needed on PATH |
| VS Code | 1.141.0 + 9 extensions | — | ✅ |

> ⚠️ **Open a NEW terminal** to pick up PATH changes. Terminals opened earlier will not see `uv`, `node`, `pnpm`, or `gh`.

### VS Code extensions installed
Python · Pylance · Ruff · ESLint · Prettier · Tailwind CSS IntelliSense · Docker · Even Better TOML · Playwright.

---

## 2. Database

Connection string — **identical for both options**:

```
postgresql://necto:necto@127.0.0.1:5432/necto
```

### Option A — portable PostgreSQL 16.4 (already running ✅)

A local cluster is initialised at `%LOCALAPPDATA%\Programs\necto-tools\pgdata` with the `necto` database and `necto` user.
It is currently **running on 127.0.0.1:5432** and JSONB is verified working.

```powershell
# start
& "$env:LOCALAPPDATA\Programs\necto-tools\pgsql\bin\pg_ctl.exe" -D "$env:LOCALAPPDATA\Programs\necto-tools\pgdata" -l "$env:LOCALAPPDATA\Programs\necto-tools\pg.log" -o "-p 5432" start

# stop
& "$env:LOCALAPPDATA\Programs\necto-tools\pgsql\bin\pg_ctl.exe" -D "$env:LOCALAPPDATA\Programs\necto-tools\pgdata" stop

# status
& "$env:LOCALAPPDATA\Programs\necto-tools\pgsql\bin\pg_isready.exe" -h 127.0.0.1 -p 5432
```

### Option B — Docker Desktop (**MANUAL — cannot be automated**)

Two hard blockers prevent automating this:

1. **Virtualization is disabled in the BIOS** (`HypervisorPresent: False`) — Docker's WSL2 backend cannot run without it.
2. **Installation requires administrator elevation** — a UAC prompt must be approved by a human.

#### Exact steps

**Step B1 — Enable virtualization in BIOS/UEFI.**
Check first: `Task Manager → Performance → CPU → "Virtualization"`.
If it says **Enabled**, skip to B2. If **Disabled**:
1. Reboot the machine.
2. Press `F2`, `Del`, or `Esc` at the manufacturer splash screen (varies by vendor — Lenovo often `F1`, HP `Esc`/`F10`).
3. Navigate to `Advanced` → `CPU Configuration` (or `Security` / `Virtualization`).
4. Set **AMD SVM Mode** (AMD CPUs) or **Intel VT-x / Virtualization Technology** (Intel CPUs) to **Enabled**.
5. Save & exit (usually `F10`).
6. Confirm in Task Manager that Virtualization now says **Enabled**.

**Step B2 — Install WSL2.**
Open PowerShell **as Administrator** (right-click Start → *Terminal (Admin)*) and run:
```powershell
wsl --install
```
Reboot when prompted.

**Step B3 — Install Docker Desktop.**
In an **Administrator** PowerShell:
```powershell
winget install --id Docker.DockerDesktop -e --accept-source-agreements --accept-package-agreements
```
Approve the UAC prompt.

**Step B4 — First launch.**
Start Docker Desktop → accept the licence → wait for the whale icon to stop animating (engine running).
If prompted, confirm `Settings → General → "Use the WSL 2 based engine"`.

**Step B5 — Verify.**
```powershell
docker --version
docker run --rm hello-world
```

**Step B6 — Switch necto over.**
Once Docker is running, tell me. I will start Postgres from `docker-compose.yml` (same credentials, same port)
and we stop the portable stand-in. **No code changes are needed — the connection string stays identical.**

---

## 3. Known issue: stuck installer processes

An earlier unattended `winget` install of Node.js is stuck waiting on a UAC prompt that was never answered.
Its `winget.exe` / `msiexec.exe` processes may still linger and cannot be killed without elevation.

**What to do:** if you see a **Windows User Account Control dialog** on screen asking about Node.js or
Windows Installer, click **No** — Node.js is already installed portably, so you do not need it.
If no dialog is visible, ignore it; the processes clear on the next reboot and block nothing.

---

## 4. Verification checklist

Open a **new** terminal and run:

```powershell
git --version          # git version 2.55.0.windows.5
uv --version           # uv 0.13.0
node --version         # v24.20.0
pnpm --version         # 12.11.2
gh --version           # gh version 2.102.0
pre-commit --version   # pre-commit 4.6.2
uv python list         # shows cpython-3.12.15
```

Database:
```powershell
& "$env:LOCALAPPDATA\Programs\necto-tools\pgsql\bin\pg_isready.exe" -h 127.0.0.1 -p 5432
# 127.0.0.1:5432 - accepting connections
```

---

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| `uv`/`node`/`pnpm` "not recognized" | Open a **new** terminal (PATH refresh) |
| `git` not found in an old terminal | Open a new terminal; git is on the machine PATH |
| `pnpm` missing | It lives next to Node at `...\necto-tools\node\pnpm.cmd` |
| Postgres won't start | Check the log: `%LOCALAPPDATA%\Programs\necto-tools\pg.log` |
| Port 5432 already in use | Stop the other PostgreSQL, or change the port in both places |
| Docker engine won't start | Confirm virtualization is enabled (B1) and WSL2 is installed (B2) |
