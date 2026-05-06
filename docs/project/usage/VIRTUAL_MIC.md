# Virtual mic

Virtual Mic mode lets the desktop app send cleaned audio into another Windows
application as a microphone source. The project does not ship an audio driver.
For local development, use VB-CABLE.

## Install and identify VB-CABLE

Install VB-CABLE from:

```text
https://vb-audio.com/Cable/
```

Reboot if the installer asks for it. After installation, Windows should show:

```text
CABLE Input  - playback endpoint the desktop app writes cleaned audio into
CABLE Output - recording endpoint another app selects as its microphone
```

If VB-CABLE is not installed, offline rendering and Listen locally can still
work. Virtual Mic mode stays unavailable until the cable endpoints are detected.

## Choose how the target app receives the cable

There are two valid ways to make another app receive the cleaned stream:

1. If the target app has a microphone selector, choose
   `CABLE Output (VB-Audio Virtual Cable)` inside that app.
1. If the target app uses the Windows default microphone, make
   `CABLE Output` the Windows default recording device before starting the
   target app.

The Android emulator usually follows the second path because it uses the host
machine's microphone input.

## Set CABLE Output as the Windows default microphone

Use this when the receiving app does not expose a microphone picker, or when
testing with the Android emulator.

1. Open the classic Windows recording-device panel:

   ```powershell
   Start-Process control.exe -ArgumentList 'mmsys.cpl,,1'
   ```

1. In the Recording tab, write down your current default microphone so you can
   restore it later.
1. Find `CABLE Output (VB-Audio Virtual Cable)`.
1. If it is disabled, right-click it and choose Enable.
1. Right-click `CABLE Output (VB-Audio Virtual Cable)` and choose
   Set as Default Device.
1. Right-click it again and choose Set as Default Communication Device if that
   option is available.
1. Click Apply, then OK.
1. Restart or reopen the receiving app if it was already running.

After the test, restore your original microphone:

1. Open the Recording tab again:

   ```powershell
   Start-Process control.exe -ArgumentList 'mmsys.cpl,,1'
   ```

1. Right-click your real microphone.
1. Choose Set as Default Device.
1. Choose Set as Default Communication Device if needed.
1. Click Apply, then OK.

Do not set `CABLE Output` as the desktop app's input microphone. In Virtual Mic
mode, the desktop app should use a real microphone or Debug WAV source as input,
then write cleaned output into `CABLE Input`.

## Tested desktop route

```text
desktop Debug WAV mic source
-> desktop live suppression
-> CABLE Input
-> CABLE Output
-> target app microphone selection
```

This is the reliable one-machine test route. It does not require a second
virtual cable pair.

## Run the desktop app

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\start-backend.ps1
.\shared\scripts\start-desktop.ps1 -DevUi
```

Use the dev UI for this workflow because it exposes Debug WAV source controls,
transmission diagnostics, and routing details.

## Use the barking demo WAV

Set the desktop Debug WAV path to:

```text
C:\SoftwareProjects\TSEBP2025\ai\data\audio\raw\speech_barking.wav
```

Desktop live settings:

```text
Mode: Virtual mic
Clean audio sink: CABLE Input (VB-Audio Virtual Cable)
Debug WAV mic source: On
Debug WAV path: C:\SoftwareProjects\TSEBP2025\ai\data\audio\raw\speech_barking.wav
Category: dog
```

Start the session, then select this microphone in the receiving app:

```text
CABLE Output (VB-Audio Virtual Cable)
```

If the receiving app does not let you choose a microphone, set `CABLE Output`
as the Windows default recording device using the steps above before opening
that app.

## Android emulator route

Use this when testing the mobile app on the Windows Android emulator with a
desktop WAV or desktop Virtual Mic source.

```text
desktop cleaned output or Python feeder
-> CABLE Input
-> CABLE Output
-> Windows default recording device
-> Android emulator host microphone
-> mobile app live suppression
```

Steps:

1. Set `CABLE Output` as the Windows default recording device.
1. Open the Android emulator.
1. Open Extended Controls, then Microphone.
1. Enable host microphone input.
1. Start or restart the mobile app after the Windows default input is set.
1. Restore your real Windows microphone after the test.

## Python feeder for routing checks

The Python feeder plays a WAV into a virtual cable playback endpoint. It does
not run suppression. Use it only to confirm routing.

```powershell
cd C:\SoftwareProjects\TSEBP2025
python -m ai.scripts.demos.virtual_mic_streamer --list-devices
python -m ai.scripts.demos.virtual_mic_streamer --input C:\path\to\test.wav --device-name "CABLE Input"
```

## Troubleshooting

- Click Refresh devices in the desktop app after installing VB-CABLE.
- Confirm the receiving app uses `CABLE Output`, not `CABLE Input`.
- If the receiving app has no microphone picker, make `CABLE Output` the
  Windows default recording device before opening that app.
- Confirm the desktop output sink is `CABLE Input`.
- Do not use `CABLE Output` as the desktop app's live input unless you are using
  a separate virtual-cable pair for advanced loopback testing.
- Use category `dog` for the Waveformer barking sample.
- If no receiving app sees `CABLE Output`, check Windows Sound settings and
  make sure the VB-CABLE recording endpoint is enabled.
