# Backend Windows PostgreSQL Runbook

This is the exact Windows setup path for the shared backend when PostgreSQL is
installed but the server is not already running as a Windows service.

Use this when:

- `pgAdmin` opens, but `psql` is not recognized.
- `psql.exe --version` works by full path.
- Prisma reports `P1001: Can't reach database server at localhost:5432`.
- `pg_ctl` says the installer data directory is not a database cluster.
- `initdb` fails on Turkish Windows locale with non-ASCII locale text.

The backend uses PostgreSQL only for app data: auth, profiles, settings,
history metadata, and devices. It does not store model artifacts and does not
run audio suppression.

## Known-Good Local Layout

This project-local development setup uses:

```text
PostgreSQL binaries: C:\Program Files\PostgreSQL\18\bin
PostgreSQL data dir: C:\tmp\tsebp2025-postgres-18-data
PostgreSQL log file: C:\tmp\tsebp2025-postgres-18.log
Database name:       tsebp2025
Database user:       postgres
Backend API:         http://localhost:4000/api/v1
Mobile emulator API: http://10.0.2.2:4000/api/v1
Desktop API:         http://localhost:4000/api/v1
Auth mode:           local
```

Do not run `postgres` manually. Start the local server through `pg_ctl`.

Do not assume pgAdmin means the database server is running. pgAdmin is only the
GUI.

## One-Time Setup

Recommended path:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\setup-backend-postgres.ps1 -PostgresPassword "<YOUR_POSTGRES_PASSWORD>"
```

Use `-StartBackend` if you want setup to immediately launch the backend after
the database and migrations are ready:

```powershell
.\shared\scripts\setup-backend-postgres.ps1 `
  -PostgresPassword "<YOUR_POSTGRES_PASSWORD>" `
  -StartBackend
```

The script is the maintained version of the manual command block below. It
uses the same known-good data directory, `initdb --locale=C`, password URL
encoding, `.env` writing, Prisma generation, and `db:deploy` migration path.

## Manual Fallback

Replace only `<YOUR_POSTGRES_PASSWORD>` with the PostgreSQL password you chose
during installation, then paste the whole block into PowerShell.

```powershell
cd C:\SoftwareProjects\TSEBP2025

$ErrorActionPreference = "Stop"

$pgPassword = "<YOUR_POSTGRES_PASSWORD>"
$pgBin = "C:\Program Files\PostgreSQL\18\bin"
$initdb = "$pgBin\initdb.exe"
$psql = "$pgBin\psql.exe"
$pgCtl = "$pgBin\pg_ctl.exe"

$dataDir = "C:\tmp\tsebp2025-postgres-18-data"
$logFile = "C:\tmp\tsebp2025-postgres-18.log"
$pwFile = "C:\tmp\tsebp2025-postgres-password.txt"

function Run-Checked {
  param([scriptblock]$Command)
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code $LASTEXITCODE"
  }
}

New-Item -ItemType Directory -Force -Path "C:\tmp" | Out-Null

if ((Test-Path -LiteralPath $dataDir) -and !(Test-Path -LiteralPath "$dataDir\PG_VERSION")) {
  Remove-Item -LiteralPath $dataDir -Recurse -Force
}

if (!(Test-Path -LiteralPath "$dataDir\PG_VERSION")) {
  Set-Content -LiteralPath $pwFile -Value $pgPassword -Encoding ASCII
  Run-Checked { & $initdb -D $dataDir -U postgres --pwfile=$pwFile --auth=scram-sha-256 --encoding=UTF8 --locale=C }
}

$alreadyListening = Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue

if (-not $alreadyListening) {
  Run-Checked { & $pgCtl -D $dataDir -l $logFile -o "-p 5432" start }
  Start-Sleep -Seconds 3
}

$encodedPassword = [uri]::EscapeDataString($pgPassword)
$env:PGPASSWORD = $pgPassword

Run-Checked { & $psql -h localhost -p 5432 -U postgres -c "SELECT version();" }

$exists = & $psql -h localhost -p 5432 -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'tsebp2025';"

if (($exists -join "").Trim() -ne "1") {
  Run-Checked { & $psql -h localhost -p 5432 -U postgres -c "CREATE DATABASE tsebp2025;" }
}

$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$bytes = New-Object byte[] 48
$rng.GetBytes($bytes)
$jwtSecret = [Convert]::ToBase64String($bytes)

@"
NODE_ENV=development
PORT=4000
CORS_ORIGINS=http://localhost:1420,http://localhost:5173,http://localhost:8080

DATABASE_URL=postgresql://postgres:$encodedPassword@localhost:5432/tsebp2025?schema=public

AUTH_PROVIDER=local
LOCAL_JWT_SECRET=$jwtSecret
LOCAL_ACCESS_TOKEN_SECONDS=900
LOCAL_REFRESH_TOKEN_DAYS=30
"@ | Set-Content -LiteralPath .\backend\.env -Encoding UTF8

"EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1" | Set-Content -LiteralPath .\mobile-part\.env -Encoding UTF8
"VITE_BACKEND_API_URL=http://localhost:4000/api/v1" | Set-Content -LiteralPath .\desktop\.env -Encoding UTF8

cd .\backend
npm run prisma:generate
npm run db:migrate
npm run dev
```

If Prisma asks for a migration name, use:

```text
init_shared_backend
```

When `npm run dev` starts, leave that terminal open.

## Health Check

Open a second PowerShell and run:

```powershell
Invoke-RestMethod http://localhost:4000/api/v1/health
```

Expected:

```text
status       : ok
authProvider : local
```

## Auth Smoke Test

Run this from a second PowerShell while the backend is still running:

```powershell
$base = "http://localhost:4000/api/v1"
$suffix = Get-Random

$registerBody = @{
  username = "probe_$suffix"
  full_name = "Probe User"
  email = "probe$suffix@example.com"
  password = "TestPassword123!"
} | ConvertTo-Json

Invoke-RestMethod "$base/auth/register" `
  -Method Post `
  -ContentType "application/json" `
  -Body $registerBody

$loginBody = @{
  email = "probe$suffix@example.com"
  password = "TestPassword123!"
} | ConvertTo-Json

$tokens = Invoke-RestMethod "$base/auth/login" `
  -Method Post `
  -ContentType "application/json" `
  -Body $loginBody

Invoke-RestMethod "$base/auth/me" `
  -Headers @{ Authorization = "Bearer $($tokens.access_token)" }
```

## Starting Later

After the one-time setup, future backend starts are shorter.

Terminal 1:

```powershell
cd C:\SoftwareProjects\TSEBP2025

$pgCtl = "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"
$dataDir = "C:\tmp\tsebp2025-postgres-18-data"
$logFile = "C:\tmp\tsebp2025-postgres-18.log"

$alreadyListening = Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue
if (-not $alreadyListening) {
  & $pgCtl -D $dataDir -l $logFile -o "-p 5432" start
}

cd .\backend
npm run dev
```

Terminal 2:

```powershell
Invoke-RestMethod http://localhost:4000/api/v1/health
```

## Stopping The Local PostgreSQL Server

The backend stops with `Ctrl+C`. To stop the local PostgreSQL cluster too:

```powershell
$pgCtl = "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"
$dataDir = "C:\tmp\tsebp2025-postgres-18-data"

& $pgCtl -D $dataDir stop
```

## Troubleshooting

### psql Is Not Recognized

Use the full path:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" --version
```

To add it to the current terminal only:

```powershell
$env:Path = "C:\Program Files\PostgreSQL\18\bin;$env:Path"
```

To add it permanently for future terminals:

```powershell
$pgBin = "C:\Program Files\PostgreSQL\18\bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")

if ($userPath -notlike "*$pgBin*") {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$pgBin", "User")
}
```

Close and reopen PowerShell after the permanent PATH change.

### pg_ctl Says The Data Directory Is Not A Database Cluster

This means the directory does not contain `PG_VERSION`. Do not use that folder
as-is.

The known-good local command above creates a fresh cluster under:

```text
C:\tmp\tsebp2025-postgres-18-data
```

### initdb Fails On Turkish Locale

If the error mentions:

```text
locale name "Turkish_Türkiye.1252" contains non-ASCII characters
```

initialize with:

```powershell
--locale=C
```

The one-time setup command already includes this.

### Prisma P1001

Error:

```text
P1001: Can't reach database server at localhost:5432
```

Check that PostgreSQL is listening:

```powershell
Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue
```

If nothing prints, start the local cluster:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" `
  -D "C:\tmp\tsebp2025-postgres-18-data" `
  -l "C:\tmp\tsebp2025-postgres-18.log" `
  -o "-p 5432" `
  start
```

### Health Route Returns 500

First stop and restart the backend dev server. A stale `tsx watch` process can
keep old code alive after backend patches.

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
npm run build
npm run dev
```

If the backend terminal stack trace mentions `HealthController.health` and
`Cannot read properties of undefined (reading 'get')`, confirm the current code
uses explicit Nest injection in backend controllers/services.

### Mobile Cannot Reach Backend

For Android emulator:

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1
```

Then restart the Android app so Expo reloads `.env`.

### Desktop Cannot Reach Backend

For desktop:

```env
VITE_BACKEND_API_URL=http://localhost:4000/api/v1
```

Then restart the Vite/Tauri dev process.

## Validation Before Committing

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
npm run typecheck
npm run build
npm audit --omit=dev
```

Backend route boundary:

```powershell
cd C:\SoftwareProjects\TSEBP2025
rg -n -e "/model" -e "/separation" backend/src mobile-part/services mobile-part/context desktop/src/lib desktop/src/contexts
```

Expected result: no matches.
