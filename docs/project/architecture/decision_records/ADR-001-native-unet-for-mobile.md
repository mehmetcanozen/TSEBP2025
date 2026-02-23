# ADR 001: Native UNet implementation for Mobile TFLite

## Status
Approved

## Context
The primary desktop model (Waveformer) uses complex-valued STFT/ISTFT operations for signal processing. While efficient on desktop GPUs, these operations present significant hurdles for mobile deployment:
1.  **TFLite Compatibility**: Standard TFLite kernels do not support complex tensors natively without custom ops or complex mapping configurations.
2.  **ONNX to TFLite Conversion**: Toolchains like `onnx2tf` struggle with high-order complex number graphs.
3.  **Performance**: Near-real-time STFT on mobile processors incurs significant overhead.

## Decision
We decided to implement a **Native UNet** architecture specifically for the mobile pipeline (`mobile-test`). 
- The model operates directly in the **time-domain**.
- It uses standard 1D convolutional layers, Skip Connections, and Max Pooling.
- It omits any complex-number math.

## Consequences
- **Positive**: The model is extremely lightweight (~514 KB) and runs reliably on Android via `react-native-fast-tflite`.
- **Positive**: Simplified export pipeline (ONNX -> TFLite) without custom C++ kernels.
- **Neutral**: The UNet requires a larger 3-second context window to compensate for the lack of frequency-domain features.
- **Negative**: Current weights are less performant than the full Waveformer model; requires dedicated training on the mobile dataset.
