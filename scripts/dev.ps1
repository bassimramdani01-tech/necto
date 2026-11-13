#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Start necto for local development: database, migrations, API and web UI.

.DESCRIPTION
    One command instead of three terminals. The database runs in Docker; the API and the
    Vite dev server run natively so both hot-reload. Ctrl+C stops the API and web servers
    (the database keeps running for the next session).

.PARAMETER ApiPort
    Port for the FastAPI server (default 8000).

.PARAMETER WebPort
    Port for the Vite dev server (default 5173).

.PARAMETER NoSeed
    Do not set NECTO_SEED=1 (which fills an empty database with demo runs).

.PARAMETER NoDb
    Skip starting the database (use an already-running Postgres).

.PARAMETER CheckOnly
    Validate prerequisites and print the plan, then exit.

.EXAMPLE
    ./scripts/dev.ps1 -CheckOnly
    ./scripts/dev.ps1
    ./scripts/dev.ps1 -ApiPort 8001 -NoSeed
#>
[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173,
    [switch]$NoSeed,
    [switch]$NoDb,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $env:LOCALAPPDATA "Programs/necto-tools"
function Resolve-Tool([string]$Name, [string]$Bundled) {
    # Prefer the portable tools this checkout was set up with, fall back to PATH.
    if (Test-Path $Bundled) { return $Bundled }
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    throw "$Name not found -- install it (see docs/DEVELOPMENT.md) or add it to PATH."
}

$uv = Resolve-Tool "uv" (Join-Path $tools "uv/uv.exe")
$pnpm = Resolve-Tool "pnpm" (Join-Path $tools "node/pnpm.cmd")

function Assert-Tool([string]$Name, [string]$Path) {
    Write-Host "  ok  $Name ($Path)"
}

Write-Host "necto dev environment" -ForegroundColor Cyan
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker engine is not running. Start Docker Desktop and retry."
}
Write-Host "  ok  Docker engine"
Assert-Tool "uv" $uv
Assert-Tool "pnpm" $pnpm

if ($CheckOnly) {
    Write-Host ""
    Write-Host "would run:" -ForegroundColor Cyan
    Write-Host "  docker compose up -d db"
    Write-Host "  cd server; uv run --no-sync alembic upgrade head"
    Write-Host "  cd server; uvicorn necto_server.main:app --port $ApiPort --reload"
    Write-Host "  cd web; pnpm dev --port $WebPort   (proxying to 127.0.0.1:$ApiPort)"
    Write-Host "  API http://127.0.0.1:$ApiPort/docs   UI http://localhost:$WebPort"
    exit 0
}

if (-not $NoDb) {
    Write-Host "starting database..." -ForegroundColor Cyan
    Push-Location $root
    try {
        & docker compose up -d db | Out-Null
    }
    finally {
        Pop-Location
    }
    $healthy = $false
    for ($i = 0; $i -lt 30; $i++) {
        $status = (& docker inspect --format "{{.State.Health.Status}}" necto-db 2>$null)
        if ($status -eq "healthy") { $healthy = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $healthy) { throw "database did not become healthy -- check: docker compose logs db" }
    Write-Host "  database healthy"
}

Write-Host "applying migrations..." -ForegroundColor Cyan
Push-Location (Join-Path $root "server")
try {
    & $uv run --no-sync alembic upgrade head | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head failed" }
}
finally {
    Pop-Location
}
Write-Host "  schema up to date"

if (-not $NoSeed) {
    $env:NECTO_SEED = "1"
    Write-Host "  NECTO_SEED=1 (empty databases get demo runs)"
}

$apiJob = Start-Process -FilePath $uv `
    -ArgumentList @("run", "--no-sync", "uvicorn", "necto_server.main:app",
                    "--host", "127.0.0.1", "--port", "$ApiPort", "--reload") `
    -WorkingDirectory (Join-Path $root "server") -NoNewWindow -PassThru

$env:NECTO_API_TARGET = "http://127.0.0.1:$ApiPort"
$webJob = Start-Process -FilePath $pnpm `
    -ArgumentList @("dev", "--port", "$WebPort", "--strictPort") `
    -WorkingDirectory (Join-Path $root "web") -NoNewWindow -PassThru

Write-Host ""
Write-Host "API  http://127.0.0.1:$ApiPort/docs" -ForegroundColor Green
Write-Host "UI   http://localhost:$WebPort" -ForegroundColor Green
Write-Host "Ctrl+C stops both servers (the database keeps running)." -ForegroundColor DarkGray

try {
    Wait-Process -Id $apiJob.Id
}
finally {
    foreach ($process in @($apiJob, $webJob)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}