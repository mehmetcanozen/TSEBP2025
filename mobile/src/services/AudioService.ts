/**
 * AudioService - Audio Recording and Playback
 * 
 * Handles:
 * - Audio recording with expo-audio
 * - Audio playback of processed results
 * - Audio permissions management
 * 
 * Note: Using expo-audio 1.1.0 API with useAudioPlayer hook
 */

import { useAudioPlayer } from "expo-audio";
import * as AudioModule from "expo-audio";
import AsyncStorage from "@react-native-async-storage/async-storage";

type AudioQuality = "high" | "medium" | "low";

class AudioService {
  private recordingUri: string | null = null;
  private currentRecording: any | null = null;
  private audioQuality: AudioQuality = "high";

  /**
   * Request audio permissions
   */
  async requestPermissions(): Promise<boolean> {
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) {
        console.warn("Audio permission denied");
        return false;
      }

      // Configure audio mode
      await AudioModule.setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });

      return true;
    } catch (error) {
      console.error("Failed to request audio permissions:", error);
      return false;
    }
  }

  /**
   * Load audio quality setting from AsyncStorage
   */
  async loadAudioQuality(): Promise<void> {
    try {
      const quality = (await AsyncStorage.getItem("audioQuality")) as AudioQuality;
      if (quality && ["high", "medium", "low"].includes(quality)) {
        this.audioQuality = quality;
      }
    } catch (error) {
      console.error("Failed to load audio quality:", error);
    }
  }

  /**
   * Get recording preset based on audio quality
   */
  private getRecordingPreset() {
    switch (this.audioQuality) {
      case "high":
        return AudioModule.RecordingPresets.HIGH_QUALITY;
      case "medium":
        return AudioModule.RecordingPresets.MEDIUM_QUALITY;
      case "low":
        return AudioModule.RecordingPresets.LOW_QUALITY;
      default:
        return AudioModule.RecordingPresets.HIGH_QUALITY;
    }
  }

  /**
   * Set audio quality
   */
  setAudioQuality(quality: AudioQuality): void {
    this.audioQuality = quality;
  }

  /**
   * Get current audio quality
   */
  getAudioQuality(): AudioQuality {
    return this.audioQuality;
  }

  /**
   * Start recording audio
   * Returns a promise that resolves when recording starts
   */
  async startRecording(): Promise<boolean> {
    try {
      // Load audio quality setting
      await this.loadAudioQuality();

      // Request permissions first
      const hasPermission = await this.requestPermissions();
      if (!hasPermission) {
        return false;
      }

      // Create recording instance
      const recording = new (AudioModule as any).Recording();

      // Prepare recording with quality-based preset
      const preset = this.getRecordingPreset();
      await recording.prepareToRecordAsync(preset);

      // Start recording
      await recording.startAsync();

      this.currentRecording = recording;

      console.log(`Recording started with ${this.audioQuality} quality`);
      return true;
    } catch (error) {
      console.error("Failed to start recording:", error);
      return false;
    }
  }

  /**
   * Stop recording and return audio URI
   */
  async stopRecording(): Promise<string | null> {
    try {
      if (!this.currentRecording) {
        console.warn("No active recording");
        return null;
      }

      await this.currentRecording.stopAndUnloadAsync();
      const uri = this.currentRecording.getURI();
      this.recordingUri = uri;
      this.currentRecording = null;

      console.log("Recording stopped:", uri);
      return uri;
    } catch (error) {
      console.error("Failed to stop recording:", error);
      return null;
    }
  }

  /**
   * Get the last recorded audio URI
   */
  getRecordingUri(): string | null {
    return this.recordingUri;
  }

  /**
   * Play audio from URI using expo-audio
   * Note: In components, use useAudioPlayer hook for better integration
   */
  async playSound(uri: string): Promise<boolean> {
    try {
      const sound = new (AudioModule as any).Sound();

      await sound.loadAsync({ uri });
      await sound.playAsync();

      // Auto cleanup after playback
      sound.setOnPlaybackStatusUpdate((status: any) => {
        if (status.isLoaded && status.didJustFinish) {
          sound.unloadAsync();
        }
      });

      console.log("Playback started:", uri);
      return true;
    } catch (error) {
      console.error("Failed to play sound:", error);
      return false;
    }
  }

  /**
   * Check if currently recording
   */
  isRecording(): boolean {
    return this.currentRecording !== null;
  }

  /**
   * Clean up resources
   */
  async cleanup(): Promise<void> {
    try {
      if (this.isRecording()) {
        await this.stopRecording();
      }
    } catch (error) {
      console.error("Cleanup failed:", error);
    }
  }
}

export default new AudioService();
