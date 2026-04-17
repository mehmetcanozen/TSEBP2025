import { useState, useRef, useCallback, useEffect } from 'react';
import { Audio } from 'expo-av';
import AudioRecord from 'react-native-audio-record';
import { Buffer } from 'buffer';
import { waveformerService } from '../services/WaveformerInferenceService';
import { writeWavFile } from '../utils/wavUtils';
import * as FileSystem from 'expo-file-system';
import { Platform, PermissionsAndroid } from 'react-native';

interface UseSuppressionDemoResult {
    startDemo: () => Promise<void>;
    status: string;
    originalUri: string | null;
    cleanUri: string | null;
    playOriginal: () => Promise<void>;
    playClean: () => Promise<void>;
    isRecording: boolean;
    target: string;
    setTarget: (t: string) => void;
    debugInfo: string;
}

export const useSuppressionDemo = (): UseSuppressionDemoResult => {
    const [isRecording, setIsRecording] = useState(false);
    const [status, setStatus] = useState<string>('Idle');
    const [originalUri, setOriginalUri] = useState<string | null>(null);
    const [cleanUri, setCleanUri] = useState<string | null>(null);
    const [target, setTarget] = useState<string>('typing');
    const [debugInfo, setDebugInfo] = useState<string>('');

    // Buffers to hold recorded data
    const chunksRef = useRef<Float32Array[]>([]);
    const listenerRef = useRef<any>(null);

    // Fix FileSystem type if needed
    const docDir = (FileSystem as any).documentDirectory;

    const initRecorder = async () => {
        if (Platform.OS === 'android') {
            const granted = await PermissionsAndroid.request(
                PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
                {
                    title: 'Microphone Permission',
                    message: 'App needs mic access to demo suppression.',
                    buttonNeutral: 'Ask Me Later',
                    buttonNegative: 'Cancel',
                    buttonPositive: 'OK',
                },
            );
            if (granted !== PermissionsAndroid.RESULTS.GRANTED) {
                throw new Error('Permission denied');
            }
        }

        const options = {
            sampleRate: 44100, // Match model expected rate
            channels: 1,
            bitsPerSample: 16,
            audioSource: 6,
            wavFile: 'test.wav'
        };
        AudioRecord.init(options);
    };

    const startDemo = useCallback(async () => {
        try {
            console.log('Starting Demo...');
            setStatus('Initializing...');
            setDebugInfo('');
            chunksRef.current = [];
            setOriginalUri(null);
            setCleanUri(null);

            await initRecorder();

            // Initialize Waveformer TFLite model (on-device)
            setStatus('Loading AI model...');
            await waveformerService.initialize();

            // Start recording
            AudioRecord.start();
            setIsRecording(true);
            setStatus(`Recording (Target: ${target})...`);

            // Listen for data
            let packetCount = 0;
            listenerRef.current = AudioRecord.on('data', (data) => {
                packetCount++;
                if (packetCount % 10 === 0) console.log(`Received ${packetCount} packets`);

                // data is base64
                const buffer = Buffer.from(data, 'base64');
                // Convert int16 buffer to Float32
                const int16 = new Int16Array(buffer.buffer, buffer.byteOffset, buffer.length / 2);
                const float32 = new Float32Array(int16.length);
                for (let i = 0; i < int16.length; i++) {
                    float32[i] = int16[i] / 32768.0;
                }
                chunksRef.current.push(float32);
            });

            // Stop automatically after exactly 5 seconds
            setTimeout(async () => {
                await finishRecording();
            }, 5000);

        } catch (e: any) {
            console.error('Start failed', e);
            setStatus('Error: ' + e.message);
            setIsRecording(false);
        }
    }, [target]);

    const finishRecording = async () => {
        try {
            console.log('Stopping recording...');

            const filePath = await AudioRecord.stop();
            setIsRecording(false);
            setStatus('Processing...');

            console.log('Recording stopped. File:', filePath);

            // 1. Flatten Buffer
            const totalLen = chunksRef.current.reduce((acc, c) => acc + c.length, 0);
            setDebugInfo(`Captured ${totalLen} samples`);
            console.log(`Captured ${totalLen} samples`);

            if (totalLen === 0) {
                setStatus('Error: No audio captured.');
                return;
            }

            const audioData = new Float32Array(totalLen);
            let offset = 0;
            for (const c of chunksRef.current) {
                audioData.set(c, offset);
                offset += c.length;
            }

            setDebugInfo(`Samples: ${audioData.length}, Model Ready: ${waveformerService.isInitialized}`);

            // 2. Save original audio as WAV
            setStatus('Saving original recording...');
            const newOrigPath = docDir + 'original.wav';

            // AudioRecord filePath might not have file:// prefix on Android
            let sourcePath = filePath;
            if (Platform.OS === 'android' && !sourcePath.startsWith('file://')) {
                sourcePath = 'file://' + sourcePath;
            }
            await FileSystem.copyAsync({ from: sourcePath, to: newOrigPath });
            setOriginalUri(newOrigPath);

            // 3. Run Waveformer on-device inference
            setStatus(`Running Waveformer AI on device... (${target})`);
            console.log('[Demo] Running Waveformer suppress...');
            const cleanAudioData = await waveformerService.suppress(audioData, target);

            // 4. Save clean output as WAV
            setStatus('Saving processed audio...');
            const cleanOutputPath = docDir + 'clean_output.wav';
            await writeWavFile(cleanOutputPath, cleanAudioData, 44100);

            setCleanUri(cleanOutputPath);
            setStatus('Done. Ready to Play.');
            console.log('[Demo] Complete. Clean audio saved to:', cleanOutputPath);

        } catch (e: any) {
            console.error('Finish failed', e);
            setStatus('Error: ' + e.message);
            setIsRecording(false);
        }
    };

    const playOriginal = async () => {
        if (!originalUri) return;
        try {
            const { sound } = await Audio.Sound.createAsync({ uri: originalUri });
            await sound.playAsync();
        } catch (e) { console.error(e); }
    };

    const playClean = async () => {
        if (!cleanUri) return;
        try {
            const { sound } = await Audio.Sound.createAsync({ uri: cleanUri });
            await sound.playAsync();
        } catch (e) { console.error(e); }
    };

    return {
        startDemo,
        status,
        originalUri,
        cleanUri,
        playOriginal,
        playClean,
        isRecording,
        target,
        setTarget,
        debugInfo
    };
};
