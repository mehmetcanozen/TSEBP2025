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
*   **Adaptive Stem Boosting**: Stems weaker than 30% of the mix are boosted by up to 4.5× when detection confidence ≥ 0.2. Under-extracted stems (ratio < 0.3) are scaled by up to 2× before masking.
*   **Decision-Directed Wiener Filter**: The boosted stems are summed and processed through an Ephraim-Malah mask. Transient categories (typing, pets) use shorter STFT (1024) and faster dd_alpha (0.92) for better time resolution.

`Clean = Original × DecisionDirectedWiener(Unwanted, Original)`

## 4. Latency Management
- **Inference Latency**: Target < 50ms per model.
- **Buffer Latency**: 100ms (chunk size).
- **Total End-to-End**: ~150ms.
- **Optimization**: Lazy loading is used to ensure the first process call doesn't stall the audio loop.
