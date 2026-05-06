/**
 * Historical Waveformer TFLite prototype service.
 *
 * The active Android runtime is the native SuppressionEngine backed by the
 * bundled `waveformer_edge_100ms` ONNX Runtime ORT artifact. The old TFLite
 * dependency has been removed from the mobile app, so this service is kept only
 * as a disabled compatibility stub for any stale imports during cleanup.
 */

export class WaveformerInferenceService {
  public isInitialized = false;

  async initialize(): Promise<void> {
    throw new Error(
      "WaveformerInferenceService is historical. Use SuppressionEngineService with the bundled Waveformer ORT runtime.",
    );
  }

  async suppress(inputBuffer: Float32Array): Promise<Float32Array> {
    return inputBuffer;
  }

  dispose(): void {
    this.isInitialized = false;
  }
}

export const waveformerService = new WaveformerInferenceService();
