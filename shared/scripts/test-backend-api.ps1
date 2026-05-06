param(
    [string]$BaseUrl = "http://127.0.0.1:4000/api/v1",
    [string]$Password = "TestPassword123!",
    [string]$Platform = "windows-desktop"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

Write-Step "Smoke-testing backend API"
Write-InfoLog "Base URL: $BaseUrl"

$health = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 5
Write-SuccessLog "Health check passed: status=$($health.status), authProvider=$($health.authProvider)"

$stamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$email = "script-test-$stamp@example.com"
$username = "script_test_$stamp"

$registerBody = @{
    username = $username
    full_name = "Script Test User"
    email = $email
    password = $Password
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/register" -ContentType "application/json" -Body $registerBody | Out-Null
Write-SuccessLog "Registered $email"

$loginBody = @{
    email = $email
    password = $Password
} | ConvertTo-Json

$tokens = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -ContentType "application/json" -Body $loginBody
if (-not $tokens.access_token) {
    throw "Login did not return an access token."
}
Write-SuccessLog "Logged in and received bearer token."

$headers = @{ Authorization = "Bearer $($tokens.access_token)" }
$me = Invoke-RestMethod -Method Get -Uri "$BaseUrl/auth/me" -Headers $headers
Write-SuccessLog "Current user: $($me.email)"

$profileBody = @{
    full_name = "Script Test User Updated"
    bio = "Created by shared/scripts/test-backend-api.ps1"
} | ConvertTo-Json

$profile = Invoke-RestMethod -Method Put -Uri "$BaseUrl/auth/profile" -Headers $headers -ContentType "application/json" -Body $profileBody
Write-SuccessLog "Profile update persisted: $($profile.full_name)"

$deviceBody = @{
    device_id = "$Platform-script-test-$stamp"
    platform = $Platform
    app_version = "script"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$BaseUrl/devices/register" -Headers $headers -ContentType "application/json" -Body $deviceBody | Out-Null
Write-SuccessLog "Device registration passed for platform=$Platform"

if ($tokens.refresh_token) {
    $logoutBody = @{ refresh_token = $tokens.refresh_token } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/logout" -ContentType "application/json" -Body $logoutBody | Out-Null
    Write-SuccessLog "Logout passed."
}

Write-SuccessLog "Backend API smoke test completed."
