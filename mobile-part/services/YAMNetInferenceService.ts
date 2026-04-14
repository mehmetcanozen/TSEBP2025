/**
 * YAMNet Inference Service for React Native
 * 
 * Handles TFLite model loading and audio classification.
 */

import { loadTensorflowModel, type TensorflowModel } from 'react-native-fast-tflite';

// YAMNet class names (521 classes)
// For brevity, we'll load the top categories we care about
const SEMANTIC_CATEGORIES: Record<string, number[]> = {
    typing: [494, 495], // Computer_keyboard, Typing
    speech: [0, 1, 2],  // Speech, Male speech/man speaking, Female speech
    music: [137, 138],  // Music, Musical instrument
    // Add more as needed
};

export class YAMNetInferenceService {
    private model: TensorflowModel | null = null;
    private isInitialized: boolean = false;

    /**
     * Initialize YAMNet model from bundled asset
     */
    async initialize(): Promise<void> {
        try {
            console.log('[YAMNet] Loading model...');

            // For react-native-fast-tflite with Expo, we need to use a direct file path
            // The asset is bundled at build time by Metro
            // Use require() to get the asset module, then extract the file path
            const modelAsset = require('../assets/models/yamnet.tflite');

            console.log('[YAMNet] Model asset:', modelAsset);

            this.model = await loadTensorflowModel(modelAsset);

            console.log('[YAMNet] Model loaded successfully');
            console.log(`[YAMNet] Inputs: ${this.model.inputs.length}`);
            console.log(`[YAMNet] Outputs: ${this.model.outputs.length}`);

            // Log tensor shapes for debugging
            this.model.inputs.forEach((input, idx) => {
                console.log(`[YAMNet] Input[${idx}]: ${input.shape.join('x')} (${input.dataType})`);
            });

            this.model.outputs.forEach((output, idx) => {
                console.log(`[YAMNet] Output[${idx}]: ${output.shape.join('x')} (${output.dataType})`);
            });

            this.isInitialized = true;
        } catch (error) {
            console.error('[YAMNet] Failed to load model:', error);
            throw error;
        }
    }

    /**
     * Run inference on audio buffer
     * 
     * @param audioBuffer Float32Array of audio samples (16kHz mono)
     * @returns Classification scores for each category
     */
    async classify(audioBuffer: Float32Array): Promise<Record<string, number>> {
        if (!this.model || !this.isInitialized) {
            throw new Error('YAMNet model not initialized. Call initialize() first.');
        }

        try {
            // YAMNet expects specific input shape
            // Input: [batch_size, waveform_length] where waveform is 16kHz mono
            // For testing, we'll use a fixed window
            const inputLength = 15600; // ~0.975s at 16kHz
            const input = new Float32Array(inputLength);

            // Copy audio buffer (pad or truncate as needed)
            const copyLength = Math.min(audioBuffer.length, inputLength);
            input.set(audioBuffer.subarray(0, copyLength));

            // Run inference
            console.log('[YAMNet] Running inference...');

            // IMPORTANT: run() is async! We must await it.
            const outputs = await this.model.run([input]);

            console.log('[YAMNet] Inference run complete');

            // Debug logging
            console.log('[YAMNet] outputs type:', typeof outputs);
            console.log('[YAMNet] outputs isArray:', Array.isArray(outputs));

            // Check if outputs is valid
            if (!outputs) {
                throw new Error('Outputs is null/undefined');
            }

            // react-native-fast-tflite returns TypedArray[]
            const outputsLength = outputs.length;
            console.log('[YAMNet] outputs length:', outputsLength);

            if (outputsLength === undefined || outputsLength < 1) {
                throw new Error(`No output tensors returned (length=${outputsLength})`);
            }

            // Get the first (and only) output: 521 class probabilities
            const scores = outputs[0];
            // console.log('[YAMNet] scores:', scores); // Don't log full array, too big

            // Check if scores is iterable/array-like
            if (!scores) {
                throw new Error('scores tensor is undefined');
            }

            const scoresLen = (scores as any).length;
            console.log('[YAMNet] scores length:', scoresLen);

            // Handle both flattened and batched outputs safely
            let scoreArray: Float32Array | number[];

            if (scoresLen === 521) {
                scoreArray = scores as Float32Array;
            } else if ((scores as any)?.[0]?.length === 521) {
                console.log('[YAMNet] Detected batched output');
                scoreArray = (scores as any)[0] as Float32Array;
            } else {
                // Fallback attempt
                console.log('[YAMNet] Fallback score usage');
                scoreArray = (scoresLen === 521 ? scores : (scores as any)[0]) as Float32Array | number[];
            }

            if (!scoreArray || (scoreArray as any).length !== 521) {
                console.log('[YAMNet] Invalid scoreArray:', scoreArray);
                throw new Error(`Expected 521 scores, got ${(scoreArray as any)?.length || 0}`);
            }

            // Map to semantic categories
            const results: Record<string, number> = {};

            for (const [category, classIndices] of Object.entries(SEMANTIC_CATEGORIES)) {
                // Take max probability across all  indices for this category
                let maxScore = 0;
                for (const idx of classIndices) {
                    maxScore = Math.max(maxScore, scoreArray[idx]);
                }
                results[category] = maxScore;
            }

            return results;
        } catch (error) {
            console.error('[YAMNet] Inference failed:', error);
            throw error;
        }
    }

    /**
     * Cleanup resources
     */
    dispose(): void {
        if (this.model) {
            // react-native-fast-tflite handles cleanup automatically
            this.model = null;
            this.isInitialized = false;
            console.log('[YAMNet] Model disposed');
        }
    }
}

// Singleton instance
export const yamnetService = new YAMNetInferenceService();
