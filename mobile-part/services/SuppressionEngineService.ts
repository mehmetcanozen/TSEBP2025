import {
  EmitterSubscription,
  NativeEventEmitter,
  NativeModules,
} from 'react-native';

export interface EngineCategoryInfo {
  id: string;
  label: string;
  defaultAggressiveness: number;
  transient: boolean;
}

export interface EngineRuntimeInfo {
  provider: string;
  warmed: boolean;
  modelId: string | null;
  modelFamily: string | null;
  displayName: string | null;
  runtimeKind: string | null;
  modelVersion: string | null;
  modelPath: string | null;
  bundlePath: string | null;
  sampleRate: number;
  categoryCount: number;
  availableProviders: string[];
}

export interface EnginePrepareOptions {
  bundleDownloadUrl?: string;
  accessToken?: string;
  expectedVersion?: string;
  expectedChecksum?: string;
  forceRefresh?: boolean;
}

export interface EngineStartLiveConfig {
  categoryId: string;
  aggressiveness: number;
  hopMs?: number;
  lookaheadMs?: number;
}

export interface EngineStartLiveResult {
  sessionId: string;
}

export interface EngineStatusEvent {
  sessionId: string | null;
  state: string;
  provider: string;
  inferenceMs: number | null;
  queueDepthMs: number | null;
  xruns: number;
  hopMs: number;
  lookaheadMs: number;
  sampleRate: number;
  message: string | null;
}

export interface EngineMeterEvent {
  sessionId: string | null;
  rmsIn: number;
  rmsOut: number;
  peakIn: number;
  peakOut: number;
  capturedFrames: number;
  renderedFrames: number;
  timestampMs: number;
}

type NativeSuppressionEngine = {
  prepare(options?: EnginePrepareOptions): Promise<EngineRuntimeInfo>;
  startLive(config: EngineStartLiveConfig): Promise<EngineStartLiveResult>;
  stopLive(): Promise<void>;
  getRuntimeInfo(): Promise<EngineRuntimeInfo>;
  getCategories(): Promise<EngineCategoryInfo[]>;
  addListener(eventName: string): void;
  removeListeners(count: number): void;
};

const nativeModule = NativeModules.SuppressionEngine as NativeSuppressionEngine | undefined;

function requireNativeModule(): NativeSuppressionEngine {
  if (!nativeModule) {
    throw new Error(
      'SuppressionEngine native module is unavailable. Build the Android dev client after syncing native changes.'
    );
  }
  return nativeModule;
}

class SuppressionEngineService {
  isAvailable(): boolean {
    return nativeModule != null;
  }

  private get native(): NativeSuppressionEngine {
    return requireNativeModule();
  }

  private get emitter(): NativeEventEmitter {
    return new NativeEventEmitter(this.native as never);
  }

  prepare(options?: EnginePrepareOptions): Promise<EngineRuntimeInfo> {
    return this.native.prepare(options);
  }

  startLive(config: EngineStartLiveConfig): Promise<EngineStartLiveResult> {
    return this.native.startLive(config);
  }

  stopLive(): Promise<void> {
    return this.native.stopLive();
  }

  getRuntimeInfo(): Promise<EngineRuntimeInfo> {
    return this.native.getRuntimeInfo();
  }

  getCategories(): Promise<EngineCategoryInfo[]> {
    return this.native.getCategories();
  }

  addStatusListener(listener: (event: EngineStatusEvent) => void): EmitterSubscription {
    return this.emitter.addListener('SuppressionEngineStatus', listener);
  }

  addMeterListener(listener: (event: EngineMeterEvent) => void): EmitterSubscription {
    return this.emitter.addListener('SuppressionEngineMeter', listener);
  }
}

export const suppressionEngineService = new SuppressionEngineService();
