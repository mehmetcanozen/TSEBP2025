# Developer scripts

The scripts in `shared/scripts` wrap the repeated Windows/PowerShell commands
used during development. They are intentionally small launchers, not hidden
magic: each script prints the working directory, command, health check, and
important environment values before it runs.

Run them from the repo root unless noted:

```powershell
cd C:\SoftwareProjects\TSEBP2025
```

## Script summary

| Script | Purpose |
| --- | --- |
| `setup-backend-postgres.ps1` | One-time Windows PostgreSQL cluster/database/env/migration setup, including the `initdb --locale=C` fix. |
| `start-backend.ps1` | Start local PostgreSQL if needed, write client `.env` URLs, apply migrations, and run the shared backend. |
| `stop-postgres.ps1` | Stop the project-local PostgreSQL cluster cleanly through `pg_ctl`. |
| `start-desktop.ps1` | Check backend health, write `desktop/.env`, and launch the Tauri desktop app. |
| `start-mobile-android.ps1` | Configure Android SDK/ADB, write `mobile-part/.env`, prepare optional assets, and run the Android app. |
| `stream-loopback-wav.ps1` | Play a WAV into `CABLE Input` or another playback endpoint for VB-CABLE/mobile loopback testing. |
| `setup-ai-runtime.ps1` | Create or reuse the Python AI CLI environment with runtime/audio/export/training profiles. |
| `test-backend-api.ps1` | Exercise health, register, login, profile update, device registration, and logout. |
| `test-desktop.ps1` | Run desktop lint, tests, and build with readable logs. |
| `test-mobile-android.ps1` | Run mobile TypeScript plus optional Android asset/Kotlin/native/APK checks. |
| `test-dev-scripts.ps1` | Sequentially smoke-test the developer scripts, excluding one-time setup/stop-Postgres scripts. |
| `stop-port.ps1` | Stop the process listening on a given port, useful for stale backend or Metro sessions. |
| `setup_env.ps1` | Older heavy Python/AI environment bootstrap. Not needed for normal app startup. |

## AI CLI setup

Use this for the Python model-testing workspace under `ai/`:

```powershell
.\shared\scripts\setup-ai-runtime.ps1 -Profile runtime -UpgradePip
.\.venv\Scripts\Activate.ps1
python -m ai --help
python -m ai models list
python -m ai artifacts check --required-only
```

Profiles:

```powershell
# Minimal CLI and offline WAV suppression.
.\shared\scripts\setup-ai-runtime.ps1 -Profile runtime

# Adds sounddevice for VB-CABLE/audio endpoint streaming.
.\shared\scripts\setup-ai-runtime.ps1 -Profile audio-device

# Adds ONNX/ONNX Runtime dependencies.
.\shared\scripts\setup-ai-runtime.ps1 -Profile onnx

# Heavier export and training profiles.
.\shared\scripts\setup-ai-runtime.ps1 -Profile export
.\shared\scripts\setup-ai-runtime.ps1 -Profile training

# Install everything.
.\shared\scripts\setup-ai-runtime.ps1 -Profile all
```

Useful options:

```powershell
# Use a named Python executable.
.\shared\scripts\setup-ai-runtime.ps1 -Python "C:\Path\To\python.exe"

# Use a different venv path.
.\shared\scripts\setup-ai-runtime.ps1 -VenvPath .\.venv-ai

# Install into the active Python without creating .venv.
.\shared\scripts\setup-ai-runtime.ps1 -SkipVenv -Profile runtime
```

The script installs the editable root package so `tsebp-ai` becomes available
inside the environment. `python -m ai ...` is always the fallback when PATH is
not refreshed.

## Backend

### One-time PostgreSQL setup

Use this when setting up the backend on a fresh Windows machine, or after
deleting the local project database cluster. This wraps the painful manual path
from [Backend Windows PostgreSQL](BACKEND_WINDOWS_POSTGRES.md).

```powershell
.\shared\scripts\setup-backend-postgres.ps1 -PostgresPassword "<YOUR_POSTGRES_PASSWORD>"
```

What it does:

- verifies PostgreSQL tools under `C:\Program Files\PostgreSQL\18\bin`;
- initializes the local cluster at `C:\tmp\tsebp2025-postgres-18-data`;
- uses `initdb --locale=C` to avoid the Turkish Windows locale failure;
- starts PostgreSQL with `pg_ctl`;
- removes a stale `postmaster.pid` when `pg_ctl status` confirms the project
  cluster is not running;
- falls back to a timestamped PostgreSQL log file if the default log is locked;
- creates the `tsebp2025` database if it does not exist;
- writes/updates `backend/.env`;
- writes/updates `desktop/.env`;
- writes/updates `mobile-part/.env`;
- runs `npm install` for the backend if needed;
- runs `npm run prisma:generate`;
- runs `npm run db:deploy`.

Useful options:

```powershell
# Prompt for the password instead of putting it in the command history.
.\shared\scripts\setup-backend-postgres.ps1

# Setup and immediately start the backend dev server.
.\shared\scripts\setup-backend-postgres.ps1 `
  -PostgresPassword "<YOUR_POSTGRES_PASSWORD>" `
  -StartBackend

# Overwrite backend/.env from scratch with a fresh local JWT secret.
.\shared\scripts\setup-backend-postgres.ps1 `
  -PostgresPassword "<YOUR_POSTGRES_PASSWORD>" `
  -OverwriteBackendEnv

# If C:\tmp\tsebp2025-postgres-18-data exists but is not a valid cluster.
.\shared\scripts\setup-backend-postgres.ps1 `
  -PostgresPassword "<YOUR_POSTGRES_PASSWORD>" `
  -ForceRecreateInvalidDataDir

# Use a different PostgreSQL install/data path.
.\shared\scripts\setup-backend-postgres.ps1 `
  -PostgresPassword "<YOUR_POSTGRES_PASSWORD>" `
  -PostgresBin "C:\Program Files\PostgreSQL\18\bin" `
  -DataDir "C:\tmp\tsebp2025-postgres-18-data"

# Use a different backend port and write matching env files.
.\shared\scripts\setup-backend-postgres.ps1 `
  -PostgresPassword "<YOUR_POSTGRES_PASSWORD>" `
  -BackendPort 4010

# Use a physical Android device over Wi-Fi.
.\shared\scripts\setup-backend-postgres.ps1 `
  -PostgresPassword "<YOUR_POSTGRES_PASSWORD>" `
  -MobileBackendHost "192.168.1.50"

# Use a non-local PostgreSQL host or port.
.\shared\scripts\setup-backend-postgres.ps1 `
  -PostgresPassword "<YOUR_POSTGRES_PASSWORD>" `
  -PostgresHost "127.0.0.1" `
  -PostgresPort 5433

# Recover from a stale project PostgreSQL PID during setup.
.\shared\scripts\setup-backend-postgres.ps1 `
  -PostgresPassword "<YOUR_POSTGRES_PASSWORD>" `
  -ForceKillStalePostgres
```

The script removes the temporary password file after `initdb`. If you do not
want the password in PowerShell history, omit `-PostgresPassword` and enter it
at the secure prompt.

### Start backend

Start the validated local backend stack:

```powershell
.\shared\scripts\start-backend.ps1
```

What it does:

- starts PostgreSQL through `pg_ctl` if port `5432` is not listening;
- handles stale PostgreSQL PID files and locked PostgreSQL log files before
  startup;
- verifies the project-local data directory at
  `C:\tmp\tsebp2025-postgres-18-data`;
- creates `backend/.env` if it is missing;
- writes:
  - `desktop/.env` -> `VITE_BACKEND_API_URL=http://localhost:4000/api/v1`
  - `mobile-part/.env` -> `EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1`
- runs `npm run prisma:generate`;
- runs `npm run db:deploy`;
- starts `npm run dev`.

Leave this terminal open while desktop or mobile are running.

Useful options:

```powershell
# Backend is already running; just report health and exit.
.\shared\scripts\start-backend.ps1

# Restart if port 4000 is occupied by a stale process.
.\shared\scripts\start-backend.ps1 -ForceRestart

# Recover from a stale project PostgreSQL PID when pg_ctl says the cluster is
# not healthy but a leftover postgres.exe still exists. Use only for the
# project-local C:\tmp\tsebp2025-postgres-18-data cluster.
.\shared\scripts\start-backend.ps1 -ForceKillStalePostgres

# Start backend without touching desktop/mobile .env files.
.\shared\scripts\start-backend.ps1 -SkipClientEnv

# Skip Prisma generation and migration for a quick restart.
.\shared\scripts\start-backend.ps1 -SkipPrismaGenerate -SkipMigrations

# Use a different PostgreSQL install or data directory.
.\shared\scripts\start-backend.ps1 `
  -PostgresBin "C:\Program Files\PostgreSQL\18\bin" `
  -DataDir "C:\tmp\tsebp2025-postgres-18-data"

# Use a different backend port and write matching desktop/mobile client URLs.
.\shared\scripts\start-backend.ps1 -BackendPort 4010

# Use a LAN IP for a physical Android device on the same Wi-Fi network.
.\shared\scripts\start-backend.ps1 -MobileBackendHost "192.168.1.50"

# Use a full custom mobile URL if host, scheme, port, or path are unusual.
.\shared\scripts\start-backend.ps1 -MobileBackendUrl "http://192.168.1.50:4000/api/v1"

# Use a non-local PostgreSQL host or port.
.\shared\scripts\start-backend.ps1 -PostgresHost "127.0.0.1" -PostgresPort 5433
```

If this script says the data directory is not initialized, use
[Backend Windows PostgreSQL](BACKEND_WINDOWS_POSTGRES.md) or run:

```powershell
.\shared\scripts\setup-backend-postgres.ps1 -PostgresPassword "<YOUR_POSTGRES_PASSWORD>"
```

### Stop PostgreSQL

Usually you can leave PostgreSQL running. To stop the project-local cluster
cleanly:

```powershell
.\shared\scripts\stop-postgres.ps1
```

Useful options:

```powershell
.\shared\scripts\stop-postgres.ps1 -Mode fast
.\shared\scripts\stop-postgres.ps1 -Mode smart
.\shared\scripts\stop-postgres.ps1 -DataDir "C:\tmp\tsebp2025-postgres-18-data"
```

## Backend API smoke test

With the backend running:

```powershell
.\shared\scripts\test-backend-api.ps1
```

This creates a throwaway test user and verifies:

- `/health`
- `/auth/register`
- `/auth/login`
- `/auth/me`
- `/auth/profile`
- `/devices/register`
- `/auth/logout`

Useful options:

```powershell
# Test a non-default backend URL.
.\shared\scripts\test-backend-api.ps1 -BaseUrl "http://localhost:4000/api/v1"

# Register the smoke device as Android instead of desktop.
.\shared\scripts\test-backend-api.ps1 -Platform "android"
```

## Desktop

Start the desktop app after the backend is running:

```powershell
.\shared\scripts\start-desktop.ps1
```

What it does:

- writes `desktop/.env`;
- writes `VITE_DESKTOP_UI_SURFACE=user` by default;
- checks backend health at `http://localhost:4000/api/v1/health`;
- adds Cargo to the current terminal PATH when available;
- installs npm packages if `desktop/node_modules` is missing;
- runs `npm run tauri:dev`.

Useful options:

```powershell
# Run desktop checks before launch.
.\shared\scripts\start-desktop.ps1 -RunChecks

# Launch Vite web UI only, without Tauri.
.\shared\scripts\start-desktop.ps1 -WebOnly

# Launch the full dev/debug UI instead of the clean user UI.
.\shared\scripts\start-desktop.ps1 -DevUi

# Launch the dev/debug UI in Vite-only mode.
.\shared\scripts\start-desktop.ps1 -WebOnly -DevUi

# Only update desktop/.env, useful for script smoke checks.
.\shared\scripts\start-desktop.ps1 -WriteEnvOnly

# Use another backend URL.
.\shared\scripts\start-desktop.ps1 -BackendUrl "http://localhost:4000/api/v1"

# Skip backend health check for UI-only debugging.
.\shared\scripts\start-desktop.ps1 -SkipBackendCheck
```

Desktop UI surface rules:

- default script launch: `VITE_DESKTOP_UI_SURFACE=user`
- `-DevUi`: `VITE_DESKTOP_UI_SURFACE=dev`
- URL query override: `?ui=user` or `?ui=dev`
- user UI hides Debug WAV, Transmission Test, Loopback Monitor, and raw runtime diagnostics
- dev UI keeps the full diagnostics in modular Semantic Debug, Speaker Debug,
  Transmission, and Runtime/Devices panels

Run desktop checks without launching:

```powershell
.\shared\scripts\test-desktop.ps1
```

Useful options:

```powershell
.\shared\scripts\test-desktop.ps1 -SkipLint
.\shared\scripts\test-desktop.ps1 -SkipTests
.\shared\scripts\test-desktop.ps1 -SkipBuild
```

## Mobile Android

Start Android with the shared backend:

```powershell
.\shared\scripts\start-mobile-android.ps1
```

What it does:

- sets `NODE_ENV=development`;
- sets `ANDROID_HOME` and `ANDROID_SDK_ROOT`;
- adds Android platform-tools and emulator tools to PATH;
- writes `mobile-part/.env` with
  `EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1`;
- checks for an ADB-ready emulator/device;
- runs `adb reverse tcp:8081 tcp:8081` for Metro;
- installs npm packages if `mobile-part/node_modules` is missing;
- runs `npm run android`.

Useful options:

```powershell
# Start the known local emulator if none is connected.
.\shared\scripts\start-mobile-android.ps1 -StartEmulator

# Use a different AVD.
.\shared\scripts\start-mobile-android.ps1 -StartEmulator -AvdName "Medium_Phone_API_36.1"

# Rebuild Android bundled suppression assets before launching.
.\shared\scripts\start-mobile-android.ps1 -PrepareAssets

# Remove the currently installed development app before running.
.\shared\scripts\start-mobile-android.ps1 -CleanInstall

# For a physical USB device, reverse backend port and use localhost in the app.
.\shared\scripts\start-mobile-android.ps1 -UseAdbReverseBackend

# For a physical device on the same Wi-Fi network, use your Windows host LAN IP.
.\shared\scripts\start-mobile-android.ps1 -BackendHost "192.168.1.50"

# Use a different backend port.
.\shared\scripts\start-mobile-android.ps1 -BackendPort 4010

# Use a full custom backend URL.
.\shared\scripts\start-mobile-android.ps1 -BackendUrl "http://192.168.1.50:4000/api/v1"

# Target one connected device explicitly.
.\shared\scripts\start-mobile-android.ps1 -DeviceId "emulator-5554"
```

For Android emulator, the default backend URL is `10.0.2.2` because that is how
the emulator reaches the Windows host. For physical USB devices,
`-UseAdbReverseBackend` is usually easier. For physical devices over Wi-Fi, pass
`-BackendHost` or `-BackendUrl`; do not edit the script source.

Run mobile build checks without launching:

```powershell
.\shared\scripts\test-mobile-android.ps1
```

Useful options:

```powershell
# Include a full debug APK build.
.\shared\scripts\test-mobile-android.ps1 -FullApk

# Fast TypeScript-only check.
.\shared\scripts\test-mobile-android.ps1 -SkipAssets -SkipKotlin -SkipNative

# Skip native/CMake work when debugging JS-only changes.
.\shared\scripts\test-mobile-android.ps1 -SkipNative
```

## Loopback WAV / VB-CABLE feeder

List playback devices:

```powershell
.\shared\scripts\stream-loopback-wav.ps1 -ListDevices
```

Stream the default barking sample into `CABLE Input`:

```powershell
.\shared\scripts\stream-loopback-wav.ps1
```

Equivalent manual route:

```text
speech_barking.wav
-> CABLE Input
-> CABLE Output
-> Windows default recording device or target app microphone
```

Useful options:

```powershell
# Use the exact device ID from -ListDevices.
.\shared\scripts\stream-loopback-wav.ps1 -DeviceId 19

# Use a custom WAV and endpoint name.
.\shared\scripts\stream-loopback-wav.ps1 `
  -InputPath "C:\path\to\test.wav" `
  -DeviceName "CABLE Input"

# Play once instead of looping.
.\shared\scripts\stream-loopback-wav.ps1 -Once

# Use a specific Python executable.
.\shared\scripts\stream-loopback-wav.ps1 `
  -Python "C:\Users\omehm\anaconda3\envs\codecsep_audio_train\python.exe"
```

If the script reports missing `sounddevice`, install it into the Python you are
using:

```powershell
python -m pip install sounddevice
```

This feeder does not clean audio. It only proves that Windows, VB-CABLE, and
the receiving app can hear the WAV route.

The script is a PowerShell wrapper around the AI CLI:

```powershell
python -m ai stream wav --list-devices
python -m ai stream wav `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --device-name "CABLE Input" `
  --once
```

## Stop a stuck port

Use this when backend or Metro is already running but you want a clean start.

```powershell
.\shared\scripts\stop-port.ps1 -Port 4000
.\shared\scripts\stop-port.ps1 -Port 8081
```

The script prints the PID and process name before stopping it.

## Test the scripts

To smoke-test the developer scripts sequentially:

```powershell
.\shared\scripts\test-dev-scripts.ps1 -StartEmulator
```

This intentionally excludes:

```text
setup-backend-postgres.ps1
stop-postgres.ps1
```

The test script:

- parses the PowerShell scripts;
- checks `stop-port.ps1` against an unused port;
- runs desktop wrapper checks without heavy lint/test/build;
- runs mobile TypeScript-only checks;
- smoke-tests `python -m ai --help`, `models list`, and required artifact checks;
- lists loopback audio devices;
- starts backend and probes `http://127.0.0.1:4000/api/v1/health`;
- smoke-tests backend API auth/profile/device/logout;
- starts desktop in Vite web-only mode and probes `http://127.0.0.1:8080`;
- starts Android/mobile when not skipped.

Long-running launch scripts are started in hidden child processes during this
test. Their stdout/stderr logs are written to:

```text
shared/scripts/.script-test-logs/
```

If a launch probe fails, the script prints the relevant log tail before it
exits, so you do not need to paste a custom debug harness.

Useful options:

```powershell
# Fast script test without launching long-running dev servers.
.\shared\scripts\test-dev-scripts.ps1 `
  -SkipBackendLaunch `
  -SkipDesktopLaunch `
  -SkipMobileLaunch

# Test backend and desktop but skip Android.
.\shared\scripts\test-dev-scripts.ps1 -SkipMobileLaunch

# If the desktop Vite port changes, override the probe port.
.\shared\scripts\test-dev-scripts.ps1 `
  -SkipMobileLaunch `
  -DesktopWebPort 8080

# Test backend and allow recovery from a stale project PostgreSQL PID.
.\shared\scripts\test-dev-scripts.ps1 `
  -SkipDesktopLaunch `
  -SkipMobileLaunch `
  -ForceKillStalePostgres

# Test Android using an already-open emulator/device.
.\shared\scripts\test-dev-scripts.ps1
```

The script uses `127.0.0.1` for internal health probes because PowerShell HTTP
calls on Windows can occasionally stall on `localhost`/IPv6 even when the
server is reachable on IPv4. App `.env` files still use the normal project URLs.

## Common workflows

Desktop with backend:

```powershell
# Terminal 1
.\shared\scripts\start-backend.ps1

# Terminal 2
.\shared\scripts\start-desktop.ps1
```

Mobile emulator with backend:

```powershell
# Terminal 1
.\shared\scripts\start-backend.ps1

# Terminal 2
.\shared\scripts\start-mobile-android.ps1 -StartEmulator
```

Mobile loopback audio using VB-CABLE:

```powershell
# Terminal 1
.\shared\scripts\start-backend.ps1

# Terminal 2
.\shared\scripts\start-mobile-android.ps1 -StartEmulator

# Terminal 3
.\shared\scripts\stream-loopback-wav.ps1
```

Before mobile loopback, set `CABLE Output` as the Windows default recording
device and enable host microphone input in the Android emulator. See
[Virtual mic](VIRTUAL_MIC.md).
