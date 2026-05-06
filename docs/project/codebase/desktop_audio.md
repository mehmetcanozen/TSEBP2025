# Desktop Audio Runtime

The Windows desktop product is a Tauri app with a React frontend and a Rust
native audio/runtime layer. It supports offline jobs, live monitoring, Debug WAV
input, VB-CABLE virtual mic routing, and target-speaker workflows.

## Runtime Ownership

| Area | Main files | Responsibility |
| --- | --- | --- |
| Model/package resolution | `desktop/src-tauri/src/config.rs` | Read shared model manifests, resolve active package, locate artifacts and `onnxruntime.dll`. |
| Tauri commands | `desktop/src-tauri/src/commands.rs` | Expose categories, devices, metrics, jobs, live start/stop, and target-speaker APIs to React. |
| App state/jobs | `desktop/src-tauri/src/state.rs` | Hold shared engine, target-speaker runtime, speaker profiles, offline jobs, and live sessions. |
| Live audio | `desktop/src-tauri/src/audio/live.rs` | CPAL capture/render, Debug WAV source, ring buffers, lookahead, health metrics, and output routing. |
| Device detection | `desktop/src-tauri/src/audio/devices.rs` | Enumerate devices and identify VB-CABLE playback/recording roles. |
| Inference/DSP | `desktop/src-tauri/src/engine/` | ONNX Runtime execution, overlap/windowing, resampling, masking, direct residual suppression, and target-speaker support. |

## Active Semantic Runtime

Desktop resolves the active semantic model from `ai/models/model_selection.json`.
The current default is Waveformer:

```text
model_id: waveformer_edge_100ms
runtime_kind: onnx_streaming_target_extractor
sample_rate: 44100
chunk_samples: 4416
artifact: semantic_hearing_100ms_desktop.onnx
```

The streaming target-extractor path maintains recurrent state tensors and
subtracts the selected category estimate from the mixture. The desktop engine
also supports `onnx_category_separator` for packaged exact-category alternatives
such as AudioSepHive15Cat and CodecSepDNRv2 ONNX.

## Live Session Flow

```text
React state
    -> start_live_monitor Tauri command
    -> AppState creates a live session
    -> CPAL input device or Debug WAV source
    -> processing queue and lookahead buffer
    -> SharedEngine suppression
    -> CPAL output device
    -> status and meter events back to React
```

The live code tracks:

- queue depth and realtime health
- inference duration
- underruns and limiter behavior
- RMS/peak meters
- output mode and selected output device
- session lifecycle

The UI default lookahead is low-latency but intentionally buffered enough to
avoid unstable audio under CPU pressure.

## Debug WAV Source

Debug WAV mode replaces the physical microphone input with a WAV file while
still using the real live session path. This is the preferred repeatable demo
route because it exercises the same runtime, buffering, and output code as a
real microphone without depending on room noise.

Use it to validate category selectivity, for example:

```text
speech_barking.wav + category dog
speech_keyboard.wav + category computer_typing
```

## Monitor vs Virtual Mic

The desktop app has two output modes:

- Monitor: write processed audio to a normal playback device for local
  listening.
- Virtual Mic: write processed audio to the VB-CABLE playback endpoint so other
  apps can receive it as a microphone.

VB-CABLE naming is easy to reverse:

```text
App output sink: CABLE Input
Other app microphone source: CABLE Output
```

Virtual Mic mode should not overwrite the user's saved monitor output device.
The app chooses the VB-CABLE sink at live-start time when Virtual Mic is active.

## Target-Speaker Runtime

Target-speaker jobs use the `target_speaker_windows` package. TSExtract ONNX is
the default engine and requires both `tsextract_fp32.onnx` and
`tsextract_fp32.onnx.data`. ClearVoice is available only as an offline quality
fallback when its native bundle is present.

The desktop UI should block unsupported live combinations, especially ClearVoice
realtime and selecting the VB-CABLE recording endpoint as the live microphone.

## Fresh-Clone Checks

Before assuming desktop suppression logic is broken, verify the runtime DLL and
generated model artifacts. `ai/models/Exports` is ignored by Git, so these
model checks can fail after a clean clone or stale cleanup until the portable
`Exports` folder is present locally.

```powershell
Test-Path .\desktop\src-tauri\runtime\onnxruntime.dll
Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\source\semantic_hearing_100ms_source.onnx
Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\desktop\semantic_hearing_100ms_desktop.onnx
Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\desktop\semantic_hearing_100ms_desktop.onnx.json
Test-Path .\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\tsextract_onnx\tsextract_fp32.onnx
Test-Path .\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\tsextract_onnx\tsextract_fp32.onnx.data
Test-Path .\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\windows_bundle_manifest.json
```

If the Waveformer files are missing, restore the portable `ai/models/Exports`
folder before treating the desktop runtime as broken.

Also confirm VB-CABLE is installed and visible in Windows audio devices if
Virtual Mic mode is needed.

## Relevant Checks

For code changes, narrow verification usually starts with:

```powershell
cd desktop
npm test
npm run build

cd src-tauri
cargo test --lib
cargo check
```

For documentation-only changes, do not run these unless the docs need to verify
a live command or runtime behavior.
