/**
 * CodecSep API Service
 * 
 * Handles sending recorded audio to the local FastAPI server 
 * and retrieving the separated audio response.
 */

import * as FileSystem from 'expo-file-system/legacy';

export class CodecSepApiService {
    // API URL is read from EXPO_PUBLIC_API_URL env variable (.env file).
    // For emulator: http://10.0.2.2:8000
    // For physical device: http://<your-pc-wifi-ip>:8000  (e.g. http://192.168.1.50:8000)
    // Ensure the FastAPI server is running with: uvicorn main:app --host 0.0.0.0 --port 8000
    private readonly API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://192.168.1.50:8000';

    public isInitialized: boolean = true; // API is always ready to accept requests

    async initialize(): Promise<void> {
        // Ping the server to check if it's alive
        try {
            console.log(`[CodecSepAPI] Pinging server at ${this.API_URL}...`);
            const response = await fetch(`${this.API_URL}/`);
            if (response.ok) {
                console.log('[CodecSepAPI] Server is reachable!');
            }
        } catch (e) {
            console.error('[CodecSepAPI] Server ping failed.', e);
        }
    }

    /**
     * Sends the audio file to the backend using FileSystem.uploadAsync
     * @param audioFileUri The local URI of the recorded audio file.
     * @param target The target separation class
     * @returns The local URI of the cleaned audio file.
     */
    async suppress(audioFileUri: string, target: string = 'speech'): Promise<string> {
        console.log(`[CodecSepAPI] Uploading ${audioFileUri} (target: ${target}) to ${this.API_URL}/separation/separate`);
        
        try {
            // Using FileSystem.uploadAsync is much more robust for large files in React Native
            const uploadResult = await FileSystem.uploadAsync(
                `${this.API_URL}/separation/separate`,
                audioFileUri,
                {
                    fieldName: 'file',
                    httpMethod: 'POST',
                    uploadType: FileSystem.FileSystemUploadType.MULTIPART,
                    parameters: {
                        target: target
                    }
                }
            );

            if (uploadResult.status !== 200) {
                throw new Error(`Server returned ${uploadResult.status}: ${uploadResult.body}`);
            }

            const responseJson = JSON.parse(uploadResult.body);
            if (responseJson.status !== 'success' || !responseJson.url) {
                throw new Error('Upload succeeded but response format is invalid');
            }

            console.log(`[CodecSepAPI] Upload success. Downloading from: ${responseJson.url}`);

            const docDir = (FileSystem as any).documentDirectory;
            const outputPath = docDir + `clean_${Date.now()}.wav`;
            
            const downloadResult = await FileSystem.downloadAsync(
                `${this.API_URL}${responseJson.url}`,
                outputPath
            );

            if (downloadResult.status !== 200) {
                throw new Error(`Download failed with status: ${downloadResult.status}`);
            }

            console.log(`[CodecSepAPI] Clean audio downloaded to: ${outputPath}`);
            return outputPath;

        } catch (e) {
            console.error('[CodecSepAPI] Upload failed:', e);
            throw e;
        }
    }

    dispose() {
        console.log('[CodecSepAPI] Service disposed');
    }
}

export const codecSepApiService = new CodecSepApiService();
