import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PermissionsAndroid, Platform } from 'react-native';
import * as FileSystem from 'expo-file-system';
import { useRecordings } from '../context/RecordingsContext';





import { modelBundleService } from '../services/ModelBundleService';
import {
  EngineCategoryInfo,
  EngineMeterEvent,
  EngineRuntimeInfo,
  EngineStatusEvent,
  suppressionEngineService,
} from '../services/SuppressionEngineService';

interface UseSuppressionDemoOptions {
  accessToken: string | null;
}

interface UseSuppressionDemoResult {
  startLive: () => Promise<void>;
  stopLive: () => Promise<void>;
  status: string;
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

// UI-only decorations stay separate from the packaged runtime contract so the
// native layer remains the source of truth for whichever model is active.
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

export const useSuppressionDemo = ({
  accessToken,
}: UseSuppressionDemoOptions): UseSuppressionDemoResult => {
  const nativeEngineAvailable = suppressionEngineService.isAvailable();
  const [status, setStatus] = useState<string>('Idle');
  const [isLive, setIsLive] = useState(false);
  const [target, setTarget] = useState<string>('');
  const [runtimeInfo, setRuntimeInfo] = useState<EngineRuntimeInfo | null>(null);
  const [liveStatus, setLiveStatus] = useState<EngineStatusEvent | null>(null);
  const [meter, setMeter] = useState<EngineMeterEvent | null>(null);
  const [nativeCategories, setNativeCategories] = useState<SuppressionTarget[]>([]);
  const [isRecordEnabled, setIsRecordEnabled] = useState(false);
  const [lastRecordingUri, setLastRecordingUri] = useState<string | null>(null);
  const activeRecordUri = useRef<string | null>(null);
  const { addRecording } = useRecordings();



  const syncEngine = useCallback(async () => {
    if (!nativeEngineAvailable) {
      setStatus('Live suppression requires a native Android build.');
      return null;
    }
    if (!accessToken) {
      setStatus('Login required');
      return null;
    }

    setStatus('Preparing on-device model...');
    const prepared = await modelBundleService.ensurePrepared(accessToken);
    setRuntimeInfo(prepared);

    const categories = await suppressionEngineService.getCategories().catch(() => []);
    if (categories.length > 0) {
      const mapped = categories.map(mapEngineCategory);
      setNativeCategories(mapped);
      setTarget((current) => (
        mapped.some((category) => category.id === current) ? current : pickDefaultTarget(mapped)
      ));
    }

    setStatus(prepared.warmed ? 'Engine ready' : 'Engine loaded');
    return prepared;
  }, [accessToken, nativeEngineAvailable]);

  useEffect(() => {
    if (!nativeEngineAvailable) {
      setStatus('Live suppression requires a native Android build.');
      return;
    }

    const statusSub = suppressionEngineService.addStatusListener((event) => {
      setLiveStatus(event);
      setStatus(event.message || event.state);
      setIsLive(event.state === 'running' || event.state === 'warming');
    });

    const meterSub = suppressionEngineService.addMeterListener((event) => {
      setMeter(event);
    });

    const finishedSub = suppressionEngineService.addFinishedListener(async (event) => {
      console.log('[useSuppressionDemo] Native engine finished draining:', event.sessionId);

      if (activeRecordUri.current && isRecordEnabled) {
        const uri = activeRecordUri.current;
        setLastRecordingUri(uri);

        // Auto-save to gallery
        const category = nativeCategories.find((v) => v.id === target);
        try {
          await addRecording({
            id: Date.now().toString(),
            uri: uri,
            category: target,
            categoryLabel: category?.label ?? target,
            createdAt: Date.now(),
          });
          console.log('[useSuppressionDemo] Successfully saved to gallery after background drain:', uri);
        } catch (err) {
          console.error('[useSuppressionDemo] Failed to save gallery after background drain', err);
        }
        activeRecordUri.current = null;
      }
    });

    return () => {
      statusSub.remove();
      meterSub.remove();
      finishedSub.remove();
    };
  }, [nativeEngineAvailable, isRecordEnabled, target, nativeCategories, addRecording]);


  useEffect(() => {
    if (!accessToken || !nativeEngineAvailable) {
      return;
    }

    syncEngine().catch((error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to prepare the engine';
      setStatus(`Error: ${message}`);
    });
  }, [accessToken, nativeEngineAvailable, syncEngine]);

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
    await requestMicrophonePermission();
    const prepared = runtimeInfo ?? (await syncEngine());
    if (!prepared) {
      throw new Error('The suppression engine is not ready');
    }

    const category = nativeCategories.find((value) => value.id === target);
    if (!category) {
      setStatus('Loading Waveformer categories...');
      return;
    }

    setStatus(`Starting live suppression for ${category.label}...`);

    try {
      console.log(`[useSuppressionDemo] Starting live, recordEnabled: ${isRecordEnabled}`);
      const result = await suppressionEngineService.startLive({
        categoryId: category.id,
        aggressiveness: category.defaultAggressiveness,
        hopMs: 500,
        lookaheadMs: 250,
        recordEnabled: isRecordEnabled,
      });

      // Native returns the actual record path it created
      if (result.recordPath) {
        // Force absolute path for playback
        const uri = Platform.OS === 'android' ? `file://${result.recordPath}` : result.recordPath;
        console.log(`[useSuppressionDemo] Native recording to: ${uri}`);
        activeRecordUri.current = uri;
        setLastRecordingUri(null);
      } else {
        console.log('[useSuppressionDemo] No recording path returned (recording disabled).');
        activeRecordUri.current = null;
      }
    } catch (error: any) {

      console.error('[useSuppressionDemo] startLive failed:', error);
      setStatus(`Error: ${error.message || 'Failed to start'}`);
      setIsLive(false);
      activeRecordUri.current = null;
      throw error;
    }

  }, [nativeCategories, nativeEngineAvailable, runtimeInfo, syncEngine, target, isRecordEnabled]);



  const stopLive = useCallback(async () => {
    if (!nativeEngineAvailable) {
      return;
    }

    // Optimistically set UI to not-live so button changes immediately
    setIsLive(false);
    setStatus('Stopping and preserving recording...');

    await suppressionEngineService.stopLive();

    console.log('[useSuppressionDemo] stopLive request sent to native');
    // Note: The actual file saving now happens in the finishedListener
  }, [nativeEngineAvailable]);



  const debugInfo = useMemo(() => {
    const lines = [
      `Model: ${runtimeInfo?.displayName ?? runtimeInfo?.modelVersion ?? 'none'}`,
      `Provider: ${runtimeInfo?.provider ?? 'unknown'}`,
      `Runtime: ${runtimeInfo?.runtimeKind ?? 'unknown'}`,
      `Latency: ${liveStatus?.inferenceMs?.toFixed(1) ?? '--'} ms`,
      `Queue: ${liveStatus?.queueDepthMs?.toFixed(1) ?? '--'} ms`,
      `XRuns: ${liveStatus?.xruns ?? 0}`,
      `Input RMS: ${meter?.rmsIn?.toFixed(3) ?? '--'}`,
      `Output RMS: ${meter?.rmsOut?.toFixed(3) ?? '--'}`,
    ];
    return lines.join('\n');
  }, [liveStatus, meter, runtimeInfo]);

  return {
    startLive,
    stopLive,
    status,
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
    clearLastRecording: () => setLastRecordingUri(null),
  };
};

