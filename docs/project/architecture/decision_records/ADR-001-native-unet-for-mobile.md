# ADR 001: Native UNet For Mobile TFLite

## Status

Superseded.

This was a valid historical experiment, but it is not the current Android
product runtime. The current approach is documented in
[ADR 002: Shared Packaged Model Runtime](ADR-002-shared-packaged-model-runtime.md).

## Historical Context

The early mobile direction attempted to avoid complex STFT/ISTFT conversion
problems by exporting a small time-domain Native UNet to TFLite. At that time,
the project expected the mobile app to use `react-native-fast-tflite` and a
single `waveformer.tflite` style asset.

The motivation was reasonable:

- Waveformer-style complex-valued signal operations were hard to lower through
  ONNX-to-TFLite tooling.
- A time-domain convolutional model used TFLite-friendly operations.
- A small model was attractive for mobile latency and app packaging.

## Decision At The Time

The project created a lightweight Native UNet mobile path, intended to operate
directly on waveform chunks and avoid custom complex-number kernels.

## Why It Was Superseded

The product architecture later moved to shared model packages:

- `ai/models/model_selection.json` chooses the active model.
- Each `model_package.json` declares desktop and Android runtime contracts.
- Android Gradle generates a suppression model bundle from the active package.
- Native Android code supports ONNX Runtime and ExecuTorch runtime kinds.

The current default Android bundle is `waveformer_edge_100ms` using
`onnx_streaming_target_extractor`, not Native UNet/TFLite.

## Current Consequence

Do not use this ADR as implementation guidance for new mobile work. Keep it as
project history explaining why TFLite was explored and why stale docs may still
mention Native UNet.
