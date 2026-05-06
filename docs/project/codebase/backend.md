# Shared Backend

The current shared backend lives in `backend/`. It replaces the old mobile-only
backend direction for current product work and gives both desktop and mobile
one account/profile/device/settings service.

The backend is deliberately not an audio runtime. It does not run suppression,
serve model files, distribute model bundles, or expose `/model/*` or
`/separation/*` APIs. Desktop and Android continue to execute suppression on
device from packaged artifacts.

## Technology Stack

| Layer | Current choice | Why it is used |
| --- | --- | --- |
| HTTP framework | NestJS with Express | Structured modules, guards, DTO validation, and a security-clean dependency baseline. |
| Database | PostgreSQL | Durable relational source of truth for users, devices, history metadata, and settings. |
| ORM | Prisma | Typed schema, migrations, generated client, and simple developer workflow. |
| Auth | Local dev auth or Supabase Auth | Local mode keeps development unblocked; Supabase mode is the shared environment path. |
| Deployment | Node process, Docker-ready | Runs without Docker first, but includes Docker files for later deployment. |

Fastify was intentionally not kept as the backend adapter after `npm audit`
reported a high-severity Fastify advisory through `@nestjs/platform-fastify`
with no available fix at the time of implementation. The current baseline uses
`@nestjs/platform-express` and audits cleanly.

## Source Layout

```text
backend/
|-- package.json
|-- .env.example
|-- Dockerfile
|-- compose.yaml
|-- prisma/
|   |-- schema.prisma
|   `-- migrations/
`-- src/
    |-- main.ts
    |-- app.module.ts
    |-- modules/
    |   |-- auth/
    |   |-- devices/
    |   |-- health/
    |   |-- history/
    |   `-- settings/
    `-- shared/
        |-- http/
        `-- prisma/
```

`main.ts` creates the Nest application, enables CORS, and installs the global
validation pipe. `app.module.ts` composes the feature modules and the shared
Prisma module.

## Modules

| Module | Important files | Responsibility |
| --- | --- | --- |
| `auth` | `auth.controller.ts`, `auth.service.ts`, DTOs, guard | Register, login, token refresh/logout, current user, profile update, password change. |
| `devices` | `devices.controller.ts`, `devices.service.ts` | Register/update desktop and mobile client metadata. |
| `history` | `history.controller.ts`, `history.service.ts` | Store optional processing history metadata. Audio files stay local unless a future explicit upload feature is added. |
| `settings` | `settings.controller.ts`, `settings.service.ts` | Store small user settings JSON. |
| `health` | `health.controller.ts` | Root and health checks. |
| `shared/prisma` | `prisma.service.ts` | Prisma client lifecycle. |

## API Boundary

Current API prefix:

```text
http://localhost:4000/api/v1
```

Current route families:

```text
GET  /health
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/logout
GET  /auth/me
PUT  /auth/profile
PUT  /auth/change-password
POST /devices/register
POST /history
GET  /history
DELETE /history
GET  /settings
PUT  /settings
```

Absent by design:

```text
/model/*
/separation/*
```

The absence of those routes is part of the project philosophy: model execution
and audio processing remain local in `desktop/`, `mobile-part/`, and `ai/`.

## Auth Modes

`AUTH_PROVIDER=local` is the development mode. The backend hashes passwords with
`bcryptjs`, issues local JWT access/refresh tokens, stores refresh-token hashes,
and rotates refresh tokens.

`AUTH_PROVIDER=supabase` is the shared-environment mode. The backend signs users
in through Supabase Auth, verifies Supabase access tokens, and mirrors the
profile identity into PostgreSQL so application data can still be related to a
local `users` row.

The clients do not talk to Supabase directly in the current implementation.
They call the shared backend and store the backend-returned access/refresh
tokens.

## Data Model

The Prisma schema defines:

| Model | Purpose |
| --- | --- |
| `User` | Auth identity mirror plus email, username, profile fields, flags, timestamps. |
| `RefreshToken` | Local-auth refresh token hashes, expiry, and revocation. |
| `UserDevice` | Desktop/mobile device id, platform, app version, last seen time. |
| `ProcessingHistory` | Optional metadata about completed app processing events. |
| `UserSettings` | Small per-user JSON settings document. |

The schema is intentionally small. Object storage, queues, Redis, model
artifact tables, and audio uploads are not required for the current backend.

## Client Wiring

Desktop uses `desktop/src/lib/backend-api.ts` and defaults to:

```text
http://localhost:4000/api/v1
```

Override with:

```env
VITE_BACKEND_API_URL=http://localhost:4000/api/v1
```

Android uses `mobile-part/services/api.ts` and defaults to:

```text
http://10.0.2.2:4000/api/v1
```

Override with:

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1
```

The Android emulator needs `10.0.2.2` because emulator `localhost` points to
the emulator itself.

## Operational Notes

- `backend/.env.example` is the template; real secrets stay in `backend/.env`.
- The backend does not have its own `.gitignore`; backend local artifacts are
  ignored from the repository root `.gitignore`.
- `compose.yaml` is optional. The service is Docker-ready, but the default
  development path can be a normal Node process against PostgreSQL.
- Before trusting a backend change, run `npm run typecheck`, `npm run build`,
  `npm audit --omit=dev`, and `npx prisma validate`.
