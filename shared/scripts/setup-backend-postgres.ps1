param(
    [string]$PostgresPassword = "",
    [string]$PostgresBin = "C:\Program Files\PostgreSQL\18\bin",
    [string]$DataDir = "C:\tmp\tsebp2025-postgres-18-data",
    [string]$LogFile = "C:\tmp\tsebp2025-postgres-18.log",
    [string]$PasswordFile = "C:\tmp\tsebp2025-postgres-password.txt",
    [string]$DatabaseName = "tsebp2025",
    [string]$DatabaseUser = "postgres",
    [string]$PostgresHost = "localhost",
    [int]$PostgresPort = 5432,
    [int]$BackendPort = 4000,
    [string]$Locale = "C",
    [string]$BackendScheme = "http",
    [string]$BackendApiPath = "/api/v1",
    [string]$DesktopBackendHost = "localhost",
    [string]$DesktopBackendUrl = "",
    [string]$MobileBackendHost = "10.0.2.2",
    [string]$MobileBackendUrl = "",
    [string]$CorsOrigins = "http://localhost:1420,http://localhost:5173,http://localhost:8080",
    [switch]$ForceRecreateInvalidDataDir,
    [switch]$OverwriteBackendEnv,
    [switch]$SkipNpmInstall,
    [switch]$SkipPrismaGenerate,
    [switch]$SkipMigrations,
    [switch]$StartBackend,
    [switch]$ForceKillStalePostgres
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

function Convert-SecureStringToPlainText {
    param([Parameter(Mandatory = $true)][securestring]$SecureString)

    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$ArgumentList = @()
    )

    $display = ($ArgumentList | ForEach-Object {
        if ($_ -match "\s") { '"' + $_ + '"' } else { $_ }
    }) -join " "
    Write-InfoLog "$FilePath $display"
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $FilePath $display"
    }
}

function Update-BackendEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EnvPath,
        [Parameter(Mandatory = $true)]
        [string]$DatabaseUrl,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$CorsOrigins,
        [switch]$Overwrite
    )

    if ($Overwrite -or -not (Test-Path -LiteralPath $EnvPath)) {
        $secret = New-LocalSecret
        $content = @(
            "NODE_ENV=development",
            "PORT=$Port",
            "CORS_ORIGINS=$CorsOrigins",
            "",
            "DATABASE_URL=$DatabaseUrl",
            "",
            "AUTH_PROVIDER=local",
            "LOCAL_JWT_SECRET=$secret",
            "LOCAL_ACCESS_TOKEN_SECONDS=900",
            "LOCAL_REFRESH_TOKEN_DAYS=30"
        )
        Set-Content -LiteralPath $EnvPath -Value $content -Encoding UTF8
        Write-SuccessLog "Wrote backend env: $EnvPath"
        return
    }

    Write-InfoLog "Updating existing backend/.env without replacing unrelated keys."
    Set-DotEnvValue -Path $EnvPath -Key "NODE_ENV" -Value "development"
    Set-DotEnvValue -Path $EnvPath -Key "PORT" -Value ([string]$Port)
    Set-DotEnvValue -Path $EnvPath -Key "CORS_ORIGINS" -Value $CorsOrigins
    Set-DotEnvValue -Path $EnvPath -Key "DATABASE_URL" -Value $DatabaseUrl
    Set-DotEnvValue -Path $EnvPath -Key "AUTH_PROVIDER" -Value "local"
    Set-DotEnvValue -Path $EnvPath -Key "LOCAL_ACCESS_TOKEN_SECONDS" -Value "900"
    Set-DotEnvValue -Path $EnvPath -Key "LOCAL_REFRESH_TOKEN_DAYS" -Value "30"

    $raw = Get-Content -LiteralPath $EnvPath -Raw
    if ($raw -notmatch "(?m)^LOCAL_JWT_SECRET=(?!replace-with-a-long-random-secret).{32,}$") {
        Set-DotEnvValue -Path $EnvPath -Key "LOCAL_JWT_SECRET" -Value (New-LocalSecret)
    }
}

$root = Get-RepoRoot
$backendDir = Resolve-RepoPath "backend"
$desktopEnv = Resolve-RepoPath "desktop\.env"
$mobileEnv = Resolve-RepoPath "mobile-part\.env"
$backendEnv = Join-Path $backendDir ".env"

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

$initdb = Join-Path $PostgresBin "initdb.exe"
$psql = Join-Path $PostgresBin "psql.exe"
$pgCtl = Join-Path $PostgresBin "pg_ctl.exe"

Write-Step "Setting up local PostgreSQL and backend env"
Write-InfoLog "Repo: $root"
Write-InfoLog "PostgreSQL bin: $PostgresBin"
Write-InfoLog "Data dir: $DataDir"
Write-InfoLog "Database: $DatabaseName"

foreach ($tool in @($initdb, $psql, $pgCtl)) {
    if (-not (Test-Path -LiteralPath $tool)) {
        throw "Required PostgreSQL tool is missing: $tool"
    }
}

if ([string]::IsNullOrWhiteSpace($PostgresPassword)) {
    Write-WarnLog "No -PostgresPassword was provided. Prompting securely."
    $securePassword = Read-Host "Enter local PostgreSQL password for user '$DatabaseUser'" -AsSecureString
    $PostgresPassword = Convert-SecureStringToPlainText -SecureString $securePassword
}

if ([string]::IsNullOrWhiteSpace($PostgresPassword)) {
    throw "PostgreSQL password cannot be empty."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DataDir) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogFile) | Out-Null

if ((Test-Path -LiteralPath $DataDir) -and -not (Test-Path -LiteralPath (Join-Path $DataDir "PG_VERSION"))) {
    if (-not $ForceRecreateInvalidDataDir) {
        throw "Data dir exists but is not a PostgreSQL cluster: $DataDir. Pass -ForceRecreateInvalidDataDir to remove and recreate it."
    }
    Write-WarnLog "Removing invalid data dir because -ForceRecreateInvalidDataDir was provided: $DataDir"
    Remove-Item -LiteralPath $DataDir -Recurse -Force
}

if (-not (Test-Path -LiteralPath (Join-Path $DataDir "PG_VERSION"))) {
    Write-Step "Initializing PostgreSQL cluster with locale=$Locale"
    Set-Content -LiteralPath $PasswordFile -Value $PostgresPassword -Encoding ASCII
    try {
        Invoke-CheckedNative -FilePath $initdb -ArgumentList @(
            "-D", $DataDir,
            "-U", $DatabaseUser,
            "--pwfile=$PasswordFile",
            "--auth=scram-sha-256",
            "--encoding=UTF8",
            "--locale=$Locale"
        )
    }
    finally {
        Remove-Item -LiteralPath $PasswordFile -Force -ErrorAction SilentlyContinue
    }
}
else {
    Write-SuccessLog "PostgreSQL cluster already exists at $DataDir."
}

if (Test-PostgresClusterRunning -PgCtl $pgCtl -DataDir $DataDir) {
    Write-SuccessLog "Project PostgreSQL cluster is already running."
}
elseif (Test-PortListening -Port $PostgresPort) {
    Assert-PostgresPortFreeForProject -Port $PostgresPort -DataDir $DataDir
}
else {
    Write-Step "Starting PostgreSQL on port $PostgresPort"
    Clear-StalePostgresPidFile -DataDir $DataDir -ForceKillRunningPostgresPid:$ForceKillStalePostgres
    $activeLogFile = Resolve-WritableLogFile -LogFile $LogFile
    Invoke-CheckedNative -FilePath $pgCtl -ArgumentList @("-D", $DataDir, "-l", $activeLogFile, "-o", "-p $PostgresPort", "start")
    Start-Sleep -Seconds 2
}

$env:PGPASSWORD = $PostgresPassword
$databaseUrl = New-PostgresDatabaseUrl `
    -DatabaseUser $DatabaseUser `
    -DatabasePassword $PostgresPassword `
    -HostName $PostgresHost `
    -Port $PostgresPort `
    -DatabaseName $DatabaseName

Write-Step "Verifying PostgreSQL connection"
Invoke-CheckedNative -FilePath $psql -ArgumentList @("-h", $PostgresHost, "-p", [string]$PostgresPort, "-U", $DatabaseUser, "-c", "SELECT version();")

$exists = & $psql -h $PostgresHost -p $PostgresPort -U $DatabaseUser -tAc "SELECT 1 FROM pg_database WHERE datname = '$DatabaseName';"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to check whether database '$DatabaseName' exists."
}

if (($exists -join "").Trim() -ne "1") {
    Write-Step "Creating database $DatabaseName"
    Invoke-CheckedNative -FilePath $psql -ArgumentList @("-h", $PostgresHost, "-p", [string]$PostgresPort, "-U", $DatabaseUser, "-c", "CREATE DATABASE $DatabaseName;")
}
else {
    Write-SuccessLog "Database already exists: $DatabaseName"
}

Write-Step "Writing backend, desktop, and mobile env files"
Update-BackendEnv -EnvPath $backendEnv -DatabaseUrl $databaseUrl -Port $BackendPort -CorsOrigins $CorsOrigins -Overwrite:$OverwriteBackendEnv
Set-DotEnvValue -Path $desktopEnv -Key "VITE_BACKEND_API_URL" -Value $DesktopBackendUrl
Set-DotEnvValue -Path $mobileEnv -Key "EXPO_PUBLIC_API_URL" -Value $MobileBackendUrl

Assert-CommandAvailable -CommandName "npm"

if (-not $SkipNpmInstall -and -not (Test-Path -LiteralPath (Join-Path $backendDir "node_modules"))) {
    Invoke-LoggedCommand -WorkingDirectory $backendDir -FilePath "npm" -ArgumentList @("install")
}
elseif ($SkipNpmInstall) {
    Write-WarnLog "Skipping backend npm install."
}

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
    Write-WarnLog "Skipping Prisma migrations."
}

Write-SuccessLog "Backend PostgreSQL setup is complete."
Write-InfoLog "Backend env: $backendEnv"
Write-InfoLog "Desktop API URL: $DesktopBackendUrl"
Write-InfoLog "Mobile emulator API URL: $MobileBackendUrl"

if ($StartBackend) {
    Write-Step "Starting backend after setup"
    & "$PSScriptRoot\start-backend.ps1" `
        -PostgresBin $PostgresBin `
        -DataDir $DataDir `
        -LogFile $LogFile `
        -PostgresPort $PostgresPort `
        -BackendPort $BackendPort `
        -DatabaseUrl $databaseUrl `
        -DesktopBackendUrl $DesktopBackendUrl `
        -MobileBackendUrl $MobileBackendUrl `
        -CorsOrigins $CorsOrigins `
        -ForceKillStalePostgres:$ForceKillStalePostgres `
        -SkipPrismaGenerate:$SkipPrismaGenerate `
        -SkipMigrations:$SkipMigrations
}
else {
    Write-InfoLog "Start backend later with: .\shared\scripts\start-backend.ps1"
}
