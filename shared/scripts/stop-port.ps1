param(
    [Parameter(Mandatory = $true)]
    [int]$Port
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

Write-Step "Stopping processes listening on port $Port"
Stop-ListeningPort -Port $Port

