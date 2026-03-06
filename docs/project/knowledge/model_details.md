# Model Details

The Semantic Noise Mixer leverages three distinct neural network architectures to achieve its goals.

## 1. Waveformer (Separation)
- **Purpose**: Time-domain audio separation.
- **Library**: `speechbrain`.
- **Target Logic**: Multi-target separation where each "noise" is an independent head.
- **Input Sample Rate**: 44.1 kHz.
- **Context Window**: 1.0 second.

## 2. YAMNet (Detection)
- **Purpose**: Multi-class audio event detection.
- **Source**: TensorFlow Hub (Pre-trained on AudioSet).
- **Classes**: 521 semantic categories.
- **Inference**: Runs on 0.975s chunks with a hop of 0.48s.
- **Output**: Probabilities across all classes, which are then mapped to the focus categories defined in `ai/ai_runtime/config`.

## 3. Native UNet (Mobile-Optimized)
- **Purpose**: Mobile-friendly noise suppression for the `mobile-test` app.
- **Constraint**: TFLite has limited support for complex numbers (STFT/ISTFT).
- **Architecture**: A fully-convolutional Native UNet that operates directly on time-domain waveform chunks.
- **Size**: ~514 KB.
- **Window**: 3.0 seconds (132,300 samples at 44.1 kHz).
- **Integration**: Deployed via `react-native-fast-tflite`.

## Normalization & Requirements
All models require input audio to be in **Float32 PCM** format in the range `[-1.0, 1.0]`. 
- **Desktop**: Normalization is handled in `semantic_suppressor.py`.
- **Mobile**: Normalization is handled in `WaveformerInferenceService.ts`.
