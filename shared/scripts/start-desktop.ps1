param(
    [string]$BackendUrl = "",
    [string]$BackendScheme = "http",
    [string]$BackendHost = "localhost",
    [int]$BackendPort = 4000,
    [string]$BackendApiPath = "/api/v1",
    [switch]$SkipBackendCheck,
    [switch]$Install,
    [switch]$RunChecks,
    [switch]$WebOnly,
    [switch]$DevUi,
    [switch]$WriteEnvOnly,
    [switch]$NoCargoPath
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$desktopDir = Resolve-RepoPath "desktop"
$desktopEnv = Join-Path $desktopDir ".env"
$BackendUrl = Resolve-BackendApiUrl `
    -Url $BackendUrl `
    -Scheme $BackendScheme `
    -HostName $BackendHost `
    -Port $BackendPort `
    -ApiPath $BackendApiPath
$healthUri = Convert-LocalhostToIPv4 -Url (Join-UrlPath -BaseUrl $BackendUrl -Path "health")
$desktopUiSurface = if ($DevUi) { "dev" } else { "user" }

Write-Step "Starting TSEBP2025 desktop app"
Set-DotEnvValue -Path $desktopEnv -Key "VITE_BACKEND_API_URL" -Value $BackendUrl
Set-DotEnvValue -Path $desktopEnv -Key "VITE_DESKTOP_UI_SURFACE" -Value $desktopUiSurface
Write-SuccessLog "Desktop UI surface: $desktopUiSurface"

if ($WriteEnvOnly) {
    Write-SuccessLog "Desktop environment updated. Skipping launch because -WriteEnvOnly was provided."
    return
}

if (-not $SkipBackendCheck) {
    Write-InfoLog "Checking backend health at $healthUri"
    if (-not (Test-HttpEndpoint -Uri $healthUri)) {
        throw "Backend health check failed. Start it with shared/scripts/start-backend.ps1 or pass -SkipBackendCheck."
    }
    Write-SuccessLog "Backend health check passed."
}

Assert-CommandAvailable -CommandName "npm"

if (-not $NoCargoPath) {
    $cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
    if ((Test-Path -LiteralPath $cargoBin) -and ($env:Path -notlike "*$cargoBin*")) {
        $env:Path = "$env:Path;$cargoBin"
        Write-InfoLog "Added Cargo to PATH for this terminal: $cargoBin"
    }
}

if ($Install -or -not (Test-Path -LiteralPath (Join-Path $desktopDir "node_modules"))) {
    Invoke-LoggedCommand -WorkingDirectory $desktopDir -FilePath "npm" -ArgumentList @("install")
}

if ($RunChecks) {
    Invoke-LoggedCommand -WorkingDirectory $desktopDir -FilePath "npm" -ArgumentList @("run", "lint")
    Invoke-LoggedCommand -WorkingDirectory $desktopDir -FilePath "npm" -ArgumentList @("test")
    Invoke-LoggedCommand -WorkingDirectory $desktopDir -FilePath "npm" -ArgumentList @("run", "build")
}

if ($WebOnly) {
    Write-Step "Launching Vite web dev server"
    Invoke-LoggedCommand -WorkingDirectory $desktopDir -FilePath "npm" -ArgumentList @("run", "dev")
}
else {
    Write-Step "Launching Tauri desktop app"
    Invoke-LoggedCommand -WorkingDirectory $desktopDir -FilePath "npm" -ArgumentList @("run", "tauri:dev")
}
