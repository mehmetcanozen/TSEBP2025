# Backend Setup

This guide gets the shared backend running from a fresh checkout. It covers the
normal no-Docker app run first, then the optional Docker path.

The backend is only for app data: auth, profiles, settings, history metadata,
and device records. It is not needed for live suppression, model preparation,
or audio inference.

On Windows with PostgreSQL 18, use the hard-won exact runbook first:
[Backend Windows PostgreSQL runbook](BACKEND_WINDOWS_POSTGRES.md). It covers
`psql` PATH issues, pgAdmin-without-server confusion, manual `pg_ctl` startup,
the Turkish locale `initdb --locale=C` fix, Prisma migrations, and health
checks.

For the shortest maintained Windows path, run:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\setup-backend-postgres.ps1 -PostgresPassword "<YOUR_POSTGRES_PASSWORD>"
.\shared\scripts\start-backend.ps1
```

## 1. Prerequisites

Install these first:

- Node.js 22 or newer
- npm
- PostgreSQL 16 or newer
- Git and PowerShell

Optional:

- Docker Desktop, only if you want Docker to provide PostgreSQL or run the API
  container later.

Check the basics:

```powershell
node --version
npm --version
psql --version
```

If `psql` is not on PATH, you can still create the database with pgAdmin or the
PostgreSQL installer tools.

## 2. Install Backend Dependencies

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
npm install
```

This creates `backend/node_modules`, which is ignored by the root `.gitignore`.

## 3. Create The Database

Use an existing local PostgreSQL server if you have one.

```powershell
psql -U postgres -c "CREATE DATABASE tsebp2025;"
```

If the database already exists, PostgreSQL will report that; continue.

Optional Docker database only:

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
docker compose --profile db up -d
```

That starts a local Postgres container on port `5432` with:

```text
database: tsebp2025
user: postgres
password: postgres
```

## 4. Create backend/.env

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
Copy-Item .env.example .env
notepad .env
```

For the simplest local run, keep:

```env
NODE_ENV=development
PORT=4000
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/tsebp2025?schema=public
AUTH_PROVIDER=local
LOCAL_JWT_SECRET=replace-with-a-long-random-secret-at-least-32-chars
LOCAL_ACCESS_TOKEN_SECONDS=900
LOCAL_REFRESH_TOKEN_DAYS=30
```

Change `DATABASE_URL` if your local PostgreSQL user/password/port is different.

## 5. Generate Prisma And Run Migrations

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
npm run prisma:generate
npm run db:migrate
```

`prisma:generate` creates the typed Prisma client. `db:migrate` applies the
schema to PostgreSQL.

## 6. Start The Backend

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
npm run dev
```

Expected API base:

```text
http://localhost:4000/api/v1
```

Health check:

```powershell
Invoke-RestMethod http://localhost:4000/api/v1/health
```

Expected response shape:

```text
status       : ok
authProvider : local
```

## 7. Create A Test User

```powershell
$base = "http://localhost:4000/api/v1"

$registerBody = @{
  username = "test_user"
  full_name = "Test User"
  email = "test.user@example.com"
  password = "testpassword123"
} | ConvertTo-Json

Invoke-RestMethod "$base/auth/register" `
  -Method Post `
  -ContentType "application/json" `
  -Body $registerBody
```

Login:

```powershell
$loginBody = @{
  email = "test.user@example.com"
  password = "testpassword123"
} | ConvertTo-Json

$tokens = Invoke-RestMethod "$base/auth/login" `
  -Method Post `
  -ContentType "application/json" `
  -Body $loginBody

$tokens.access_token
```

Check current user:

```powershell
Invoke-RestMethod "$base/auth/me" `
  -Headers @{ Authorization = "Bearer $($tokens.access_token)" }
```

Register a desktop test device:

```powershell
$deviceBody = @{
  device_id = "manual-desktop-test"
  platform = "windows-desktop"
  app_version = "manual"
} | ConvertTo-Json

Invoke-RestMethod "$base/devices/register" `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $($tokens.access_token)" } `
  -Body $deviceBody
```

## 8. Point Desktop At The Backend

Desktop defaults to:

```text
http://localhost:4000/api/v1
```

Create an override only if needed:

```powershell
cd C:\SoftwareProjects\TSEBP2025\desktop
Copy-Item .env.example .env
notepad .env
```

Expected value:

```env
VITE_BACKEND_API_URL=http://localhost:4000/api/v1
```

Run desktop:

```powershell
cd C:\SoftwareProjects\TSEBP2025\desktop
npm install
npm run tauri:dev
```

Desktop auth/profile calls go to the shared backend. Desktop suppression,
VB-CABLE routing, and target-speaker processing still run locally.

## 9. Point Android At The Backend

Android emulator must use `10.0.2.2` to reach the Windows host.

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part
Copy-Item .env.example .env
notepad .env
```

Expected value:

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1
```

Run mobile:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part
npm install
npm run android
```

Mobile auth/profile/device calls go to the shared backend. Mobile suppression
and saved recordings remain on device.

## 10. Supabase Mode

Use this only when you have a Supabase project ready.

In `backend/.env`:

```env
AUTH_PROVIDER=supabase
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-publishable-or-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_AUDIENCE=authenticated
```

Then restart:

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
npm run dev
```

The desktop and mobile clients still call the shared backend. They do not need
to call Supabase directly for the current implementation.

## 11. Optional Docker API

Docker is not required for local development. It is available for deployment
readiness.

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
docker compose --profile all up --build
```

Use this only after `backend/.env` is configured.

## 12. Verification Commands

Run these before committing backend changes:

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
npm run typecheck
npm run build
npm audit --omit=dev
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/tsebp2025?schema=public"
npx prisma validate
```

Check that model and separation routes did not creep into the shared backend
clients:

```powershell
cd C:\SoftwareProjects\TSEBP2025
rg -n -e "/model" -e "/separation" backend/src mobile-part/services mobile-part/context desktop/src/lib desktop/src/contexts
```

Expected result: no matches.

## Common Problems

`P1001: Can't reach database server`

PostgreSQL is not running, the port is wrong, or `DATABASE_URL` has the wrong
credentials.

`Environment variable not found: DATABASE_URL`

You did not create `backend/.env`, or the current shell is not running from
`backend/`.

Android login cannot reach backend

Confirm the backend is running on Windows, then use:

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1
```

Desktop login cannot reach backend

Confirm:

```env
VITE_BACKEND_API_URL=http://localhost:4000/api/v1
```

Then restart the Vite/Tauri dev process so the env file is reloaded.
