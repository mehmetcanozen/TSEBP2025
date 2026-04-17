export interface ModelCategory {
  id: string;
  label: string;
  transient: boolean;
  defaultAggressiveness: number;
}

export interface Hive15Preset {
  id: string;
  name: string;
  description: string;
  categories: string[];
}

export interface AudioDevice {
  id: string;
  name: string;
  direction: "input" | "output";
  default: boolean;
}

export interface RuntimeMetrics {
  provider: string;
  availableProviders: string[];
  warmed: boolean;
  categoryCount: number;
  activeLiveSessions: number;
  activeJobs: number;
  modelPath?: string | null;
}

export interface StartOfflineJobRequest {
  inputPath: string;
  outputPath: string;
  categories: string[];
  aggressiveness: number;
}

export interface CancelOfflineJobRequest {
  jobId: string;
}

export interface StartLiveMonitorRequest {
  inputDeviceId?: string | null;
  outputDeviceId?: string | null;
  categories: string[];
  aggressiveness: number;
  lookaheadMs: number;
  recordOutputPath?: string | null;
}

export interface StopLiveMonitorRequest {
  sessionId: string;
}

export interface OfflineProgressEvent {
  jobId: string;
  stage:
    | "queued"
    | "warming"
    | "decoding"
    | "processing"
    | "writing"
    | "completed"
    | "failed"
    | "cancelled";
  progress: number;
  etaSeconds?: number | null;
  message?: string | null;
  outputPath?: string | null;
}

export interface LiveStatusEvent {
  sessionId: string;
  state: "starting" | "running" | "stopping" | "stopped" | "error";
  xruns: number;
  provider: string;
  lookaheadMs: number;
  inferenceMs?: number | null;
  queueDepthMs?: number | null;
  sampleRate?: number | null;
  inputDeviceId?: string | null;
  outputDeviceId?: string | null;
  message?: string | null;
}

export interface LiveMeterEvent {
  sessionId: string;
  rmsIn: number;
  rmsOut: number;
  peakIn: number;
  peakOut: number;
  waveformIn: number[];
  waveformOut: number[];
  capturedFrames: number;
  renderedFrames: number;
  timestampMs: number;
}

const FALLBACK_CATEGORIES: ModelCategory[] = [
  { id: "speech", label: "speech", transient: false, defaultAggressiveness: 1.4 },
  { id: "music", label: "music", transient: false, defaultAggressiveness: 1.5 },
  { id: "dog barking", label: "dog barking", transient: false, defaultAggressiveness: 1.9 },
  { id: "car engine", label: "car engine", transient: false, defaultAggressiveness: 1.8 },
  { id: "footsteps", label: "footsteps", transient: false, defaultAggressiveness: 1.5 },
  { id: "rain", label: "rain", transient: false, defaultAggressiveness: 1.3 },
  { id: "wind", label: "wind", transient: false, defaultAggressiveness: 1.6 },
  { id: "keyboard typing", label: "keyboard typing", transient: true, defaultAggressiveness: 2.2 },
  { id: "phone ringing", label: "phone ringing", transient: false, defaultAggressiveness: 2.0 },
  { id: "crowd noise", label: "crowd noise", transient: false, defaultAggressiveness: 1.5 },
  { id: "bird singing", label: "bird singing", transient: false, defaultAggressiveness: 1.5 },
  { id: "water flowing", label: "water flowing", transient: false, defaultAggressiveness: 1.4 },
  { id: "door knocking", label: "door knocking", transient: true, defaultAggressiveness: 2.0 },
  { id: "alarm", label: "alarm", transient: true, defaultAggressiveness: 2.3 },
  { id: "background noise", label: "background noise", transient: false, defaultAggressiveness: 1.2 },
];

const FALLBACK_PRESETS: Hive15Preset[] = [
  {
    id: "audiosep15-office",
    name: "Hive15 Office",
    description: "Exact-15 suppression for office distractions and alert sounds",
    categories: ["keyboard typing", "phone ringing", "door knocking", "alarm", "background noise"],
  },
  {
    id: "audiosep15-outdoors",
    name: "Hive15 Outdoors",
    description: "Exact-15 suppression for wind, weather, animals, and environmental wash",
    categories: ["dog barking", "rain", "wind", "bird singing", "water flowing", "background noise"],
  },
  {
    id: "audiosep15-transit",
    name: "Hive15 Transit",
    description: "Exact-15 suppression for engines, crowd wash, and background ambience",
    categories: ["music", "car engine", "footsteps", "crowd noise", "background noise"],
  },
];

const FALLBACK_RUNTIME_METRICS: RuntimeMetrics = {
  provider: "web-fallback",
  availableProviders: ["web-fallback"],
  warmed: false,
  categoryCount: FALLBACK_CATEGORIES.length,
  activeLiveSessions: 0,
  activeJobs: 0,
  modelPath: null,
};

const isTauriDesktop = () =>
  typeof window !== "undefined" && typeof window.__TAURI_INTERNALS__ !== "undefined";

async function loadTauriCore() {
  return import("@tauri-apps/api/core");
}

export async function browseForAudioInput(): Promise<string | null> {
  if (!isTauriDesktop()) {
    return null;
  }

  const { open } = await import("@tauri-apps/plugin-dialog");
  const selection = await open({
    multiple: false,
    filters: [
      {
        name: "Audio",
        extensions: ["wav", "flac", "ogg", "mp3", "m4a", "aac"],
      },
    ],
  });
  return Array.isArray(selection) ? selection[0] ?? null : selection ?? null;
}

export async function browseForOutputWav(): Promise<string | null> {
  if (!isTauriDesktop()) {
    return null;
  }

  const { save } = await import("@tauri-apps/plugin-dialog");
  return save({
    defaultPath: "cleaned.wav",
    filters: [{ name: "Wave Audio", extensions: ["wav"] }],
  });
}

export async function getModelCategories(): Promise<ModelCategory[]> {
  if (!isTauriDesktop()) {
    return FALLBACK_CATEGORIES;
  }

  const { invoke } = await loadTauriCore();
  return invoke<ModelCategory[]>("get_model_categories");
}

export async function getHive15Presets(): Promise<Hive15Preset[]> {
  if (!isTauriDesktop()) {
    return FALLBACK_PRESETS;
  }

  const { invoke } = await loadTauriCore();
  return invoke<Hive15Preset[]>("get_hive15_presets");
}

export async function listAudioDevices(): Promise<AudioDevice[]> {
  if (!isTauriDesktop()) {
    if (!navigator.mediaDevices?.enumerateDevices) {
      return [];
    }
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices
      .filter((device) => device.kind === "audioinput" || device.kind === "audiooutput")
      .map((device, index) => ({
        id: device.deviceId || `${device.kind}-${index}`,
        name: device.label || `${device.kind} ${index + 1}`,
        direction: device.kind === "audioinput" ? "input" : "output",
        default: index === 0,
      }));
  }

  const { invoke } = await loadTauriCore();
  return invoke<AudioDevice[]>("list_audio_devices");
}

export async function getRuntimeMetrics(): Promise<RuntimeMetrics> {
  if (!isTauriDesktop()) {
    return FALLBACK_RUNTIME_METRICS;
  }

  const { invoke } = await loadTauriCore();
  return invoke<RuntimeMetrics>("get_runtime_metrics");
}

export async function startOfflineJob(
  request: StartOfflineJobRequest,
  onProgress: (event: OfflineProgressEvent) => void,
): Promise<{ jobId: string }> {
  if (!isTauriDesktop()) {
    const jobId = `mock-offline-${Date.now()}`;
    onProgress({
      jobId,
      stage: "completed",
      progress: 100,
      message: "Desktop bridge unavailable in browser mode.",
      outputPath: request.outputPath,
    });
    return { jobId };
  }

  const { invoke, Channel } = await loadTauriCore();
  const progressChannel = new Channel<OfflineProgressEvent>();
  progressChannel.onmessage = onProgress;
  return invoke<{ jobId: string }>("start_offline_job", {
    request,
    progressChannel,
  });
}

export async function cancelOfflineJob(request: CancelOfflineJobRequest): Promise<void> {
  if (!isTauriDesktop()) {
    return;
  }

  const { invoke } = await loadTauriCore();
  await invoke("cancel_offline_job", { request });
}

export async function startLiveMonitor(
  request: StartLiveMonitorRequest,
  handlers: {
    onStatus: (event: LiveStatusEvent) => void;
    onMeter: (event: LiveMeterEvent) => void;
  },
): Promise<{ sessionId: string }> {
  if (!isTauriDesktop()) {
    const sessionId = `mock-live-${Date.now()}`;
    handlers.onStatus({
      sessionId,
      state: "error",
      xruns: 0,
      provider: "web-fallback",
      lookaheadMs: request.lookaheadMs,
      message: "Desktop bridge unavailable in browser mode.",
    });
    return { sessionId };
  }

  const { invoke, Channel } = await loadTauriCore();
  const statusChannel = new Channel<LiveStatusEvent>();
  const meterChannel = new Channel<LiveMeterEvent>();
  statusChannel.onmessage = handlers.onStatus;
  meterChannel.onmessage = handlers.onMeter;

  return invoke<{ sessionId: string }>("start_live_monitor", {
    request,
    statusChannel,
    meterChannel,
  });
}

export async function stopLiveMonitor(request: StopLiveMonitorRequest): Promise<void> {
  if (!isTauriDesktop()) {
    return;
  }

  const { invoke } = await loadTauriCore();
  await invoke("stop_live_monitor", { request });
}
