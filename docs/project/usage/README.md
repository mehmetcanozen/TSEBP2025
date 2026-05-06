# Usage guide index

This folder contains the operational runbooks for getting the project working.
Use this index instead of hunting through the root README.

## Recommended order

1. [Model artifacts](MODEL_ARTIFACTS.md)
   Restore the portable `ai/models/Exports` bundle and verify required files.
1. [Getting started](GETTING_STARTED.md)
   Prepare the local environment and choose a workflow.
1. [Python CLI](PYTHON_CLI.md)
   Run file-based suppression, semantic demos, and comparison backends.
1. [Desktop app](DESKTOP_APP.md)
   Run the Windows Tauri app, live monitor, Debug WAV, and target-speaker mode.
1. [Virtual mic](VIRTUAL_MIC.md)
   Route cleaned desktop audio into other Windows applications with VB-CABLE.
1. [Mobile app](MOBILE_APP.md)
   Run Android on-device suppression with the bundled Waveformer ORT model.
1. [Backend](BACKEND.md)
   Run the generic FastAPI backend for auth, history, and device records.
1. [Troubleshooting](TROUBLESHOOTING.md)
   Diagnose the common setup, model, audio, desktop, and Android failures.

## Reference docs

- [User manual](USER_MANUAL.md)
- [Mobile deployment reference](MOBILE_DEPLOYMENT.md)
- [Waveformer wide evaluation](WAVEFORMER_WIDE_EVAL.md)
- [Project documentation home](../README.md)

## Current product defaults

| Concern | Current answer |
| --- | --- |
| Default model | `waveformer_edge_100ms` |
| Desktop semantic model artifact | `ai/models/Exports/Waveformer/waveformer_edge_100ms/desktop/semantic_hearing_100ms_desktop.onnx` |
| Android semantic model artifact | `ai/models/Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort` |
| Desktop target-speaker artifact | `ai/models/Exports/TargetSpeakerWindows/target_speaker_windows_desktop/desktop/windows_bundle_manifest.json` |
| Mobile inference | On-device, bundled model, no backend suppression API |
| Backend role | Auth, history, devices |

Historical Native UNet, TFLite, old `WFExports`, and lowercase `exports`
references should not be treated as the current runtime.
