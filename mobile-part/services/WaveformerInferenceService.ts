/**
 * Waveformer Inference Service
 * 
 * Handles loading the Separation model and running inference.
 * Uses a TFLite-native UNet architecture to bypass Waveformer export issues.
 */

import { loadTensorflowModel, type TensorflowModel } from 'react-native-fast-tflite';

export class WaveformerInferenceService {
    private model: TensorflowModel | null = null;
    public isInitialized: boolean = false;

    // Waveformer specific constants
    private readonly SAMPLE_RATE = 44100; // Model trained/defined at 44.1kHz
    private readonly WINDOW_SIZE = 132300; // 3 seconds input window

    async initialize(): Promise<void> {
        if (this.isInitialized) return;
        try {
            console.log('[Waveformer] Loading model...');
            // Points to the native UNet architecture exported earlier
            const modelAsset = require('../assets/models/waveformer.tflite');
            this.model = await loadTensorflowModel(modelAsset);

            console.log('[Waveformer] Model loaded successfully');
            this.isInitialized = true;
        } catch (e) {
            console.error('[Waveformer] Failed to load model:', e);
            throw e;
        }
    }

    /**
     * Suppress noise from audio buffer using chunked inference.
     * Processes audio in 3-second blocks to match model window.
     * @param inputBuffer Float32Array (variable length)
     * @returns Processed audio of the same length
     */
    async suppress(inputBuffer: Float32Array, target: string = 'mix'): Promise<Float32Array> {
        if (!this.isInitialized || !this.model) {
            console.warn('[Waveformer] Model not ready, passing through');
            return inputBuffer;
        }

        console.log(`[Waveformer] Processing ${inputBuffer.length} samples with target: ${target}`);

        const outputBuffer = new Float32Array(inputBuffer.length);
        const chunkSize = this.WINDOW_SIZE;

        try {
            // Process in blocks of 132300 samples (3s @ 44.1kHz)
            for (let i = 0; i < inputBuffer.length; i += chunkSize) {
                const remaining = inputBuffer.length - i;
                const chunkInput = new Float32Array(chunkSize);

                // Copy data (pads with zeros if the last chunk is shorter than 3s)
                const copyLen = Math.min(remaining, chunkSize);
                chunkInput.set(inputBuffer.subarray(i, i + copyLen));

                // Log RMS for sanity check
                let sumSq = 0;
                for (let j = 0; j < chunkInput.length; j++) sumSq += chunkInput[j] * chunkInput[j];
                const rms = Math.sqrt(sumSq / chunkInput.length);
                console.log(`[Waveformer] Chunk at ${i}: RMS ${rms.toFixed(4)}`);

                // Run Inference (UNet architecture)
                const outputs = await this.model.run([chunkInput]);

                if (outputs && outputs.length > 0) {
                    const rawOutput = outputs[0] as Float32Array;
                    // Write back only the valid part of the output (trimming padding if last chunk)
                    const writeLen = Math.min(copyLen, rawOutput.length);
                    outputBuffer.set(rawOutput.subarray(0, writeLen), i);
                } else {
                    console.warn(`[Waveformer] No output for chunk at ${i}, falling back to original`);
                    outputBuffer.set(inputBuffer.subarray(i, i + copyLen), i);
                }
            }

            console.log('[Waveformer] Full buffer processed successfully');

        } catch (e) {
            console.error('[Waveformer] Chunked Inference Failed:', e);
            outputBuffer.set(inputBuffer);
        }

        return outputBuffer;
    }

    dispose() {
        this.model = null;
        this.isInitialized = false;
        console.log('[Waveformer] Model disposed');
    }
}

export const waveformerService = new WaveformerInferenceService();
