param(
    [string]$PostgresBin = "C:\Program Files\PostgreSQL\18\bin",
    [string]$DataDir = "C:\tmp\tsebp2025-postgres-18-data",
    [string]$Mode = "fast"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$pgCtl = Join-Path $PostgresBin "pg_ctl.exe"
if (-not (Test-Path -LiteralPath $pgCtl)) {
    throw "pg_ctl.exe not found at '$pgCtl'. Pass -PostgresBin or install PostgreSQL."
}

if (-not (Test-Path -LiteralPath (Join-Path $DataDir "PG_VERSION"))) {
    throw "Postgres data directory is not initialized: $DataDir"
}

Write-Step "Stopping local PostgreSQL cluster"
Write-InfoLog "Data dir: $DataDir"
Write-InfoLog "Mode: $Mode"

& $pgCtl -D $DataDir -m $Mode stop
if ($LASTEXITCODE -ne 0) {
    throw "pg_ctl stop failed with exit code $LASTEXITCODE."
}

Write-SuccessLog "PostgreSQL stopped."

