import { create } from "zustand";

export interface DetectionResult {
  speech: number;
  noise: number;
  events: number;
}

export interface AudioState {
  // Recording state
  isRecording: boolean;
  isProcessing: boolean;
  recordingDuration: number;

  // Gain controls
  speechGain: number;
  noiseGain: number;
  eventsGain: number;

  // Detection results
  detections: DetectionResult;

  // Mode
  isAutoMode: boolean;

  // Actions
  setRecording: (isRecording: boolean) => void;
  setProcessing: (isProcessing: boolean) => void;
  setRecordingDuration: (duration: number) => void;
  setSpeechGain: (gain: number) => void;
  setNoiseGain: (gain: number) => void;
  setEventsGain: (gain: number) => void;
  setDetections: (detections: DetectionResult) => void;
  setAutoMode: (isAuto: boolean) => void;
  resetGains: () => void;
}

export const useAudioStore = create<AudioState>((set) => ({
  isRecording: false,
  isProcessing: false,
  recordingDuration: 0,
  speechGain: 1.0,
  noiseGain: 0.0,
  eventsGain: 0.5,
  detections: { speech: 0, noise: 0, events: 0 },
  isAutoMode: true,

  setRecording: (isRecording) => set({ isRecording }),
  setProcessing: (isProcessing) => set({ isProcessing }),
  setRecordingDuration: (recordingDuration) => set({ recordingDuration }),
  setSpeechGain: (speechGain) => set({ speechGain }),
  setNoiseGain: (noiseGain) => set({ noiseGain }),
  setEventsGain: (eventsGain) => set({ eventsGain }),
  setDetections: (detections) => set({ detections }),
  setAutoMode: (isAutoMode) => set({ isAutoMode }),
  resetGains: () =>
    set({
      speechGain: 1.0,
      noiseGain: 0.0,
      eventsGain: 0.5,
    }),
}));
