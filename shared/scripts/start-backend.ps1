param(
    [string]$PostgresBin = "C:\Program Files\PostgreSQL\18\bin",
    [string]$DataDir = "C:\tmp\tsebp2025-postgres-18-data",
    [string]$LogFile = "C:\tmp\tsebp2025-postgres-18.log",
    [int]$PostgresPort = 5432,
    [int]$BackendPort = 4000,
    [string]$PostgresHost = "localhost",
    [string]$DatabaseName = "tsebp2025",
    [string]$DatabaseUser = "postgres",
    [string]$DatabasePassword = "postgres",
    [string]$DatabaseUrl = "",
    [string]$BackendScheme = "http",
    [string]$BackendApiPath = "/api/v1",
    [string]$DesktopBackendHost = "localhost",
    [string]$DesktopBackendUrl = "",
    [string]$MobileBackendHost = "10.0.2.2",
    [string]$MobileBackendUrl = "",
    [string]$CorsOrigins = "http://localhost:1420,http://localhost:5173,http://localhost:8080",
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
$backendEnv = Join-Path $backendDir ".env"

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    $DatabaseUrl = New-PostgresDatabaseUrl `
        -DatabaseUser $DatabaseUser `
        -DatabasePassword $DatabasePassword `
        -HostName $PostgresHost `
        -Port $PostgresPort `
        -DatabaseName $DatabaseName
}

$DesktopBackendUrl = Resolve-BackendApiUrl `
    -Url $DesktopBackendUrl `
    -Scheme $BackendScheme `
    -HostName $DesktopBackendHost `
    -Port $BackendPort `
    -ApiPath $BackendApiPath

$MobileBackendUrl = Resolve-BackendApiUrl `
    -Url $MobileBackendUrl `
    -Scheme $BackendScheme `
    -HostName $MobileBackendHost `
    -Port $BackendPort `
    -ApiPath $BackendApiPath

$backendProbeUrl = New-BackendApiUrl -Scheme "http" -HostName "127.0.0.1" -Port $BackendPort -ApiPath $BackendApiPath
$healthUri = Join-UrlPath -BaseUrl $backendProbeUrl -Path "health"

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

$backendEnvAlreadyExists = Test-Path -LiteralPath $backendEnv
Ensure-BackendEnv -BackendDir $backendDir -DatabaseUrl $DatabaseUrl -Port $BackendPort -CorsOrigins $CorsOrigins
if ($backendEnvAlreadyExists) {
    Set-DotEnvValue -Path $backendEnv -Key "PORT" -Value ([string]$BackendPort)
    Set-DotEnvValue -Path $backendEnv -Key "CORS_ORIGINS" -Value $CorsOrigins

    $databaseOverrideProvided = (
        $PSBoundParameters.ContainsKey("DatabaseUrl") -or
        $PSBoundParameters.ContainsKey("PostgresHost") -or
        $PSBoundParameters.ContainsKey("PostgresPort") -or
        $PSBoundParameters.ContainsKey("DatabaseName") -or
        $PSBoundParameters.ContainsKey("DatabaseUser") -or
        $PSBoundParameters.ContainsKey("DatabasePassword")
    )
    if ($databaseOverrideProvided) {
        Set-DotEnvValue -Path $backendEnv -Key "DATABASE_URL" -Value $DatabaseUrl
    }
}

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
