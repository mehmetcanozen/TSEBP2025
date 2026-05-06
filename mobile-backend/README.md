# Mobile Backend

FastAPI backend for mobile account, history, and device metadata.

The mobile suppression model is handled inside `mobile-part` by the native
Android `SuppressionEngine` and the bundled Android assets. This backend does
not expose model update, model download, or server-side separation endpoints.

## Architecture

```text
Mobile app
  |-- Auth, history, devices --> FastAPI backend --> database
  |
  `-- Suppression model/runtime --> bundled Android assets + native runtime
```

## Active Endpoints

Auth:

| Method | URL | Auth |
| --- | --- | --- |
| POST | `/auth/register` | No |
| POST | `/auth/login` | No |
| POST | `/auth/refresh` | No |
| POST | `/auth/logout` | No |
| GET | `/auth/me` | Yes |
| PUT | `/auth/change-password` | Yes |
| PUT | `/auth/profile` | Yes |

History:

| Method | URL | Auth |
| --- | --- | --- |
| POST | `/history` | Yes |
| GET | `/history?page=1&per_page=20` | Yes |
| DELETE | `/history` | Yes |

Devices:

| Method | URL | Auth |
| --- | --- | --- |
| POST | `/devices/register` | Yes |

System:

| Method | URL | Auth |
| --- | --- | --- |
| GET | `/health` | No |
| GET | `/` | No |

## Removed Model API Surface

These routes are intentionally not registered:

```text
GET /model/latest
GET /model/download/{version_id}
POST /model/upload
GET /model/versions
POST /separation/separate
```

Android model files live in the app bundle. The backend should not be required
for live suppression to prepare, load categories, start audio capture, or run
inference.

## Local Setup

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create `mobile-backend/.env` if needed:

```env
DATABASE_URL=sqlite:///./audioapp.db
SECRET_KEY=dev-local-secret-change-me
DEBUG=True
```

Run:

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

```text
http://localhost:8000/docs
```

## Tests

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-backend
python -m pytest tests -q
```
