param(
    [switch]$SkipBackendLaunch,
    [switch]$SkipDesktopLaunch,
    [switch]$SkipMobileLaunch,
    [switch]$StartEmulator,
    [switch]$ForceKillStalePostgres,
    [string]$AndroidHome = "$env:LOCALAPPDATA\Android\Sdk",
    [string]$MobilePackage = "com.anonymous.mobiletest",
    [string]$LogDirectory = (Join-Path $PSScriptRoot ".script-test-logs"),
    [int]$BackendPort = 4000,
    [int]$MetroPort = 8081,
    [int]$DesktopWebPort = 8080,
    [int]$BackendTimeoutSeconds = 90,
    [int]$DesktopTimeoutSeconds = 90,
    [int]$AndroidDeviceTimeoutSeconds = 180,
    [int]$AndroidInstallTimeoutSeconds = 360
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

function Invoke-TestStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$ScriptBlock
    )

    Write-Host ""
    Write-Host "========== TEST: $Name ==========" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    & $ScriptBlock
    $code = $LASTEXITCODE
    if ($null -ne $code -and $code -ne 0) {
        throw "$Name failed with exit code $code"
    }
    Write-Host "========== PASS: $Name ==========" -ForegroundColor Green
}

function Wait-Http {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSeconds = 60,
        $ProcessHandle = $null
    )

    $probeUrl = Convert-LocalhostToIPv4 -Url $Url
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpEndpoint -Uri $probeUrl -TimeoutSeconds 2) {
            return
        }
        if ($null -ne $ProcessHandle -and $null -ne $ProcessHandle.Process -and $ProcessHandle.Process.HasExited) {
            throw "$($ProcessHandle.Name) launcher exited before $probeUrl became healthy."
        }
        Start-Sleep -Seconds 1
    }

    throw "Timed out waiting for $probeUrl"
}

function Wait-AdbDevice {
    param([int]$TimeoutSeconds = 180)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $devices = adb devices | Select-String -Pattern "\sdevice$"
        if ($devices) {
            return
        }
        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for Android device"
}

function Wait-AndroidPackage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PackageName,
        [int]$TimeoutSeconds = 360
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $path = adb shell pm path $PackageName 2>$null
        if ($path -match "package:") {
            return
        }
        Start-Sleep -Seconds 3
    }

    throw "Timed out waiting for Android package $PackageName"
}

function Show-LogTail {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [int]$Lines = 80
    )

    if (Test-Path -LiteralPath $Path) {
        Write-Host ""
        Write-Host "----- LOG TAIL: $Path -----" -ForegroundColor DarkYellow
        Get-Content -LiteralPath $Path -Tail $Lines
    }
}

function Start-ScriptProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [string[]]$Arguments = @()
    )

    $safeName = $Name -replace "[^A-Za-z0-9_.-]", "_"
    $stdoutPath = Join-Path $LogDirectory "$safeName.out.log"
    $stderrPath = Join-Path $LogDirectory "$safeName.err.log"

    Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue

    Write-InfoLog "Launching $Name"
    Write-InfoLog "stdout: $stdoutPath"
    Write-InfoLog "stderr: $stderrPath"

    $process = Start-Process powershell `
        -ArgumentList (@("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ScriptPath) + $Arguments) `
        -WorkingDirectory (Get-RepoRoot) `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru `
        -WindowStyle Hidden

    return [pscustomobject]@{
        Name = $Name
        Process = $process
        StdoutPath = $stdoutPath
        StderrPath = $stderrPath
    }
}

function Stop-ScriptProcess {
    param($Handle)

    if ($null -ne $Handle -and $null -ne $Handle.Process -and -not $Handle.Process.HasExited) {
        Write-WarnLog "Stopping $($Handle.Name) launcher PID $($Handle.Process.Id)."
        Stop-Process -Id $Handle.Process.Id -Force -ErrorAction SilentlyContinue
    }
}

function Stop-OwnedTestPorts {
    param(
        [switch]$Backend,
        [switch]$Desktop,
        [switch]$Mobile
    )

    if ($Backend) {
        Stop-ListeningPort -Port $BackendPort
    }
    if ($Mobile) {
        Stop-ListeningPort -Port $MetroPort
    }
    if ($Desktop) {
        Stop-ListeningPort -Port $DesktopWebPort
        if ($DesktopWebPort -ne 5173) {
            Stop-ListeningPort -Port 5173
        }
    }
}

$root = Get-RepoRoot
$backendProcess = $null
$desktopProcess = $null
$mobileProcess = $null

New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null

Write-Step "Testing shared developer scripts"
Write-InfoLog "Repo: $root"
Write-InfoLog "Logs: $LogDirectory"
Write-InfoLog "The setup-backend-postgres.ps1 and stop-postgres.ps1 scripts are intentionally excluded."

try {
    Stop-OwnedTestPorts `
        -Backend:(-not $SkipBackendLaunch) `
        -Desktop:(-not $SkipDesktopLaunch) `
        -Mobile:(-not $SkipMobileLaunch)

    Invoke-TestStep "PowerShell syntax parse" {
        $scripts = Get-ChildItem -LiteralPath $PSScriptRoot -Filter *.ps1 |
            Where-Object { $_.Name -notin @("setup-backend-postgres.ps1", "stop-postgres.ps1") }

        foreach ($script in $scripts) {
            $tokens = $null
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($script.FullName, [ref]$tokens, [ref]$errors) | Out-Null
            if ($errors.Count -gt 0) {
                $errors | ForEach-Object { Write-Host "$($script.Name): $($_.Message)" -ForegroundColor Red }
                throw "Syntax errors in $($script.Name)"
            }
            Write-Host "[OK] $($script.Name)" -ForegroundColor Green
        }
    }

    Invoke-TestStep "stop-port.ps1 unused port" {
        powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\stop-port.ps1" -Port 59999
    }

    Invoke-TestStep "test-desktop.ps1 wrapper" {
        powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\test-desktop.ps1" -SkipLint -SkipTests -SkipBuild
    }

    Invoke-TestStep "test-mobile-android.ps1 TypeScript-only" {
        powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\test-mobile-android.ps1" -SkipAssets -SkipKotlin -SkipNative
    }

    Invoke-TestStep "stream-loopback-wav.ps1 list devices" {
        powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\stream-loopback-wav.ps1" -ListDevices
    }

    if (-not $SkipBackendLaunch) {
        Write-Host ""
        Write-Host "========== TEST: start-backend.ps1 ==========" -ForegroundColor Cyan
        $backendArgs = @("-SkipPrismaGenerate", "-SkipMigrations", "-ForceRestart", "-BackendPort", [string]$BackendPort)
        if ($ForceKillStalePostgres) {
            $backendArgs += "-ForceKillStalePostgres"
        }

        $backendProcess = Start-ScriptProcess `
            -Name "backend" `
            -ScriptPath "$PSScriptRoot\start-backend.ps1" `
            -Arguments $backendArgs

        $backendBaseUrl = New-BackendApiUrl -Scheme "http" -HostName "127.0.0.1" -Port $BackendPort -ApiPath "/api/v1"
        try {
            Wait-Http `
                -Url (Join-UrlPath -BaseUrl $backendBaseUrl -Path "health") `
                -TimeoutSeconds $BackendTimeoutSeconds `
                -ProcessHandle $backendProcess
        }
        catch {
            Show-LogTail -Path $backendProcess.StdoutPath
            Show-LogTail -Path $backendProcess.StderrPath
            throw
        }

        Write-Host "========== PASS: start-backend.ps1 ==========" -ForegroundColor Green

        Invoke-TestStep "test-backend-api.ps1" {
            powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\test-backend-api.ps1" -BaseUrl $backendBaseUrl
        }
    }
    else {
        Write-WarnLog "Skipping backend launch."
    }

    if (-not $SkipDesktopLaunch) {
        foreach ($surfaceCase in @(
            @{ Label = "start-desktop.ps1 user UI config"; Args = @("-SkipBackendCheck", "-WriteEnvOnly"); Expected = "user" },
            @{ Label = "start-desktop.ps1 dev UI config"; Args = @("-SkipBackendCheck", "-WriteEnvOnly", "-DevUi"); Expected = "dev" }
        )) {
            Invoke-TestStep $surfaceCase.Label {
                powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\start-desktop.ps1" @($surfaceCase.Args)
                $desktopEnv = Join-Path $root "desktop\.env"
                $surfaceLine = Get-Content -LiteralPath $desktopEnv |
                    Select-String -Pattern "^VITE_DESKTOP_UI_SURFACE=$($surfaceCase.Expected)$" -Quiet
                if (-not $surfaceLine) {
                    throw "Desktop .env did not contain VITE_DESKTOP_UI_SURFACE=$($surfaceCase.Expected)."
                }
            }
        }

        Set-DotEnvValue -Path (Join-Path $root "desktop\.env") -Key "VITE_DESKTOP_UI_SURFACE" -Value "user"
    }
    else {
        Write-WarnLog "Skipping desktop launch."
    }

    if (-not $SkipMobileLaunch) {
        Write-Host ""
        Write-Host "========== TEST: start-mobile-android.ps1 ==========" -ForegroundColor Cyan

        $env:ANDROID_HOME = $AndroidHome
        $env:ANDROID_SDK_ROOT = $AndroidHome
        $env:Path = "$AndroidHome\platform-tools;$AndroidHome\emulator;$env:Path"
        Assert-CommandAvailable -CommandName "adb"

        $mobileArgs = @("-CleanInstall", "-BackendPort", [string]$BackendPort, "-MetroPort", [string]$MetroPort)
        if ($StartEmulator) {
            $mobileArgs += "-StartEmulator"
        }

        $mobileProcess = Start-ScriptProcess `
            -Name "mobile-android" `
            -ScriptPath "$PSScriptRoot\start-mobile-android.ps1" `
            -Arguments $mobileArgs

        try {
            Wait-AdbDevice -TimeoutSeconds $AndroidDeviceTimeoutSeconds
            Wait-AndroidPackage -PackageName $MobilePackage -TimeoutSeconds $AndroidInstallTimeoutSeconds
            adb shell monkey -p $MobilePackage 1 | Out-Null
            Start-Sleep -Seconds 5

            $appPid = adb shell pidof $MobilePackage 2>$null
            if (-not $appPid) {
                throw "Android package $MobilePackage installed but is not running."
            }
        }
        catch {
            Show-LogTail -Path $mobileProcess.StdoutPath
            Show-LogTail -Path $mobileProcess.StderrPath
            throw
        }

        Write-Host "========== PASS: start-mobile-android.ps1 ==========" -ForegroundColor Green
    }
    else {
        Write-WarnLog "Skipping mobile launch."
    }

    Write-Host ""
    Write-Host "ALL SCRIPT CHECKS PASSED" -ForegroundColor Green
}
finally {
    Stop-ScriptProcess -Handle $mobileProcess
    Stop-ScriptProcess -Handle $desktopProcess
    Stop-ScriptProcess -Handle $backendProcess

    if (-not $SkipMobileLaunch -and (Get-Command adb -ErrorAction SilentlyContinue)) {
        adb shell am force-stop $MobilePackage 2>$null
    }

    Stop-OwnedTestPorts `
        -Backend:(-not $SkipBackendLaunch) `
        -Desktop:(-not $SkipDesktopLaunch) `
        -Mobile:(-not $SkipMobileLaunch)
}
