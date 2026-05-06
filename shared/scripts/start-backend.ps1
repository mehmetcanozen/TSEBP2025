param(
    [string]$PostgresBin = "C:\Program Files\PostgreSQL\18\bin",
    [string]$DataDir = "C:\tmp\tsebp2025-postgres-18-data",
    [string]$LogFile = "C:\tmp\tsebp2025-postgres-18.log",
    [int]$PostgresPort = 5432,
    [int]$BackendPort = 4000,
    [string]$DatabaseUrl = "postgresql://postgres:postgres@localhost:5432/tsebp2025?schema=public",
    [string]$DesktopBackendUrl = "http://localhost:4000/api/v1",
    [string]$MobileBackendUrl = "http://10.253.52.35:4000/api/v1",
    [switch]$SkipPostgres,
    [switch]$SkipPrismaGenerate,
    [switch]$SkipMigrations,
    [switch]$SkipClientEnv,
    [switch]$ForceRestart,
    [switch]$ForceKillStalePostgres
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$root = Get-RepoRoot
$backendDir = Resolve-RepoPath "backend"
$desktopEnv = Resolve-RepoPath "desktop\.env"
$mobileEnv = Resolve-RepoPath "mobile-part\.env"
$healthUri = "http://127.0.0.1:$BackendPort/api/v1/health"

Write-Step "Starting TSEBP2025 shared backend"
Write-InfoLog "Repo: $root"

if (-not $SkipPostgres) {
    $pgCtl = Join-Path $PostgresBin "pg_ctl.exe"
    if (-not (Test-Path -LiteralPath $pgCtl)) {
        throw "pg_ctl.exe not found at '$pgCtl'. Pass -PostgresBin or install PostgreSQL."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $DataDir "PG_VERSION"))) {
        throw "Postgres data directory is not initialized: $DataDir. Run shared/scripts/setup-backend-postgres.ps1 or see docs/project/usage/BACKEND_WINDOWS_POSTGRES.md."
    }

    if (Test-PostgresClusterRunning -PgCtl $pgCtl -DataDir $DataDir) {
        Write-SuccessLog "Project PostgreSQL cluster is already running."
    }
    elseif (Test-PortListening -Port $PostgresPort) {
        Assert-PostgresPortFreeForProject -Port $PostgresPort -DataDir $DataDir
    }
    else {
        Write-InfoLog "Starting PostgreSQL on port $PostgresPort."
        Clear-StalePostgresPidFile -DataDir $DataDir -ForceKillRunningPostgresPid:$ForceKillStalePostgres
        $activeLogFile = Resolve-WritableLogFile -LogFile $LogFile
        & $pgCtl -D $DataDir -l $activeLogFile -o "-p $PostgresPort" start
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to start PostgreSQL with pg_ctl."
        }
        Start-Sleep -Seconds 2
        Write-SuccessLog "PostgreSQL started. Log: $activeLogFile"
    }
}
else {
    Write-WarnLog "Skipping PostgreSQL startup."
}

if (-not $SkipClientEnv) {
    Set-DotEnvValue -Path $desktopEnv -Key "VITE_BACKEND_API_URL" -Value $DesktopBackendUrl
    Set-DotEnvValue -Path $mobileEnv -Key "EXPO_PUBLIC_API_URL" -Value $MobileBackendUrl
}

Ensure-BackendEnv -BackendDir $backendDir -DatabaseUrl $DatabaseUrl -Port $BackendPort

if (Test-PortListening -Port $BackendPort) {
    if (Test-HttpEndpoint -Uri $healthUri) {
        Write-SuccessLog "Backend is already running and healthy at $healthUri."
        Write-InfoLog "Leave that backend running, or pass -ForceRestart to stop it and start a new one."
        exit 0
    }

    if (-not $ForceRestart) {
        $pids = (Get-ListeningProcessIds -Port $BackendPort) -join ", "
        throw "Port $BackendPort is in use by PID(s): $pids. Pass -ForceRestart or free the port."
    }

    Stop-ListeningPort -Port $BackendPort
}

Assert-CommandAvailable -CommandName "npm"

if (-not $SkipPrismaGenerate) {
    Invoke-LoggedCommand -WorkingDirectory $backendDir -FilePath "npm" -ArgumentList @("run", "prisma:generate")
}
else {
    Write-WarnLog "Skipping Prisma client generation."
}

if (-not $SkipMigrations) {
    Invoke-LoggedCommand -WorkingDirectory $backendDir -FilePath "npm" -ArgumentList @("run", "db:deploy")
}
else {
    Write-WarnLog "Skipping database migrations."
}

Write-Step "Launching backend dev server"
Write-InfoLog "Health URL after startup: $healthUri"
Invoke-LoggedCommand -WorkingDirectory $backendDir -FilePath "npm" -ArgumentList @("run", "dev")
