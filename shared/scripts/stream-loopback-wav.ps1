param(
    [string]$InputPath = "ai\data\audio\raw\speech_barking.wav",
    [string]$DeviceName = "CABLE Input",
    [Nullable[int]]$DeviceId = $null,
    [int]$Channels = 2,
    [double]$Volume = 0.9,
    [double]$StartSilence = 1.0,
    [string]$Python = "python",
    [switch]$ListDevices,
    [switch]$Once
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$root = Get-RepoRoot
Write-Step "Streaming WAV into a Windows playback endpoint"
Write-InfoLog "This feeds audio into VB-CABLE or another playback endpoint. It does not run suppression."

Assert-CommandAvailable -CommandName $Python

$args = @("-m", "ai.scripts.demos.virtual_mic_streamer")

if ($ListDevices) {
    $args += "--list-devices"
    Invoke-LoggedCommand -WorkingDirectory $root -FilePath $Python -ArgumentList $args
    exit 0
}

$resolvedInput = $InputPath
if (-not [System.IO.Path]::IsPathRooted($resolvedInput)) {
    $resolvedInput = Join-Path $root $resolvedInput
}
if (-not (Test-Path -LiteralPath $resolvedInput)) {
    throw "Input WAV does not exist: $resolvedInput"
}

$args += @("--input", $resolvedInput)
if ($DeviceId.HasValue) {
    $args += @("--device-id", [string]$DeviceId.Value)
}
else {
    $args += @("--device-name", $DeviceName)
}
$args += @("--channels", [string]$Channels)
$args += @("--volume", [string]$Volume)
$args += @("--start-silence", [string]$StartSilence)
if ($Once) {
    $args += "--no-loop"
}

Write-InfoLog "If this fails with missing sounddevice, install it for this Python with: $Python -m pip install sounddevice"
Invoke-LoggedCommand -WorkingDirectory $root -FilePath $Python -ArgumentList $args

