param(
    [string]$BackendUrl = "http://10.0.2.2:4000/api/v1",
    [string]$AndroidHome = "$env:LOCALAPPDATA\Android\Sdk",
    [string]$AvdName = "Medium_Phone_API_36.1",
    [string]$DeviceId = "",
    [int]$MetroPort = 8081,
    [int]$BackendPort = 4000,
    [switch]$StartEmulator,
    [switch]$UseAdbReverseBackend,
    [switch]$SkipMetroReverse,
    [switch]$CleanInstall,
    [switch]$Install,
    [switch]$PrepareAssets
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$mobileDir = Resolve-RepoPath "mobile-part"
$androidDir = Join-Path $mobileDir "android"
$mobileEnv = Join-Path $mobileDir ".env"

Write-Step "Starting TSEBP2025 Android mobile app"

$env:NODE_ENV = "development"
$env:ANDROID_HOME = $AndroidHome
$env:ANDROID_SDK_ROOT = $AndroidHome
$platformTools = Join-Path $AndroidHome "platform-tools"
$emulatorTools = Join-Path $AndroidHome "emulator"
$env:Path = "$platformTools;$emulatorTools;$env:Path"

Assert-CommandAvailable -CommandName "adb"
Assert-CommandAvailable -CommandName "npm"

if ($UseAdbReverseBackend) {
    $BackendUrl = "http://localhost:$BackendPort/api/v1"
    Write-InfoLog "Using adb reverse for backend. Mobile URL becomes $BackendUrl"
}

Set-DotEnvValue -Path $mobileEnv -Key "EXPO_PUBLIC_API_URL" -Value $BackendUrl

function Invoke-Adb {
    param([string[]]$AdbArgs)
    if ($DeviceId) {
        & adb -s $DeviceId @AdbArgs
    }
    else {
        & adb @AdbArgs
    }
    if ($LASTEXITCODE -ne 0) {
        throw "adb command failed: adb $($AdbArgs -join ' ')"
    }
}

function Get-ReadyAdbDeviceIds {
    $deviceIds = @()
    foreach ($line in @(adb devices)) {
        if ($line -match "^(\S+)\s+device$") {
            $deviceIds += $Matches[1]
        }
    }

    return @($deviceIds)
}

$readyDeviceIds = @(Get-ReadyAdbDeviceIds)

if ($readyDeviceIds.Count -eq 0 -and $StartEmulator) {
    $emulatorExe = Join-Path $emulatorTools "emulator.exe"
    if (-not (Test-Path -LiteralPath $emulatorExe)) {
        throw "emulator.exe not found at $emulatorExe"
    }
    Write-InfoLog "Starting Android emulator AVD '$AvdName'."
    Start-Process -FilePath $emulatorExe -ArgumentList @("-avd", $AvdName, "-netdelay", "none", "-netspeed", "full")
    & adb wait-for-device
    if ($LASTEXITCODE -ne 0) {
        throw "Timed out waiting for Android device."
    }
    $readyDeviceIds = @(Get-ReadyAdbDeviceIds)
}

if ($readyDeviceIds.Count -eq 0) {
    Write-WarnLog "No Android device is ready."
    Write-InfoLog "Run with -StartEmulator or open an emulator/device, then rerun this script."
    & adb devices -l
    exit 1
}

if ($DeviceId) {
    if ($readyDeviceIds -notcontains $DeviceId) {
        & adb devices -l
        throw "Requested Android device '$DeviceId' is not ready. Ready device(s): $($readyDeviceIds -join ', ')."
    }
}
elseif ($readyDeviceIds.Count -gt 1) {
    & adb devices -l
    throw "Multiple Android devices are ready: $($readyDeviceIds -join ', '). Pass -DeviceId to choose one."
}
else {
    $DeviceId = $readyDeviceIds[0]
}

Write-SuccessLog "Android device ready: $DeviceId"
adb devices -l

$env:ANDROID_SERIAL = $DeviceId
Write-InfoLog "Using ANDROID_SERIAL=$DeviceId"

if (-not $SkipMetroReverse) {
    Invoke-Adb -AdbArgs @("reverse", "tcp:$MetroPort", "tcp:$MetroPort")
    Write-SuccessLog "Reversed Metro port $MetroPort."
}

if ($UseAdbReverseBackend) {
    Invoke-Adb -AdbArgs @("reverse", "tcp:$BackendPort", "tcp:$BackendPort")
    Write-SuccessLog "Reversed backend port $BackendPort."
}

if ($Install -or -not (Test-Path -LiteralPath (Join-Path $mobileDir "node_modules"))) {
    Invoke-LoggedCommand -WorkingDirectory $mobileDir -FilePath "npm" -ArgumentList @("install")
}

if ($PrepareAssets) {
    Invoke-LoggedCommand -WorkingDirectory $androidDir -FilePath ".\gradlew.bat" -ArgumentList @(":app:prepareBundledSuppressionModel")
    Invoke-LoggedCommand -WorkingDirectory $androidDir -FilePath ".\gradlew.bat" -ArgumentList @(":app:mergeDebugAssets")
}

if ($CleanInstall) {
    Write-WarnLog "Uninstalling existing development app if present."
    if ($DeviceId) {
        & adb -s $DeviceId uninstall com.anonymous.mobiletest | Out-Host
    }
    else {
        & adb uninstall com.anonymous.mobiletest | Out-Host
    }
}

Write-Step "Launching Expo Android development build"
Invoke-LoggedCommand -WorkingDirectory $mobileDir -FilePath "npm" -ArgumentList @("run", "android")
