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
  { id: "alarm_clock", label: "alarm clock", transient: true, defaultAggressiveness: 1.1 },
  { id: "baby_cry", label: "baby cry", transient: false, defaultAggressiveness: 1.1 },
  { id: "birds_chirping", label: "birds chirping", transient: false, defaultAggressiveness: 1.05 },
  { id: "cat", label: "cat", transient: false, defaultAggressiveness: 1.0 },
  { id: "car_horn", label: "car horn", transient: true, defaultAggressiveness: 1.2 },
  { id: "cock_a_doodle_doo", label: "cock-a-doodle-doo", transient: true, defaultAggressiveness: 1.1 },
  { id: "cricket", label: "cricket", transient: false, defaultAggressiveness: 1.0 },
  { id: "computer_typing", label: "computer typing", transient: true, defaultAggressiveness: 1.25 },
  { id: "dog", label: "dog", transient: false, defaultAggressiveness: 1.1 },
  { id: "glass_breaking", label: "glass breaking", transient: true, defaultAggressiveness: 1.25 },
  { id: "gunshot", label: "gunshot", transient: true, defaultAggressiveness: 1.25 },
  { id: "hammer", label: "hammer", transient: true, defaultAggressiveness: 1.2 },
  { id: "music", label: "music", transient: false, defaultAggressiveness: 1.0 },
  { id: "ocean", label: "ocean", transient: false, defaultAggressiveness: 0.95 },
  { id: "door_knock", label: "door knock", transient: true, defaultAggressiveness: 1.2 },
  { id: "singing", label: "singing", transient: false, defaultAggressiveness: 1.0 },
  { id: "siren", label: "siren", transient: true, defaultAggressiveness: 1.15 },
  { id: "speech", label: "speech", transient: false, defaultAggressiveness: 1.0 },
  { id: "thunderstorm", label: "thunderstorm", transient: false, defaultAggressiveness: 1.05 },
  { id: "toilet_flush", label: "toilet flush", transient: true, defaultAggressiveness: 1.0 },
];

const FALLBACK_PRESETS: Hive15Preset[] = [
  {
    id: "waveformer-focus",
    name: "Waveformer Focus",
    description: "Suppress conversational and office-like distractions with the streaming target extractor.",
    categories: ["speech", "singing", "computer_typing", "door_knock", "alarm_clock"],
  },
  {
    id: "waveformer-alerts",
    name: "Waveformer Alerts",
    description: "Suppress prominent alert-like events and sharp alarms.",
    categories: ["alarm_clock", "car_horn", "glass_breaking", "gunshot", "siren"],
  },
  {
    id: "waveformer-outdoors",
    name: "Waveformer Outdoors",
    description: "Suppress common outdoor ambience and animal distractions.",
    categories: ["birds_chirping", "dog", "ocean", "thunderstorm", "cricket"],
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
