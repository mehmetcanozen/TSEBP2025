/**
 * Historical YAMNet TFLite prototype service.
 *
 * The current mobile product path does not run YAMNet or TensorFlow Lite.
 * Suppression is handled on device by the native SuppressionEngine and the
 * bundled Waveformer ORT model. This stub keeps stale imports fail-safe without
 * carrying the old TFLite native dependency.
 */

export class YAMNetInferenceService {
  async initialize(): Promise<void> {
    throw new Error(
      "YAMNetInferenceService is historical. Use the native SuppressionEngine bundled-model runtime.",
    );
  }

  async classify(): Promise<Record<string, number>> {
    throw new Error(
      "YAMNetInferenceService is historical. Use the native SuppressionEngine bundled-model runtime.",
    );
  }

  dispose(): void {
    // No native resources are held by the historical stub.
  }
}

export const yamnetService = new YAMNetInferenceService();
