# Audio Pipeline Deep Dive

The Semantic Noise Mixer uses a high-fidelity, low-latency pipeline designed for real-time interaction.

## 1. Rolling Context Buffer
Both YAMNet and Waveformer perform better when they have access to some audio history (context).
*   **Buffer Size**: 1.0 second (44,100 samples).
*   **Update Strategy**: As new 100ms chunks arrive from the microphone, the buffer is rolled, and the new data is appended.
*   **Inference**: Models process the full 1.0s buffer to provide a context-rich prediction for the latest 100ms.

## 2. Input Normalization
Deep learning models are sensitive to input amplitudes. Microphone levels vary wildly.
*   **Problem**: Quiet keyboards may be ignored if the signal-to-noise ratio is too low or if the absolute amplitude is near zero.
*   **Solution**: Before inference, the 1.0s buffer is normalized to a range of `[-1, 1]` based on its maximum absolute value.
*   **Inverse Scaling**: The separated noise stem is then de-normalized using the same scale factor before being subtracted from the original (non-normalized) chunk.

## 3. Per-Category Separation
Instead of combining all suppression targets into a single multi-hot Waveformer query (which allows loud sources to dominate quiet ones), each category receives its own dedicated Waveformer pass:

*   **Batched Inference**: Multiple query vectors are batched into a single GPU forward pass via `separate_multi_query()`, eliminating redundant preprocessing (resampling, device transfer).
*   **Adaptive Stem Boosting**: After separation, each stem's RMS energy is compared to the mix. Stems weaker than 10% of the mix are boosted by up to 4× to compensate for Waveformer's under-extraction of quiet sounds.
*   **Two-Stage Spectral Masking**: The boosted stems are summed and processed through a spectral ratio mask (Stage 1) and a targeted Wiener post-filter on noise-heavy bins (Stage 2).

`Clean = Original × SpectralMask(Unwanted, Original)`

## 4. Latency Management
- **Inference Latency**: Target < 50ms per model.
- **Buffer Latency**: 100ms (chunk size).
- **Total End-to-End**: ~150ms.
- **Optimization**: Lazy loading is used to ensure the first process call doesn't stall the audio loop.
