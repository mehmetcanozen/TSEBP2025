Set-StrictMode -Version Latest

function Get-RepoRoot {
    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
}

function Resolve-RepoPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    return (Join-Path (Get-RepoRoot) $RelativePath)
}

function Write-LogLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Level,
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Gray
    )

    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp][$Level] $Message" -ForegroundColor $Color
}

function Write-Step {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-LogLine -Level "STEP" -Message $Message -Color Cyan
}

function Write-InfoLog {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-LogLine -Level "INFO" -Message $Message -Color Gray
}

function Write-SuccessLog {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-LogLine -Level " OK " -Message $Message -Color Green
}

function Write-WarnLog {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-LogLine -Level "WARN" -Message $Message -Color Yellow
}

function Assert-CommandAvailable {
    param([Parameter(Mandatory = $true)][string]$CommandName)

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Required command '$CommandName' was not found on PATH."
    }
}

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$ArgumentList = @()
    )

    $display = ($ArgumentList | ForEach-Object {
        if ($_ -match "\s") { '"' + $_ + '"' } else { $_ }
    }) -join " "

    Write-InfoLog "($WorkingDirectory)> $FilePath $display"
    Push-Location $WorkingDirectory
    try {
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code $LASTEXITCODE`: $FilePath $display"
        }
    }
    finally {
        Pop-Location
    }
}

function Test-PortListening {
    param([Parameter(Mandatory = $true)][int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($connections) {
        return $true
    }

    $client = New-Object Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(750, $false)
        if (-not $connected) {
            return $false
        }

        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Get-ListeningProcessIds {
    param([Parameter(Mandatory = $true)][int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        return @()
    }

    return @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Stop-ListeningPort {
    param([Parameter(Mandatory = $true)][int]$Port)

    $processIds = @(Get-ListeningProcessIds -Port $Port)
    if ($processIds.Count -eq 0) {
        Write-SuccessLog "Port $Port is already free."
        return
    }

    foreach ($processId in $processIds) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) {
            Write-WarnLog "Stopping PID $processId ($($process.ProcessName)) listening on port $Port."
            Stop-Process -Id $processId -Force -ErrorAction Stop
        }
    }
}

function Test-HttpEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [int]$TimeoutSeconds = 3
    )

    try {
        Invoke-RestMethod -Uri $Uri -TimeoutSec $TimeoutSeconds | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Convert-LocalhostToIPv4 {
    param([Parameter(Mandatory = $true)][string]$Url)

    # PowerShell HTTP clients can occasionally stall on localhost/IPv6 on
    # Windows while the dev server is reachable on IPv4. Keep app-facing env
    # URLs unchanged, but use 127.0.0.1 for script health probes.
    return ($Url -replace "^http://localhost(?=[:/])", "http://127.0.0.1")
}

function Test-PostgresClusterRunning {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PgCtl,
        [Parameter(Mandatory = $true)]
        [string]$DataDir
    )

    & $PgCtl -D $DataDir status *> $null
    return ($LASTEXITCODE -eq 0)
}

function Assert-PostgresPortFreeForProject {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$DataDir
    )

    $processIds = @(Get-ListeningProcessIds -Port $Port)
    $pidDetail = ""
    if ($processIds.Count -gt 0) {
        $pidDetail = " PID(s): $($processIds -join ',')."
    }

    throw "Port $Port is already listening, but the project PostgreSQL cluster is not running for data dir '$DataDir'.$pidDetail Stop that listener, or pass -PostgresPort with a free port, then rerun this script."
}

function Clear-StalePostgresPidFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataDir,
        [switch]$ForceKillRunningPostgresPid
    )

    $pidFile = Join-Path $DataDir "postmaster.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) {
        return
    }

    $lines = @(Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue)
    if ($lines.Count -eq 0) {
        return
    }

    $serverPid = 0
    if (-not [int]::TryParse(($lines[0].Trim()), [ref]$serverPid)) {
        return
    }

    $process = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -like "postgres*") {
        if ($ForceKillRunningPostgresPid) {
            Write-WarnLog "Force-stopping stale PostgreSQL PID $serverPid ($($process.ProcessName))."
            Stop-Process -Id $serverPid -Force -ErrorAction Stop
            Start-Sleep -Seconds 1

            $stillRunning = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
            if ($stillRunning) {
                throw "PostgreSQL PID $serverPid is still running after Stop-Process. Run PowerShell as administrator or restart Windows, then rerun this script."
            }

            Write-WarnLog "Removing stale PostgreSQL PID file after force stop: $pidFile"
            Remove-Item -LiteralPath $pidFile -Force -ErrorAction Stop
            return
        }

        throw "PostgreSQL PID file points at running PID $serverPid ($($process.ProcessName)), but pg_ctl status did not report a healthy project cluster. Stop the stale PostgreSQL process, or restart Windows, then rerun this script. Data dir: $DataDir"
    }

    Write-WarnLog "Removing stale PostgreSQL PID file: $pidFile"
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction Stop
}

function Resolve-WritableLogFile {
    param([Parameter(Mandatory = $true)][string]$LogFile)

    $directory = Split-Path -Parent $LogFile
    if ($directory) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }

    try {
        $stream = [System.IO.File]::Open(
            $LogFile,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::ReadWrite
        )
        $stream.Dispose()
        return $LogFile
    }
    catch {
        $fallback = Join-Path $directory ("tsebp2025-postgres-18-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
        Write-WarnLog "Cannot write PostgreSQL log '$LogFile'. Using '$fallback' instead."
        return $fallback
    }
}

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $directory = Split-Path -Parent $Path
    if ($directory -and -not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }

    $lines = @()
    if (Test-Path -LiteralPath $Path) {
        $lines = @(Get-Content -LiteralPath $Path)
    }

    $pattern = "^\s*$([regex]::Escape($Key))="
    $updated = $false
    $newLines = @(foreach ($line in $lines) {
        if ($line -match $pattern) {
            $updated = $true
            "$Key=$Value"
        }
        else {
            $line
        }
    })

    if (-not $updated) {
        $newLines += "$Key=$Value"
    }

    Set-Content -LiteralPath $Path -Value $newLines -Encoding UTF8
    Write-SuccessLog "Wrote $Key to $Path"
}

function New-LocalSecret {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 48
    $rng.GetBytes($bytes)
    return [Convert]::ToBase64String($bytes)
}

function Ensure-BackendEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BackendDir,
        [Parameter(Mandatory = $true)]
        [string]$DatabaseUrl,
        [int]$Port = 4000
    )

    $envPath = Join-Path $BackendDir ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        Write-WarnLog "backend/.env is missing. Creating a local development .env."
        $secret = New-LocalSecret
        $content = @(
            "NODE_ENV=development",
            "PORT=$Port",
            "CORS_ORIGINS=http://localhost:1420,http://localhost:5173,http://localhost:8080",
            "",
            "DATABASE_URL=$DatabaseUrl",
            "",
            "AUTH_PROVIDER=local",
            "LOCAL_JWT_SECRET=$secret",
            "LOCAL_ACCESS_TOKEN_SECONDS=900",
            "LOCAL_REFRESH_TOKEN_DAYS=30"
        )
        Set-Content -LiteralPath $envPath -Value $content -Encoding UTF8
        Write-SuccessLog "Created $envPath"
    }
}
