# Semantic Noise Mixer - Mobile Testbed

This is a standalone **React Native (Expo)** testbed used to validate the on-device AI pipeline for the Semantic Noise Mixer project. It demonstrates recording audio, processing it using a TFLite model, and playing back the cleaned result.

> **Note**: This is a **Development Client** project. It uses native modules for AI inference (`react-native-fast-tflite`) and audio recording, meaning it **cannot** be run inside the standard "Expo Go" app. You must build the native binary.

---

## 🛠 Prerequisites

Before running the app, ensure you have the following installed:

1.  **Node.js** (LTS version recommended).
2.  **Android Studio** (for Android) or **Xcode** (for macOS/iOS).
3.  **Physical Device** recommended (Emulator microphone support can be flaky).
    *   **Android**: Enable Developer Options and USB Debugging.
    *   **iOS**: Requires a paid or free Apple Developer account for code signing.

---

## 🚀 Installation & Build

If you just received this code as a zip file, follow these steps in order:

### 1. Install Dependencies
Open a terminal in the `mobile-test` folder and run:
```bash
npm install
```

### 2. Generate Native Projects
Since the native code is excluded from the repository to keep it clean, you must regenerate the `android/` and `ios/` folders:
```bash
npx expo prebuild --clean
```

### 3. Run the App
Connect your device and run the appropriate command:

**For Android:**
```bash
npx expo run:android
```

**For iOS (Mac only):**
```bash
npx expo run:ios
```

---

## 📱 How to Use

The app provides a simple interface to test the AI suppression pipeline:

1.  **Record**: Press **"Record (5s)"**. Speak into the microphone or make some noise (like typing).
2.  **Listen to Raw**: Press **"Play Original"** to verify the recording worked.
3.  **Process**: The app automatically processes the audio through the TFLite model in the background after recording.
4.  **Listen to Clean**: Press **"Play Clean"** to hear the output of the AI suppression model.
    *   *Note: In this testbed, the output may sound muffled or different as it validates the pipeline stability rather than final audio quality.*

---

## 🏗 Architecture & Assets

*   **Models**: Located in `assets/models/`.
    *   `waveformer.tflite`: The core suppression engine (Native UNet architecture).
    *   `yamnet.tflite`: Used for semantic sound classification.
*   **Pipeline**:
    1.  **Capture**: `react-native-audio-record` captures 44.1kHz mono WAV.
    2.  **Inference**: `react-native-fast-tflite` runs the model on-device.
    3.  **Stitching**: Audio is processed in 3-second chunks and reassembled.
    4.  **Playback**: `expo-av` handles audio output.

---

## 📦 Sharing with Others

If you need to zip this project for a teammate:

1.  **Delete these folders first** (they are huge and will be regenerated):
    *   `node_modules/`
    *   `.expo/`
    *   `android/`
    *   `ios/`
2.  **Ensure these are included**:
    *   `assets/` (Critical: contains the `.tflite` models)
    *   `package.json`
    *   `app.json`
    *   `metro.config.js`
    *   All `.ts` and `.tsx` source files.

---

## ❓ Troubleshooting

*   **Silent Recording**: Ensure the app has Microphone permissions. On Android Emulator, check the "Extended Controls" -> "Microphone" settings to ensure the host mic is connected.
*   **Model Load Failure**: Check if `metro.config.js` includes `'tflite'` in the `assetExts` array.
*   **Build Errors**: Try running `npx expo prebuild --clean` to reset the native build state.
