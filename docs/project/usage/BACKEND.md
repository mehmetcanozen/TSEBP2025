# Backend

The mobile backend is a generic FastAPI service for application data. It is not
part of model delivery or audio suppression.

## Responsibilities

| Area | Backend role |
| --- | --- |
| Auth | Register, login, and current-user APIs |
| History | Store and fetch app history records |
| Devices | Register and manage device metadata |
| Models | None |
| Suppression inference | None |

The Android app should not call `/model/*` or `/separation/*` for the current
product path.

## Environment file

Create `mobile-backend/.env` for local development:

```env
DATABASE_URL=sqlite:///./audioapp.db
SECRET_KEY=dev-local-secret-change-me
DEBUG=True
```

## Install and run

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

```text
http://localhost:8000/docs
http://localhost:8000/
```

## Android emulator URL

For the mobile app running in the Android emulator:

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000
```

Use `10.0.2.2` because emulator `localhost` points to the emulator itself, not
the Windows host.

## Boundary checks

Run backend tests from `mobile-backend`:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-backend
python -m pytest tests -q
```

Optional static check from the repository root:

```powershell
cd C:\SoftwareProjects\TSEBP2025
rg -n "/model|/separation|model download|download model" mobile-part mobile-backend
```

Expected result: backend tests may mention absent `/model` or `/separation`
routes as negative coverage, but mobile app runtime code should not depend on
those routes.
