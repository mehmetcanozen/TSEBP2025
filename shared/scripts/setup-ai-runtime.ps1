param(
    [ValidateSet("runtime", "audio-device", "onnx", "training", "export", "all")]
    [string[]]$Profile = @("runtime"),
    [string]$Python = "python",
    [string]$VenvPath = ".\.venv",
    [switch]$SkipVenv,
    [switch]$UpgradePip
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$root = Get-RepoRoot
$venvFullPath = if ([System.IO.Path]::IsPathRooted($VenvPath)) { $VenvPath } else { Join-Path $root $VenvPath }

Write-Step "Setting up TSEBP2025 AI Python tooling"
Write-InfoLog "Profiles: $($Profile -join ', ')"
Write-InfoLog "Repo: $root"

Assert-CommandAvailable -CommandName $Python

if (-not $SkipVenv) {
    if (-not (Test-Path -LiteralPath $venvFullPath)) {
        Write-InfoLog "Creating virtual environment: $venvFullPath"
        Invoke-LoggedCommand -WorkingDirectory $root -FilePath $Python -ArgumentList @("-m", "venv", $venvFullPath)
    }
    else {
        Write-SuccessLog "Virtual environment already exists: $venvFullPath"
    }

    $pythonExe = Join-Path $venvFullPath "Scripts\python.exe"
}
else {
    $pythonExe = $Python
}

if ($UpgradePip) {
    Invoke-LoggedCommand -WorkingDirectory $root -FilePath $pythonExe -ArgumentList @("-m", "pip", "install", "--upgrade", "pip")
}

$selectedProfiles = [System.Collections.Generic.HashSet[string]]::new()
foreach ($item in $Profile) {
    if ($item -eq "all") {
        foreach ($expanded in @("runtime", "audio-device", "onnx", "training", "export")) {
            [void]$selectedProfiles.Add($expanded)
        }
    }
    else {
        [void]$selectedProfiles.Add($item)
    }
}

if ($selectedProfiles.Count -gt 0) {
    Invoke-LoggedCommand -WorkingDirectory $root -FilePath $pythonExe -ArgumentList @("-m", "pip", "install", "-r", "ai\requirements-runtime.txt")
    Invoke-LoggedCommand -WorkingDirectory $root -FilePath $pythonExe -ArgumentList @("-m", "pip", "install", "-e", ".")
}

if ($selectedProfiles.Contains("audio-device")) {
    Invoke-LoggedCommand -WorkingDirectory $root -FilePath $pythonExe -ArgumentList @("-m", "pip", "install", "sounddevice>=0.4.6")
}

if ($selectedProfiles.Contains("onnx")) {
    Invoke-LoggedCommand -WorkingDirectory $root -FilePath $pythonExe -ArgumentList @("-m", "pip", "install", "onnx>=1.14", "onnxruntime>=1.15")
}

if ($selectedProfiles.Contains("training")) {
    Invoke-LoggedCommand -WorkingDirectory $root -FilePath $pythonExe -ArgumentList @("-m", "pip", "install", "-r", "ai\training\requirements.txt")
}

if ($selectedProfiles.Contains("export")) {
    Invoke-LoggedCommand -WorkingDirectory $root -FilePath $pythonExe -ArgumentList @("-m", "pip", "install", "-r", "ai\export\requirements.txt")
}

Invoke-LoggedCommand -WorkingDirectory $root -FilePath $pythonExe -ArgumentList @("-m", "ai", "diagnostics", "env")
Write-SuccessLog "AI setup completed."
