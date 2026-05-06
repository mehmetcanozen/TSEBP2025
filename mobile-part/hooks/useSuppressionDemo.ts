import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PermissionsAndroid, Platform } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import { useRecordings } from '../context/RecordingsContext';
import { modelBundleService } from '../services/ModelBundleService';
import {
  EngineCategoryInfo,
  EngineMeterEvent,
  EngineRuntimeInfo,
  EngineStatusEvent,
  LivePhase,
  suppressionEngineService,
} from '../services/SuppressionEngineService';

interface UseSuppressionDemoResult {
  startLive: () => Promise<void>;
  stopLive: () => Promise<void>;
  status: string;
  phase: LivePhase;
  isLive: boolean;
  target: string;
  setTarget: (target: string) => void;
  debugInfo: string;
  runtimeInfo: EngineRuntimeInfo | null;
  liveStatus: EngineStatusEvent | null;
  meter: EngineMeterEvent | null;
  availableTargets: SuppressionTarget[];
  isRecordEnabled: boolean;
  setIsRecordEnabled: (enabled: boolean) => void;
  lastRecordingUri: string | null;
  lastRecordingFileName: string | null;
  lastRecordingFilePath: string | null;
  lastRecordingFileSizeBytes: number | null;
  clearLastRecording: () => void;
}

interface SuppressionTarget {
  id: string;
  label: string;
  icon: string;
  defaultAggressiveness: number;
  transient: boolean;
}

interface CategoryDecoration {
  icon: string;
  defaultAggressiveness?: number;
  transient?: boolean;
}

const STOP_FINISHED_TIMEOUT_MS = 12000;
const ALWAYS_SAVE_PROCESSED_AUDIO = true;

const CATEGORY_DECORATIONS: Record<string, CategoryDecoration> = {
  alarm: { icon: 'alarm-outline', transient: true },
  alarm_clock: { icon: 'alarm-outline', transient: true },
  baby_cry: { icon: 'happy-outline' },
  background_noise: { icon: 'pulse-outline' },
  'background noise': { icon: 'pulse-outline' },
  bird_singing: { icon: 'leaf-outline' },
  'bird singing': { icon: 'leaf-outline' },
  birds_chirping: { icon: 'leaf-outline' },
  car_engine: { icon: 'car-sport-outline' },
  'car engine': { icon: 'car-sport-outline' },
  car_horn: { icon: 'car-sport-outline', transient: true },
  cat: { icon: 'paw-outline' },
  cock_a_doodle_doo: { icon: 'sunny-outline', transient: true },
  computer_typing: { icon: 'keypad-outline', transient: true },
  cricket: { icon: 'bug-outline' },
  crowd_noise: { icon: 'people-outline' },
  'crowd noise': { icon: 'people-outline' },
  dog: { icon: 'paw-outline' },
  dog_barking: { icon: 'paw-outline' },
  'dog barking': { icon: 'paw-outline' },
  door_knock: { icon: 'hand-left-outline', transient: true },
  door_knocking: { icon: 'hand-left-outline', transient: true },
  'door knocking': { icon: 'hand-left-outline', transient: true },
  footsteps: { icon: 'walk-outline' },
  glass_breaking: { icon: 'alert-circle-outline', transient: true },
  gunshot: { icon: 'flash-outline', transient: true },
  hammer: { icon: 'construct-outline', transient: true },
  keyboard_typing: { icon: 'keypad-outline', transient: true },
  'keyboard typing': { icon: 'keypad-outline', transient: true },
  music: { icon: 'musical-notes-outline' },
  ocean: { icon: 'water-outline' },
  phone_ringing: { icon: 'call-outline' },
  'phone ringing': { icon: 'call-outline' },
  rain: { icon: 'rainy-outline' },
  singing: { icon: 'mic-outline' },
  siren: { icon: 'radio-outline', transient: true },
  speech: { icon: 'chatbubble-ellipses-outline' },
  thunderstorm: { icon: 'thunderstorm-outline' },
  toilet_flush: { icon: 'water-outline', transient: true },
  water_flowing: { icon: 'water-outline' },
  'water flowing': { icon: 'water-outline' },
  wind: { icon: 'cloud-outline' },
};

const DEFAULT_TARGET_PRIORITY = [
  'speech',
  'computer_typing',
  'keyboard typing',
  'music',
  'alarm_clock',
  'alarm',
];

function prettifyCategoryLabel(categoryId: string): string {
  return categoryId.replace(/[_-]+/g, ' ');
}

function decorationForCategory(categoryId: string): CategoryDecoration {
  return CATEGORY_DECORATIONS[categoryId] ?? CATEGORY_DECORATIONS[categoryId.toLowerCase()] ?? {
    icon: 'pulse-outline',
  };
}

function pickDefaultTarget(categories: SuppressionTarget[]): string {
  for (const preferred of DEFAULT_TARGET_PRIORITY) {
    const match = categories.find((category) => category.id === preferred);
    if (match) {
      return match.id;
    }
  }
  return categories[0]?.id ?? '';
}

function mapEngineCategory(category: EngineCategoryInfo): SuppressionTarget {
  const decoration = decorationForCategory(category.id);
  return {
    id: category.id,
    label: category.label || prettifyCategoryLabel(category.id),
    icon: decoration.icon,
    defaultAggressiveness:
      category.defaultAggressiveness ?? decoration.defaultAggressiveness ?? 1.2,
    transient: category.transient ?? decoration.transient ?? false,
  };
}

async function requestMicrophonePermission(): Promise<void> {
  if (Platform.OS !== 'android') {
    return;
  }

  const granted = await PermissionsAndroid.request(
    PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
    {
      title: 'Microphone Permission',
      message: 'Semantic Noise Suppression needs microphone access for live suppression.',
      buttonPositive: 'OK',
      buttonNegative: 'Cancel',
      buttonNeutral: 'Ask Me Later',
    }
  );

  if (granted !== PermissionsAndroid.RESULTS.GRANTED) {
    throw new Error('Microphone permission was denied');
  }
}

function filenameFromPath(path: string | null): string {
  return path?.split('/').pop() || `suppression_${Date.now()}.wav`;
}

export const useSuppressionDemo = (): UseSuppressionDemoResult => {
  const nativeEngineAvailable = suppressionEngineService.isAvailable();
  const [status, setStatus] = useState<string>('Idle');
  const [phase, setPhaseState] = useState<LivePhase>('idle');
  const [isLive, setIsLive] = useState(false);
  const [target, setTarget] = useState<string>('');
  const [runtimeInfo, setRuntimeInfo] = useState<EngineRuntimeInfo | null>(null);
  const [liveStatus, setLiveStatus] = useState<EngineStatusEvent | null>(null);
  const [meter, setMeter] = useState<EngineMeterEvent | null>(null);
  const [nativeCategories, setNativeCategories] = useState<SuppressionTarget[]>([]);
  const [isRecordEnabled, setIsRecordEnabled] = useState(true);
  const [lastRecordingUri, setLastRecordingUri] = useState<string | null>(null);
  const [lastRecordingFileName, setLastRecordingFileName] = useState<string | null>(null);
  const [lastRecordingFilePath, setLastRecordingFilePath] = useState<string | null>(null);
  const [lastRecordingFileSizeBytes, setLastRecordingFileSizeBytes] = useState<number | null>(null);
  const activeRecordUri = useRef<string | null>(null);
  const activeRecordPath = useRef<string | null>(null);
  const activeCategory = useRef<SuppressionTarget | null>(null);
  const sessionIntendedToRecord = useRef(false);
  const currentSessionId = useRef<string | null>(null);
  const releasedSessionId = useRef<string | null>(null);
  const phaseRef = useRef<LivePhase>('idle');
  const stopTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { addRecording } = useRecordings();

  const setPhase = useCallback((next: LivePhase) => {
    phaseRef.current = next;
    setPhaseState(next);
    setIsLive(next === 'running');
  }, []);

  const clearStopTimeout = useCallback(() => {
    if (stopTimeoutRef.current) {
      clearTimeout(stopTimeoutRef.current);
      stopTimeoutRef.current = null;
    }
  }, []);

  const resetLastRecording = useCallback(() => {
    setLastRecordingUri(null);
    setLastRecordingFileName(null);
    setLastRecordingFilePath(null);
    setLastRecordingFileSizeBytes(null);
  }, []);

  const isCurrentSessionEvent = useCallback((sessionId: string | null | undefined) => {
    const current = currentSessionId.current;
    if (!sessionId) {
      return current == null;
    }
    return current != null && sessionId === current;
  }, []);

  useEffect(() => () => {
    clearStopTimeout();
  }, [clearStopTimeout]);

  const syncEngine = useCallback(async () => {
    if (!nativeEngineAvailable) {
      setStatus('Live suppression requires a native Android build.');
      return null;
    }

    setStatus('Preparing on-device model...');
    const prepared = await modelBundleService.ensurePrepared();
    setRuntimeInfo(prepared.runtimeInfo);

    const categories = await suppressionEngineService.getCategories().catch(() => []);
    if (categories.length > 0) {
      const mapped = categories.map(mapEngineCategory);
      setNativeCategories(mapped);
      setTarget((current) => (
        mapped.some((category) => category.id === current) ? current : pickDefaultTarget(mapped)
      ));
    }

    setStatus(prepared.message ?? (prepared.runtimeInfo.warmed ? 'Engine ready' : 'Engine loaded'));
    return prepared.runtimeInfo;
  }, [nativeEngineAvailable]);

  useEffect(() => {
    if (!nativeEngineAvailable) {
      setStatus('Live suppression requires a native Android build.');
      return;
    }

    const statusSub = suppressionEngineService.addStatusListener((event) => {
      if (!isCurrentSessionEvent(event.sessionId)) {
        return;
      }
      setLiveStatus(event);
      setStatus(event.message || event.state);
      if (event.state === 'running') {
        setPhase('running');
      } else if (event.state === 'stopping') {
        setPhase('stopping');
      } else if (event.state === 'stopped' && currentSessionId.current == null) {
        setPhase('idle');
      }
    });

    const meterSub = suppressionEngineService.addMeterListener((event) => {
      if (!isCurrentSessionEvent(event.sessionId)) {
        return;
      }
      setMeter(event);
    });

    const finishedSub = suppressionEngineService.addFinishedListener(async (event) => {
      console.log('[useSuppressionDemo] Native engine finished draining:', event.sessionId);

      const matchesCurrent = event.sessionId === currentSessionId.current;
      const matchesReleased = event.sessionId === releasedSessionId.current;
      if (!matchesCurrent && !matchesReleased) {
        console.log('[useSuppressionDemo] Ignoring finished event for old/mismatched session:', event.sessionId);
        return;
      }

      clearStopTimeout();

      if (activeRecordUri.current && sessionIntendedToRecord.current) {
        const uri = activeRecordUri.current;
        const path = activeRecordPath.current;
        const fileName = filenameFromPath(path);

        setLastRecordingUri(uri);
        setLastRecordingFileName(fileName);
        setLastRecordingFilePath(path);

        const category = activeCategory.current ?? nativeCategories.find((value) => value.id === target);
        try {
          const fileInfo = await FileSystem.getInfoAsync(uri);
          const size = fileInfo.exists ? ((fileInfo as any).size ?? null) : null;
          console.log(`[useSuppressionDemo] Recording file info: exists=${fileInfo.exists}, size=${size} bytes`);
          setLastRecordingFileSizeBytes(size);

          await addRecording({
            id: Date.now().toString(),
            uri,
            fileName,
            filePath: path ?? uri,
            fileSizeBytes: size,
            category: target,
            categoryLabel: category?.label ?? target,
            createdAt: Date.now(),
          });
          console.log('[useSuppressionDemo] Successfully saved to library after background drain:', uri);
        } catch (error) {
          console.error('[useSuppressionDemo] Failed to save library after background drain', error);
        }
      } else {
        console.log('[useSuppressionDemo] Session ended but no recording saved.');
      }

      activeRecordUri.current = null;
      activeRecordPath.current = null;
      activeCategory.current = null;
      sessionIntendedToRecord.current = false;
      currentSessionId.current = null;
      releasedSessionId.current = null;
      setPhase('idle');
    });

    return () => {
      statusSub.remove();
      meterSub.remove();
      finishedSub.remove();
    };
  }, [addRecording, clearStopTimeout, isCurrentSessionEvent, nativeCategories, nativeEngineAvailable, setPhase, target]);

  useEffect(() => {
    if (!nativeEngineAvailable) {
      return;
    }

    syncEngine().catch((error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to prepare the engine';
      setStatus(`Error: ${message}`);
      setPhase('error');
    });
  }, [nativeEngineAvailable, setPhase, syncEngine]);

  useEffect(() => {
    if (!nativeEngineAvailable) {
      return;
    }

    return () => {
      suppressionEngineService.stopLive().catch(() => undefined);
    };
  }, [nativeEngineAvailable]);

  const startLive = useCallback(async () => {
    if (!nativeEngineAvailable) {
      setStatus('Live suppression requires a native Android build.');
      return;
    }
    if (phaseRef.current === 'preparing' || phaseRef.current === 'running' || phaseRef.current === 'stopping') {
      setStatus(phaseRef.current === 'stopping' ? 'Finishing previous session...' : status);
      return;
    }

    if (currentSessionId.current || releasedSessionId.current) {
      setStatus('Saving previous recording...');
      return;
    }

    setPhase('preparing');
    try {
      await requestMicrophonePermission();
      const prepared = runtimeInfo ?? (await syncEngine());
      if (!prepared) {
        setPhase('idle');
        throw new Error('The suppression engine is not ready');
      }

      const category = nativeCategories.find((value) => value.id === target);
      if (!category) {
        setStatus('Loading Waveformer categories...');
        setPhase('idle');
        return;
      }

      setStatus(`Starting live suppression for ${category.label}...`);
      activeCategory.current = category;
      const shouldRecord = ALWAYS_SAVE_PROCESSED_AUDIO || isRecordEnabled;
      if (shouldRecord && !isRecordEnabled) {
        setIsRecordEnabled(true);
      }

      console.log(`[useSuppressionDemo] Starting live, recordEnabled: ${shouldRecord}`);
      const result = await suppressionEngineService.startLive({
        categoryId: category.id,
        aggressiveness: category.defaultAggressiveness,
        hopMs: 200,
        lookaheadMs: 350,
        audioEngine: 'legacy',
        waveformerPostFilter: 'off',
        recordEnabled: shouldRecord,
      });

      console.log(`[useSuppressionDemo] Starting session: ${result.sessionId}`);
      currentSessionId.current = result.sessionId;
      setPhase('running');

      if (result.recordPath) {
        const uri = Platform.OS === 'android' ? `file://${result.recordPath}` : result.recordPath;
        console.log(`[useSuppressionDemo] Native recording to: ${uri}`);
        activeRecordUri.current = uri;
        activeRecordPath.current = result.recordPath;
        sessionIntendedToRecord.current = true;
        resetLastRecording();
      } else {
        console.log('[useSuppressionDemo] No recording path returned (recording disabled).');
        activeRecordUri.current = null;
        activeRecordPath.current = null;
        sessionIntendedToRecord.current = false;
      }
    } catch (error: any) {
      console.error('[useSuppressionDemo] startLive failed:', error);
      setStatus(`Error: ${error.message || 'Failed to start'}`);
      setPhase('error');
      activeRecordUri.current = null;
      activeRecordPath.current = null;
      activeCategory.current = null;
      sessionIntendedToRecord.current = false;
      currentSessionId.current = null;
      releasedSessionId.current = null;
      resetLastRecording();
      throw error;
    }
  }, [
    isRecordEnabled,
    nativeCategories,
    nativeEngineAvailable,
    resetLastRecording,
    runtimeInfo,
    setPhase,
    status,
    syncEngine,
    target,
  ]);

  const stopLive = useCallback(async () => {
    if (!nativeEngineAvailable || phaseRef.current !== 'running') {
      return;
    }

    setPhase('stopping');
    setStatus('Stopping and preserving recording...');

    try {
      await suppressionEngineService.stopLive();
      clearStopTimeout();
      stopTimeoutRef.current = setTimeout(() => {
        console.warn('[useSuppressionDemo] Timed out waiting for native finished event; releasing UI.');
        releasedSessionId.current = currentSessionId.current;
        currentSessionId.current = null;
        setPhase('idle');
        setStatus('Stopped; saving may finish in the background.');
      }, STOP_FINISHED_TIMEOUT_MS);
      console.log('[useSuppressionDemo] stopLive request sent to native');
    } catch (error: any) {
      console.error('[useSuppressionDemo] stopLive failed:', error);
      clearStopTimeout();
      setPhase('error');
      setStatus(`Error: ${error.message || 'Failed to stop'}`);
      throw error;
    }
  }, [clearStopTimeout, nativeEngineAvailable, setPhase]);

  const debugInfo = useMemo(() => {
    const lines = [
      `Model: ${runtimeInfo?.displayName ?? runtimeInfo?.modelVersion ?? 'none'}`,
      `Provider: ${runtimeInfo?.provider ?? 'unknown'}`,
      `Runtime: ${runtimeInfo?.runtimeKind ?? 'unknown'}`,
      `Audio engine: ${liveStatus?.audioEngine ?? runtimeInfo?.audioEngine ?? 'auto'}`,
      `Native Oboe available: ${runtimeInfo?.nativeOboeAvailable ? 'yes' : 'no'}`,
      `Latency: ${liveStatus?.inferenceMs?.toFixed(1) ?? '--'} ms`,
      `Latency p95: ${liveStatus?.inferenceP95Ms?.toFixed(1) ?? '--'} ms`,
      `Queue: ${liveStatus?.queueDepthMs?.toFixed(1) ?? '--'} ms`,
      `Native rate: ${liveStatus?.nativeSampleRate ?? runtimeInfo?.sampleRate ?? '--'} Hz`,
      `Frames/burst: ${liveStatus?.framesPerBurst ?? '--'}`,
      `XRuns: ${liveStatus?.xruns ?? 0}`,
      `AudioTrack underruns: ${liveStatus?.audioTrackUnderruns ?? 0}`,
      `Callback underruns: ${liveStatus?.callbackUnderruns ?? 0}`,
      `Input overflows: ${liveStatus?.inputOverflows ?? 0}`,
      `Render underruns: ${liveStatus?.renderUnderruns ?? 0}`,
      `Limiter hits: ${liveStatus?.limiterHits ?? 0}`,
      `Fail-open: ${liveStatus?.failOpenCount ?? 0}`,
      `Boundary repairs: ${liveStatus?.boundaryRepairHits ?? 0}`,
      `Startup blend: ${liveStatus?.startupBlendMs ?? 0} ms`,
      `Waveformer post-filter: ${liveStatus?.waveformerPostFilter ?? '--'}`,
      `STFT Wiener bypassed: ${liveStatus?.wienerBypassed ? 'yes' : 'no'}`,
      `Input RMS: ${meter?.rmsIn?.toFixed(3) ?? '--'}`,
      `Output RMS: ${meter?.rmsOut?.toFixed(3) ?? '--'}`,
      `Raw out peak: ${meter?.rawOutPeak?.toFixed(3) ?? '--'}`,
      `Final out peak: ${meter?.finalOutPeak?.toFixed(3) ?? '--'}`,
    ];
    return lines.join('\n');
  }, [liveStatus, meter, runtimeInfo]);

  return {
    startLive,
    stopLive,
    status,
    phase,
    isLive,
    target,
    setTarget,
    debugInfo,
    runtimeInfo,
    liveStatus,
    meter,
    availableTargets: nativeCategories,
    isRecordEnabled,
    setIsRecordEnabled,
    lastRecordingUri,
    lastRecordingFileName,
    lastRecordingFilePath,
    lastRecordingFileSizeBytes,
    clearLastRecording: resetLastRecording,
  };
};
