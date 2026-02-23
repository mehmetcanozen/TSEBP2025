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

## 3. Inverse Separation (Subtraction)
The "Clean" signal is calculated as:
`Clean = Original - (Extracted_Noise * Aggressiveness)`

*   **Aggressiveness**: A multiplier (default 1.0 - 1.5). Setting it to 1.5 allows the system to subtract more than what the model predicts, effectively creating a "safety margin" for noise removal at the cost of slight spectral artifacts.
*   **Phase Alignment**: Since Waveformer processes the same buffer used in the original mixture, the extracted noise stem is naturally phase-aligned, allowing for destructive interference (subtraction) without complex alignment logic.

## 4. Latency Management
- **Inference Latency**: Target < 50ms per model.
- **Buffer Latency**: 100ms (chunk size).
- **Total End-to-End**: ~150ms.
- **Optimization**: Lazy loading is used to ensure the first process call doesn't stall the audio loop.
