# Backend

The current backend is the shared service in `backend/`. It is used by both
desktop and mobile for account/profile metadata and device registration.

It is not part of model delivery or audio suppression. Desktop and Android
continue to run suppression locally.

For a complete start-to-finish setup, use
[Backend setup](BACKEND_SETUP.md).

For the exact Windows/PostgreSQL 18 local cluster path that fixes `psql` PATH,
pgAdmin-without-server, `P1001`, and Turkish locale `initdb` failures, use
[Backend Windows PostgreSQL](BACKEND_WINDOWS_POSTGRES.md).

## Responsibilities

| Area | Backend role |
| --- | --- |
| Auth | Register, login, refresh, logout, current user |
| Profiles | Name, bio, local photo URI metadata |
| Devices | Register desktop/mobile client metadata |
| Settings | Store small user settings JSON |
| History | Optional processing-history metadata only |
| Models | None |
| Suppression inference | None |

The mobile and desktop apps should not call `/model/*` or `/separation/*`.

## Local development without Docker

Preferred Windows path:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\setup-backend-postgres.ps1 -PostgresPassword "<YOUR_POSTGRES_PASSWORD>"
.\shared\scripts\start-backend.ps1
```

The setup script creates the local PostgreSQL cluster/database when needed,
writes `backend/.env`, writes desktop/mobile API URLs, generates the Prisma
client, and applies migrations. After the one-time setup, normal starts are:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\start-backend.ps1
```

The API listens on:

```text
http://localhost:4000/api/v1
```

## Auth mode

For local development, use:

```env
AUTH_PROVIDER=local
```

For shared environments, use Supabase Auth:

```env
AUTH_PROVIDER=supabase
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-publishable-or-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

## Client URLs

Desktop uses:

```env
VITE_BACKEND_API_URL=http://localhost:4000/api/v1
```

Android emulator uses:

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1
```

Use `10.0.2.2` because emulator `localhost` points to the emulator itself, not
the Windows host.

## Optional Docker

Docker is ready but not required.

To use only Docker Postgres:

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
docker compose --profile db up -d
```

To run the backend and database in Docker:

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
docker compose --profile all up --build
```

## Boundary checks

```powershell
cd C:\SoftwareProjects\TSEBP2025
rg -n -e "/model" -e "/separation" backend/src mobile-part/services mobile-part/context desktop/src/lib desktop/src/contexts
```

Expected result: no mobile/desktop shared-backend client calls to model or
separation routes.
