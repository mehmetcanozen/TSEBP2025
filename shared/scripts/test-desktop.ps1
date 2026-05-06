param(
    [switch]$SkipLint,
    [switch]$SkipTests,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$desktopDir = Resolve-RepoPath "desktop"
Write-Step "Running desktop checks"

Assert-CommandAvailable -CommandName "npm"

if (-not $SkipLint) {
    Invoke-LoggedCommand -WorkingDirectory $desktopDir -FilePath "npm" -ArgumentList @("run", "lint")
}
else {
    Write-WarnLog "Skipping desktop lint."
}

if (-not $SkipTests) {
    Invoke-LoggedCommand -WorkingDirectory $desktopDir -FilePath "npm" -ArgumentList @("test")
}
else {
    Write-WarnLog "Skipping desktop tests."
}

if (-not $SkipBuild) {
    Invoke-LoggedCommand -WorkingDirectory $desktopDir -FilePath "npm" -ArgumentList @("run", "build")
}
else {
    Write-WarnLog "Skipping desktop build."
}

Write-SuccessLog "Desktop checks completed."

