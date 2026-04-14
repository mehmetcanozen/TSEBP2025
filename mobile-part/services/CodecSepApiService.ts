/**
 * CodecSep API Service
 * 
 * Handles sending recorded audio to the local FastAPI server 
 * and retrieving the separated audio response.
 */

import * as FileSystem from 'expo-file-system/legacy';
import { Platform } from 'react-native';

export class CodecSepApiService {
    // For Android emulator, use 10.0.2.2 to access localhost of the host machine.
    // Ensure the FastAPI server is running with: uvicorn main:app --host 0.0.0.0 --port 8000
    private readonly API_URL = Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';

    public isInitialized: boolean = true; // API is always ready to accept requests

    async initialize(): Promise<void> {
        // Ping the server to check if it's alive
        try {
            console.log(`[CodecSepAPI] Pinging server at ${this.API_URL}...`);
            const response = await fetch(`${this.API_URL}/`);
            if (!response.ok) {
                console.warn('[CodecSepAPI] Server ping failed with status:', response.status);
            } else {
                console.log('[CodecSepAPI] Server is reachable!');
            }
        } catch (e) {
            console.error('[CodecSepAPI] Server ping failed. Ensure FastAPI is running.', e);
        }
    }

    /**
     * Sends the audio file to the backend and saves the response.
     * @param audioFileUri The local URI of the recorded audio file.
     * @param target The target separation class (e.g., 'typing', 'speech', 'music', 'noise')
     * @returns The local URI of the cleaned audio file downloaded from the server.
     */
    async suppress(audioFileUri: string, target: string = 'mix'): Promise<string> {
        console.log(`[CodecSepAPI] Sending file ${audioFileUri} with target: ${target} to server.`);
        
        try {
            const formData = new FormData();
            
            // Format URI for upload
            let uploadUri = audioFileUri;
            if (Platform.OS === 'android' && !uploadUri.startsWith('file://')) {
                uploadUri = 'file://' + uploadUri;
            }

            formData.append('file', {
                uri: uploadUri,
                name: 'audio.wav',
                type: 'audio/wav',
            } as any);

            formData.append('target', target);

            console.log(`[CodecSepAPI] Making POST request to ${this.API_URL}/separate`);
            const response = await fetch(`${this.API_URL}/separate`, {
                method: 'POST',
                body: formData,
                headers: {
                    'Accept': 'audio/wav',
                    'Content-Type': 'multipart/form-data',
                },
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server returned ${response.status}: ${errorText}`);
            }

            console.log(`[CodecSepAPI] Response received. Downloading clean audio...`);

            // Read the binary response as a blob and save it locally
            const blob = await response.blob();
            
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = async () => {
                    try {
                        const base64data = (reader.result as string).split(',')[1];
                        const docDir = (FileSystem as any).documentDirectory;
                        const outputPath = docDir + `clean_${Date.now()}.wav`;
                        
                        await FileSystem.writeAsStringAsync(outputPath, base64data, {
                            encoding: FileSystem.EncodingType.Base64,
                        });
                        
                        console.log(`[CodecSepAPI] Saved clean audio to: ${outputPath}`);
                        resolve(outputPath);
                    } catch (err) {
                        reject(err);
                    }
                };
                reader.onerror = (e) => reject(e);
                reader.readAsDataURL(blob);
            });

        } catch (e) {
            console.error('[CodecSepAPI] Processing failed:', e);
            throw e;
        }
    }

    dispose() {
        console.log('[CodecSepAPI] Service disposed');
    }
}

export const codecSepApiService = new CodecSepApiService();
