[CmdletBinding()]
param(
    [string]$InputDir = "C:\SoftwareProjects\TSEBP2025\ai\data\audio\raw",
    [string]$OutputRoot = "C:\SoftwareProjects\TSEBP2025\ai\data\audio\processed\eartest",
    [string]$PythonExe = "python",
    [string]$SeparatorBackend = "audiosep_hive15cat",
    [string[]]$MaskingMethods = @("wiener_dd", "cirm"),
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:TokenCatalog = @{
    "speech" = @{
        Label = "speech"
        Kind = "speech"
        Note = $null
    }
    "music" = @{
        Label = "music"
        Kind = "non_speech"
        Note = $null
    }
    "barking" = @{
        Label = "dog barking"
        Kind = "non_speech"
        Note = $null
    }
    "dog" = @{
        Label = "dog barking"
        Kind = "non_speech"
        Note = $null
    }
    "keyboard" = @{
        Label = "keyboard typing"
        Kind = "non_speech"
        Note = $null
    }
    "typing" = @{
        Label = "keyboard typing"
        Kind = "non_speech"
        Note = $null
    }
    "alarm" = @{
        Label = "alarm"
        Kind = "non_speech"
        Note = $null
    }
    "phone" = @{
        Label = "phone ringing"
        Kind = "non_speech"
        Note = $null
    }
    "ringing" = @{
        Label = "phone ringing"
        Kind = "non_speech"
        Note = $null
    }
    "wind" = @{
        Label = "wind"
        Kind = "non_speech"
        Note = $null
    }
    "rain" = @{
        Label = "rain"
        Kind = "non_speech"
        Note = $null
    }
    "crowd" = @{
        Label = "crowd noise"
        Kind = "non_speech"
        Note = $null
    }
    "bird" = @{
        Label = "bird singing"
        Kind = "non_speech"
        Note = $null
    }
    "water" = @{
        Label = "water flowing"
        Kind = "non_speech"
        Note = $null
    }
    "door" = @{
        Label = "door knocking"
        Kind = "non_speech"
        Note = $null
    }
    "siren" = @{
        Label = "alarm"
        Kind = "non_speech"
        Note = "Mapped to closest available AudioSepHive15Cat label 'alarm'."
    }
    "boat" = @{
        Label = "car engine"
        Kind = "non_speech"
        Note = "Mapped to closest available AudioSepHive15Cat label 'car engine'."
    }
    "engine" = @{
        Label = "car engine"
        Kind = "non_speech"
        Note = $null
    }
    "office" = @{
        Label = "background noise"
        Kind = "non_speech"
        Note = "Mapped to broad proxy label 'background noise'."
    }
    "background" = @{
        Label = "background noise"
        Kind = "non_speech"
        Note = $null
    }
    "noise" = @{
        Label = "background noise"
        Kind = "non_speech"
        Note = $null
    }
}

function ConvertTo-Slug {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $slug = $Value.ToLowerInvariant() -replace "[^a-z0-9]+", "_"
    return $slug.Trim("_")
}

function Quote-ForDisplay {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if ($Value -match "\s") {
        return '"' + $Value.Replace('"', '\"') + '"'
    }
    return $Value
}

function Resolve-TargetsFromFileName {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileInfo]$WavFile
    )

    $tokens = @($WavFile.BaseName -split "[_\-\s]+" | Where-Object { $_ -and $_.Trim() })
    $resolved = New-Object System.Collections.Generic.List[object]
    $notes = New-Object System.Collections.Generic.List[string]
    $seenLabels = @{}

    foreach ($token in $tokens) {
        $normalized = $token.ToLowerInvariant()
        if (-not $script:TokenCatalog.ContainsKey($normalized)) {
            $notes.Add("Token '$token' has no explicit AudioSepHive15Cat mapping and was ignored.")
            continue
        }

        $entry = $script:TokenCatalog[$normalized]
        $label = [string]$entry.Label
        if (-not $seenLabels.ContainsKey($label)) {
            $seenLabels[$label] = $true
            $resolved.Add(
                [pscustomobject]@{
                    Token = $token
                    Label = $label
                    Kind = [string]$entry.Kind
                }
            )
        }

        if ($entry.Note) {
            $notes.Add("Token '$token': $($entry.Note)")
        }
    }

    return [pscustomobject]@{
        Tokens = @($tokens)
        Targets = @($resolved.ToArray())
        Notes = @($notes.ToArray())
    }
}

function Build-RunPlan {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Targets
    )

    $speechTargets = @($Targets | Where-Object { $_.Kind -eq "speech" })
    $nonSpeechTargets = @($Targets | Where-Object { $_.Kind -ne "speech" })
    $runs = New-Object System.Collections.Generic.List[object]
    $seenLabels = @{}

    function Add-Run {
        param(
            [Parameter(Mandatory = $true)]
            [string]$Label,
            [Parameter(Mandatory = $true)]
            [string]$Reason
        )

        if ($seenLabels.ContainsKey($Label)) {
            return
        }

        $seenLabels[$Label] = $true
        $runs.Add(
            [pscustomobject]@{
                Label = $Label
                Reason = $Reason
                Source = "original"
            }
        )
    }

    $preferredTargets = @()
    if ($nonSpeechTargets.Count -gt 0) {
        $preferredTargets = @($nonSpeechTargets)
    } else {
        $preferredTargets = @($Targets)
    }

    switch ($Targets.Count) {
        0 {
            return @()
        }
        1 {
            Add-Run -Label $Targets[0].Label -Reason "Single-target file -> suppress the single parsed target."
        }
        2 {
            if ($speechTargets.Count -eq 1 -and $nonSpeechTargets.Count -eq 1) {
                Add-Run -Label $nonSpeechTargets[0].Label -Reason "Two-target file with speech + non-speech -> suppress only the non-speech target."
            } else {
                foreach ($target in $preferredTargets) {
                    Add-Run -Label $target.Label -Reason "Two-target file without a single speech/non-speech split -> run one selective suppression per target from the original file."
                }
            }
        }
        default {
            foreach ($target in $preferredTargets) {
                Add-Run -Label $target.Label -Reason "Three-or-more-target file -> suppress this target from the original file to verify selectivity."
            }
        }
    }

    return @($runs.ToArray())
}

function Write-PlanFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [System.IO.FileInfo]$WavFile,
        [Parameter(Mandatory = $true)]
        [object]$Parsed,
        [Parameter(Mandatory = $true)]
        [object[]]$Runs,
        [Parameter(Mandatory = $true)]
        [string[]]$MaskingMethods
    )

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("Source file: $($WavFile.FullName)")
    $lines.Add("Parsed tokens: $([string]::Join(', ', $Parsed.Tokens))")
    $lines.Add("Resolved targets: $([string]::Join(', ', @($Parsed.Targets | ForEach-Object { $_.Label })))")
    $lines.Add("Masking methods: $([string]::Join(', ', $MaskingMethods))")
    $lines.Add("Selection policy: explicit --suppress target labels only; never blanket-suppress all non-speech classes.")
    $lines.Add("")

    if ($Parsed.Notes.Count -gt 0) {
        $lines.Add("Notes:")
        foreach ($note in $Parsed.Notes) {
            $lines.Add("- $note")
        }
        $lines.Add("")
    }

    if ($Runs.Count -eq 0) {
        $lines.Add("Run plan: no runnable suppressions were inferred from this file name.")
    } else {
        $lines.Add("Run plan:")
        $index = 1
        foreach ($run in $Runs) {
            $lines.Add("$index. Suppress '$($run.Label)' from the original file.")
            $lines.Add("   Reason: $($run.Reason)")
            $lines.Add("   Source policy: always start from the original WAV to keep the test selective.")
            $index += 1
        }
    }

    Set-Content -LiteralPath $Path -Value $lines -Encoding UTF8
}

function Invoke-BatchSuppression {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$PythonExe,
        [Parameter(Mandatory = $true)]
        [string]$InputPath,
        [Parameter(Mandatory = $true)]
        [string]$OutputPath,
        [Parameter(Mandatory = $true)]
        [string]$LogPath,
        [Parameter(Mandatory = $true)]
        [string]$SeparatorBackend,
        [Parameter(Mandatory = $true)]
        [string]$MaskingMethod,
        [Parameter(Mandatory = $true)]
        [string]$SuppressLabel
    )

    $cmdArgs = @(
        "-m", "ai.ai_runtime.batch.batch_processor",
        "--input", $InputPath,
        "--output", $OutputPath,
        "--separator-backend", $SeparatorBackend,
        "--masking-method", $MaskingMethod,
        "--suppress", $SuppressLabel
    )

    $displayCommand = $PythonExe + " " + [string]::Join(
        " ",
        @($cmdArgs | ForEach-Object { Quote-ForDisplay -Value ([string]$_) })
    )

    if ($DryRun) {
        Write-Host "[DRY-RUN] $displayCommand"
        Set-Content -LiteralPath $LogPath -Value @(
            "DRY RUN - no command executed.",
            $displayCommand
        ) -Encoding UTF8
        return
    }

    Set-Content -LiteralPath $LogPath -Value @(
        "Command: $displayCommand",
        "Started: $(Get-Date -Format s)",
        ""
    ) -Encoding UTF8

    Push-Location -LiteralPath $RepoRoot
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $capturedOutput = New-Object System.Collections.Generic.List[string]
        try {
            & $PythonExe @cmdArgs 2>&1 | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) {
                    $line = [string]$_.TargetObject
                    if (-not $line) {
                        $line = [string]$_.Exception.Message
                    }
                } else {
                    $line = [string]$_
                }

                $capturedOutput.Add($line)
                Write-Host $line
            }
            $exitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }

        if ($capturedOutput.Count -gt 0) {
            Add-Content -LiteralPath $LogPath -Value @($capturedOutput.ToArray()) -Encoding UTF8
        }
        Add-Content -LiteralPath $LogPath -Value @(
            "",
            "Finished: $(Get-Date -Format s)",
            "ExitCode: $exitCode"
        ) -Encoding UTF8

        if ($exitCode -ne 0) {
            throw "Batch suppression failed with exit code $exitCode. See log: $LogPath"
        }
    } finally {
        Pop-Location
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$resolvedInputDir = (Resolve-Path $InputDir).Path
if (Test-Path -LiteralPath $OutputRoot) {
    $resolvedOutputRoot = (Resolve-Path $OutputRoot).Path
} else {
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    $resolvedOutputRoot = (Resolve-Path $OutputRoot).Path
}

$wavs = @(Get-ChildItem -LiteralPath $resolvedInputDir -Filter *.wav | Sort-Object Name)
if ($wavs.Count -eq 0) {
    throw "No .wav files were found in $resolvedInputDir"
}

$summaryLines = New-Object System.Collections.Generic.List[string]
$summaryLines.Add("AudioSepHive15Cat ear-test run")
$summaryLines.Add("InputDir: $resolvedInputDir")
$summaryLines.Add("OutputRoot: $resolvedOutputRoot")
$summaryLines.Add("MaskingMethods: $([string]::Join(', ', $MaskingMethods))")
$summaryLines.Add("DryRun: $DryRun")
$summaryLines.Add("SelectionPolicy: explicit per-target suppression only; multi-target checks always start from the original WAV.")
$summaryLines.Add("")

foreach ($wav in $wavs) {
    $parsed = Resolve-TargetsFromFileName -WavFile $wav
    $runs = @(Build-RunPlan -Targets $parsed.Targets)
    $caseFolder = Join-Path $resolvedOutputRoot $wav.BaseName
    New-Item -ItemType Directory -Path $caseFolder -Force | Out-Null

    $planPath = Join-Path $caseFolder "run_plan.txt"
    Write-PlanFile -Path $planPath -WavFile $wav -Parsed $parsed -Runs $runs -MaskingMethods $MaskingMethods

    $summaryLines.Add("$($wav.Name) -> $($runs.Count) planned suppression run(s)")
    foreach ($run in $runs) {
        $summaryLines.Add("  - $($run.Label)")
    }

    if ($runs.Count -eq 0) {
        $skipLogPath = Join-Path $caseFolder "skip.log.txt"
        Set-Content -LiteralPath $skipLogPath -Value @(
            "No runnable suppressions were inferred for $($wav.FullName).",
            "See run_plan.txt for details."
        ) -Encoding UTF8
        continue
    }

    foreach ($run in $runs) {
        $targetSlug = ConvertTo-Slug -Value $run.Label
        foreach ($maskingMethod in $MaskingMethods) {
            $outputFile = Join-Path $caseFolder ("suppress_{0}__{1}.wav" -f $targetSlug, $maskingMethod)
            $logFile = Join-Path $caseFolder ("suppress_{0}__{1}.log.txt" -f $targetSlug, $maskingMethod)
            Write-Host ("[{0}] suppress '{1}' with {2}" -f $wav.Name, $run.Label, $maskingMethod)
            Invoke-BatchSuppression `
                -RepoRoot $repoRoot `
                -PythonExe $PythonExe `
                -InputPath $wav.FullName `
                -OutputPath $outputFile `
                -LogPath $logFile `
                -SeparatorBackend $SeparatorBackend `
                -MaskingMethod $maskingMethod `
                -SuppressLabel $run.Label
        }
    }
}

$summaryPath = Join-Path $resolvedOutputRoot "eartest_summary.txt"
Set-Content -LiteralPath $summaryPath -Value $summaryLines -Encoding UTF8
Write-Host "Ear-test outputs are under $resolvedOutputRoot"
Write-Host "Summary written to $summaryPath"
