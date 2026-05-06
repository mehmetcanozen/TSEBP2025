# TSEBP2025 Shared Backend

This is the central backend for account, profile, device, history metadata, and settings sync across desktop and mobile.

It does not process audio, run suppression, expose model routes, or store model artifacts by default. Mobile and desktop suppression remain on device.

## Stack

- NestJS with Express
- PostgreSQL
- Prisma
- Supabase Auth in shared environments
- Local auth provider for development without a Supabase project
- Docker-ready, but not Docker-required

## Local Development Without Docker

Preferred repo-level setup:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\setup-backend-postgres.ps1 -PostgresPassword "<YOUR_POSTGRES_PASSWORD>"
.\shared\scripts\start-backend.ps1
```

The API listens on `http://localhost:4000/api/v1` by default.

Use script arguments instead of editing source when ports or client hosts differ:

```powershell
.\shared\scripts\start-backend.ps1 -BackendPort 4010
.\shared\scripts\start-backend.ps1 -MobileBackendHost "192.168.1.50"
.\shared\scripts\start-backend.ps1 -DesktopBackendUrl "http://localhost:4000/api/v1"
```

## Optional Docker Path

Docker is optional. The compose file is there for repeatable deployment or a quick Postgres container.

```powershell
cd C:\SoftwareProjects\TSEBP2025\backend
docker compose --profile db up -d
npm install
npm run prisma:generate
npm run db:migrate
npm run dev
```

For containerized API plus database:

```powershell
docker compose --profile all up --build
```

## Auth Modes

`AUTH_PROVIDER=local` is for development and automated checks.

`AUTH_PROVIDER=supabase` uses Supabase Auth. In that mode, configure:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- optionally `SUPABASE_JWT_SECRET` for legacy symmetric projects

Clients still call this backend. The backend returns/validates Supabase access tokens and mirrors profile metadata into Postgres.

## Boundary

The following routes are intentionally absent:

- `/model/*`
- `/separation/*`
- any route that uploads, downloads, or runs suppression models

Suppression and model execution stay local in `mobile-part` and `desktop`.
