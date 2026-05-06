param(
    [string]$AndroidHome = "$env:LOCALAPPDATA\Android\Sdk",
    [switch]$SkipTypeScript,
    [switch]$SkipAssets,
    [switch]$SkipKotlin,
    [switch]$SkipNative,
    [switch]$FullApk
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$mobileDir = Resolve-RepoPath "mobile-part"
$androidDir = Join-Path $mobileDir "android"

Write-Step "Running mobile Android checks"

$env:ANDROID_HOME = $AndroidHome
$env:ANDROID_SDK_ROOT = $AndroidHome
$env:Path = "$(Join-Path $AndroidHome 'platform-tools');$(Join-Path $AndroidHome 'emulator');$env:Path"

Assert-CommandAvailable -CommandName "npm"

if (-not $SkipTypeScript) {
    Invoke-LoggedCommand -WorkingDirectory $mobileDir -FilePath "npx" -ArgumentList @("tsc", "--noEmit", "--pretty", "false")
}
else {
    Write-WarnLog "Skipping mobile TypeScript check."
}

if (-not $SkipAssets) {
    Invoke-LoggedCommand -WorkingDirectory $androidDir -FilePath ".\gradlew.bat" -ArgumentList @(":app:prepareBundledSuppressionModel")
    Invoke-LoggedCommand -WorkingDirectory $androidDir -FilePath ".\gradlew.bat" -ArgumentList @(":app:mergeDebugAssets")
}
else {
    Write-WarnLog "Skipping Android asset checks."
}

if (-not $SkipKotlin) {
    Invoke-LoggedCommand -WorkingDirectory $androidDir -FilePath ".\gradlew.bat" -ArgumentList @(":app:compileDebugKotlin")
}
else {
    Write-WarnLog "Skipping Kotlin compile."
}

if (-not $SkipNative) {
    Invoke-LoggedCommand -WorkingDirectory $androidDir -FilePath ".\gradlew.bat" -ArgumentList @(":app:externalNativeBuildDebug")
    Invoke-LoggedCommand -WorkingDirectory $androidDir -FilePath ".\gradlew.bat" -ArgumentList @(":app:mergeDebugNativeLibs")
}
else {
    Write-WarnLog "Skipping native/CMake checks."
}

if ($FullApk) {
    Invoke-LoggedCommand -WorkingDirectory $androidDir -FilePath ".\gradlew.bat" -ArgumentList @(":app:assembleDebug")
}

Write-SuccessLog "Mobile Android checks completed."

