## React Native / Expo Mobile Deployment Guide

> **Goal**: Run the semantic noise suppression stack (YAMNet + Native UNet TFLite) on a React Native (Expo) app, using the `mobile-test` project as a reference implementation.

### 1. High-Level Architecture

- **App type**: React Native + Expo (TypeScript).
- **Audio capture & playback**:
  - `react-native-audio-record` for 44.1 kHz microphone recording.
  - `expo-av` for WAV playback (original vs. cleaned).
- **File & asset handling**:
  - `expo-file-system` for reading/writing audio files.
  - Raw `.tflite` models stored under `assets/models/`.
- **ML runtime**:
  - `react-native-fast-tflite` (JSI-based TFLite inference on-device).
- **Pipeline** (current validated design):
  1. Record N seconds of mic audio into a WAV file (44.1 kHz).
  2. Load the WAV into a `Float32Array`.
  3. Slice into fixed-length chunks (3s at 44.1 kHz).
  4. Run each chunk through TFLite model (Native UNet).
  5. Stitch outputs and save as a new WAV.
  6. Playback “Original” vs “Clean” audio for A/B comparison.

---

### 2. Project Scaffolding & Dependencies

#### 2.1 Base Expo project

- Create an Expo app (TypeScript):

```bash
npx create-expo-app mobile-app --template
cd mobile-app
```

#### 2.2 Core dependencies (validated in `mobile-test`)

Add these packages (matching what worked in `mobile-test/package.json`):

```bash
npm install \
  expo@~54.0.33 \
  react@19.1.0 \
  react-native@0.81.5 \
  expo-av@~16.0.8 \
  expo-file-system@~19.0.21 \
  react-native-audio-record@^0.2.2 \
  react-native-fast-tflite@^2.0.0 \
  buffer@^6.0.3

npm install --save-dev \
  typescript@~5.9.2 \
  @types/react@~19.1.0
```

**Notes / pitfalls**:

- **Expo SDK versions**: Keep Expo/React/React Native versions consistent (see `mobile-test/package.json`) to avoid native build issues.
- **Android focus first**: All validation was done on Android; iOS should work but was not fully exercised.

---

### 3. TFLite Model Assets

#### 3.1 Expected asset layout

- Place models under:

```text
mobile-app/
  assets/
    models/
      yamnet.tflite        # YAMNet for detection (optional for now)
      waveformer.tflite    # Native UNet TFLite (~514 KB)
```

- In `mobile-test`, `waveformer.tflite` is a **real TFLite model with a Native UNet architecture** exported from Python (no complex-number ops, TFLite-friendly).
- File paths in code use relative `require` paths like:
  - `require('../assets/models/waveformer.tflite')`

**Pitfall**: Incorrect asset paths (e.g. `../../assets` instead of `../assets`) will cause silent failures where the model never loads but the app still runs. Always verify the require path matches your folder structure.

#### 3.2 Model export summary (Python side)

- Export is done in Python via the `ai/export` package in the main repo:
  - `ai/export/export_onnx.py` for ONNX export.
  - `ai/export/export_tflite.py` for TFLite, using ONNX → TFLite tooling.
- **Key constraints that shaped the current model**:
  - Original Waveformer used complex STFT ops that are hard to convert to TFLite.
  - To avoid complex-number blockers, a **Native UNet** architecture was introduced and exported as `waveformer.tflite`.
  - Size is ~514 KB and runs successfully on-device via `react-native-fast-tflite`.

For mobile devs: you don’t need to re-export the model for basic integration tests; just consume the `.tflite` artifacts provided under `assets/models`. If you re-export in the future, keep to TFLite-safe ops (no complex tensors, avoid unsupported ONNX ops).

---

### 4. React Native Integration Details

#### 4.1 Metro configuration for `.tflite` assets

- Metro needs to treat `.tflite` as a static asset. In `mobile-test/metro.config.js` the pattern is:

```js
const { getDefaultConfig } = require('expo/metro-config');
const config = getDefaultConfig(__dirname);

config.resolver.assetExts.push('tflite');

module.exports = config;
```

**Pitfall**: If `.tflite` isn’t added to `assetExts`, bundling will fail or the model won’t be bundled, leading to runtime errors when loading via `require`.

#### 4.2 Loading the model (`react-native-fast-tflite`)

- The `WaveformerInferenceService.ts` in `mobile-test/services` demonstrates:
  - Loading the TFLite model once at startup.
  - Reusing the interpreter for multiple inferences.
  - Managing input/output buffers explicitly.

Core ideas:

- Use `react-native-fast-tflite` to:
  - Load:
    - `const model = await TfliteModel.fromAsset(require('../assets/models/waveformer.tflite'));`
  - Create an interpreter:
    - `const interpreter = new TfliteInterpreter(model);`
  - Allocate `Float32Array` buffers that match model input and output shapes.
  - Run inference:
    - `interpreter.run(inputBuffer, outputBuffer);`

**Pitfalls and fixes**:

- **Wrong tensor rank/shape**:
  - The model expects a fixed-length 3-second window at 44.1 kHz.
  - Use `(B, L, C) = (1, 132300, 1)` or the exact shape for your exported model.
  - Mismatched shapes will either throw errors or produce garbage output.
- **Multiple outputs confusion**:
  - Early attempts assumed 3 outputs; actual model had a single output tensor.
  - Fixed by reading only the single output and mapping it to a `Float32Array` correctly.

---

### 5. Audio Recording & Playback

#### 5.1 Recording with `react-native-audio-record`

- `mobile-test` uses `react-native-audio-record` for capturing mic input:
  - Configure for 44.1 kHz, mono.
  - Start/stop recording from UI buttons.
  - Output is a `.wav` file (path returned from the library).

**Pitfalls & learnings**:

- **Shorter-than-expected recordings**:
  - Initially, a “5 second” record produced shorter audio.
  - Root cause: mismatched sample rate assumptions across recording and processing.
  - Fix: Align everything to **44.1 kHz** and ensure timing logic uses sample counts, not just timers.

#### 5.2 File I/O and conversion

- Use `expo-file-system` to:
  - Read recorded WAV file bytes.
  - Convert bytes to `Float32Array` for ML input (see `utils/wavUtils.ts`).
  - Write processed samples back to a new WAV file.

Key design used in `mobile-test`:

- `utils/wavUtils.ts` contains helpers for:
  - Parsing WAV headers.
  - Extracting PCM samples as `Float32Array`.
  - Writing new WAV files from processed float data.

#### 5.3 Playback with `expo-av`

- Use `expo-av`’s `Audio.Sound` to:
  - Load the “original” WAV.
  - Load the “cleaned” WAV.
  - Provide simple UI actions:
    - “Play Original”
    - “Play Clean”

---

### 6. Processing Pipeline (Chunked Inference)

Because mobile devices can’t efficiently process arbitrarily long audio in a single pass, `mobile-test` uses **chunked processing**:

1. Convert entire recorded WAV to `Float32Array`.
2. Compute chunk size: `chunkSamples = 3 * 44100`.
3. For each 3-second block:
   - Extract a slice `inputChunk`.
   - Zero-pad the final chunk if shorter.
   - Run TFLite inference: `outputChunk`.
4. Concatenate all `outputChunk`s.
5. Write concatenated array to a new WAV as the “cleaned” audio.

**Benefits**:

- Handles arbitrary-length recordings while using a fixed-size TFLite model.
- Keeps memory usage bounded.

**Pitfalls & fixes**:

- **Muffled audio**:
  - Early versions produced “muffled” output due to:
    - Untrained weights (Native UNet with random weights).
    - Slight inconsistencies in scaling/normalization.
  - For production:
    - Train the UNet on noise-suppression tasks and export updated weights.
    - Ensure input audio is normalized consistently with training.
- **Length mismatch**:
  - Discrepancies between original and cleaned audio duration were solved by:
    - Keeping sample rate and chunk sizes consistent.
    - Avoiding off-by-one errors when slicing and stitching.

---

### 7. Hooks and Services Layout (`mobile-test`)

- `hooks/useSuppressionDemo.ts`:
  - Orchestrates:
    - Recording via `react-native-audio-record`.
    - Triggering processing via `WaveformerInferenceService`.
    - Managing UI state (idle, recording, processing, playing).
- `services/WaveformerInferenceService.ts`:
  - Encapsulates:
    - TFLite model loading.
    - Chunked inference logic.
    - Input/output buffer handling.
- `services/YAMNetInferenceService.ts` (optional for now):
  - Prototype for YAMNet-based classification on-device.
  - Not strictly required for the current record-process-play demo, but useful for future semantic control on mobile.

**Recommendation for production**:

- Keep ML runtime details fully encapsulated in `services/`.
- Keep UI logic in `hooks/` and `App.tsx`.
- Expose high-level API like:
  - `recordAndProcess(durationSeconds: number): Promise<{ originalPath: string; cleanPath: string }>`

---

### 8. Native / Expo Prebuild Steps

Working sequence validated in `mobile-test`:

```bash
# From mobile-test/ (or your app directory)
npm install
npx expo prebuild --clean --platform android
npx expo run:android
```

**Pitfalls & recoveries**:

- **Stale native build artifacts**:
  - Use `--clean` with `expo prebuild` when changing native modules (`react-native-fast-tflite`, audio libs, etc.).
- **Metro cache issues**:
  - If models or JS changes aren’t reflected:
    - `npx expo start -c` to clear Metro cache.
- **Gradle/Android issues**:
  - Keep `android/` directory under version control once stabilized.
  - When dependencies change, regenerate with `expo prebuild --clean` rather than hand-editing Gradle files.

---

### 9. Known Pitfalls and How We Solved Them

- **1. Complex-number Waveformer export to TFLite failed**:
  - Problem: Original Waveformer graph relied on complex STFT ops that current ONNX→TFLite toolchains couldn’t handle reliably.
  - Solution: Introduced a TFLite-friendly Native UNet model and exported it as `waveformer.tflite`. This is the model currently deployed in `mobile-test`.

- **2. Dummy models vs. “real” processing**:
  - Early attempts used trivial “dummy” models just to validate the pipeline, which produced no meaningful suppression.
  - Final approach uses a real UNet architecture so the pipeline exercises a legitimate deep network, even if current weights are not yet fully trained for noise suppression.

- **3. Wrong YAMNet indices for keyboard typing** (desktop, but relevant to semantics on mobile):
  - Initially used incorrect YAMNet indices (370/371) for typing.
  - Debugged by printing **all** YAMNet detections and discovered correct indices (e.g. 378, 380).
  - Lesson: When porting semantics to mobile, always verify class indices empirically, not just from docs.

- **4. Hardware pre-filtering hides noise**:
  - Some “smart” headsets heavily filter typing noise before the mic signal reaches the app.
  - Result: YAMNet (or mobile model) sees almost no keyboard content to suppress.
  - Lesson: On-device suppression can’t remove sounds that never reach the microphone; test with “dumb” mics when validating.

- **5. Mono vs. stereo mismatch**:
  - Desktop: errors like “index 1 is out of bounds” occurred when assuming stereo output on mono devices.
  - Mobile: similar care is needed—always check channel count, default to mono, and avoid hard-coded stereo assumptions.

- **6. Asset path mistakes and silent loading failures**:
  - Wrong `require` paths caused silent failure to load the `.tflite` file.
  - Fix: keep `assets/models` under the project root, and use short, well-tested relative paths.

- **7. Recording duration mismatch**:
  - UI said “5 seconds” but actual recorded WAV was shorter.
  - Fix: Consistently use 44.1 kHz everywhere and compute durations from sample counts.

---

### 10. How to Reuse `mobile-test` in the Real App

When you are ready to move from `mobile-test` into the real `mobile/` app:

1. **Copy structure**:
   - Replicate:
     - `hooks/useSuppressionDemo.ts`
     - `services/WaveformerInferenceService.ts`
     - `services/YAMNetInferenceService.ts` (optional)
     - `utils/wavUtils.ts`
   - Adjust import paths to match the real app’s folder layout.

2. **Copy assets**:
   - Copy `assets/models/waveformer.tflite` (and `yamnet.tflite` if needed).
   - Ensure `metro.config.js` in the real app is configured with `.tflite` in `assetExts`.

3. **Install identical dependencies**:
   - Mirror `mobile-test/package.json` dependency versions, or upgrade carefully and re-validate builds.

4. **Wire up UI**:
   - Use `useSuppressionDemo` (or a similar hook) to expose a simple UI with:
     - Record button (N seconds).
     - Play Original.
     - Play Clean.

5. **Gradual enhancement**:
   - Start with record-process-play offline flow (already validated).
   - Later, explore streaming / near-real-time suppression if required.

---

### 11. Quick Start Checklist (For Mobile Devs)

- **Android Emulator microphone access (if testing on an emulator)**
  - [ ] In Android Studio → **Device Manager** → select your AVD → **Edit** (pencil) → **Show Advanced Settings**:
    - Set **Microphone** / **Audio input** to **Virtual microphone uses host audio input** (wording varies by Android Studio version).
  - [ ] In the running emulator: open **Extended controls** (⋮) → **Microphone**:
    - Enable microphone input if there is a toggle.
    - Verify the emulator isn’t muted.
  - [ ] Inside the emulator: **Settings → Apps → <your app> → Permissions → Microphone → Allow**.
  - [ ] If recordings are silent:
    - Prefer a **physical device** (emulator mic support varies by host OS/driver and AVD image).
    - Try recreating the AVD or switching system images (Google APIs vs AOSP can differ).
    - Fully rebuild the dev client (`npx expo prebuild --clean --platform android` then `npx expo run:android`).

- **Environment**
  - [ ] Node + npm installed (2026 LTS).
  - [ ] Android SDK installed (Android Studio recommended).
  - [ ] Expo CLI installed globally (`npm install -g expo-cli` if needed).

- **Project Setup**
  - [ ] Clone repo and navigate to `mobile/` (or `mobile-test/` during experimentation).
  - [ ] Run `npm install`.
  - [ ] Ensure `metro.config.js` includes `tflite` in `assetExts`.

- **Models**
  - [ ] `assets/models/waveformer.tflite` present (~514 KB).
  - [ ] (Optional) `assets/models/yamnet.tflite` present (~4 MB).

- **Build & Run**
  - [ ] `npx expo prebuild --clean --platform android` succeeds.
  - [ ] `npx expo run:android` installs the app on a device/emulator.

- **Functional Test**
  - [ ] Can record 5+ seconds of audio without errors.
  - [ ] “Original” playback matches the spoken content.
  - [ ] “Clean” playback is generated (may sound muffled until trained weights are deployed).

Once all boxes are checked, the model deployment pipeline is working, and you can iterate on model quality (training, exporting new weights) without changing the React Native integration.

