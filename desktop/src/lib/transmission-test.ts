import type { LiveStatusEvent, VirtualMicStatus } from "@/lib/desktop-api";

export type TransmissionPermissionState = "unknown" | "prompt" | "granted" | "denied";
export type TransmissionTestState =
  | "idle"
  | "requestingPermission"
  | "ready"
  | "running"
  | "calibrating"
  | "error";

export interface TransmissionCaptureSettings {
  channelCount: number | null;
  latency: number | null;
  sampleRate: number | null;
  sampleSize: number | null;
}

export interface TransmissionCalibrationResult {
  status: "idle" | "running" | "completed" | "failed";
  startedAtMs?: number | null;
  completedAtMs?: number | null;
  calibratedLoopbackMs?: number | null;
  message?: string | null;
}

export interface TransmissionMetricsSnapshot {
  captureDeviceId: string | null;
  captureDeviceName: string | null;
  captureSettings: TransmissionCaptureSettings | null;
  codecName: string | null;
  currentRoundTripTimeMs: number | null;
  averageRoundTripTimeMs: number | null;
  maxRoundTripTimeMs: number | null;
  inboundJitterMs: number | null;
  avgJitterBufferDelayMs: number | null;
  packetsLost: number | null;
  packetsReceived: number | null;
  packetLossRate: number | null;
  concealedSamples: number | null;
  concealmentEvents: number | null;
  sendBitrateKbps: number | null;
  receiveBitrateKbps: number | null;
  appLiveLatencyMs: number | null;
  queueDepthMs: number | null;
  inferenceP95Ms: number | null;
  realtimeHealth: LiveStatusEvent["realtimeHealth"];
  networkLoopbackEstimateMs: number | null;
  combinedEstimateMs: number | null;
  calibratedLoopbackMs: number | null;
  sessionSeconds: number;
  receivedRms: number;
  receivedPeak: number;
  receivedWaveform: number[];
  permissionState: TransmissionPermissionState;
  message?: string | null;
}

export interface TransmissionStatsAggregate {
  samples: number;
  rttSumMs: number;
  maxRoundTripTimeMs: number | null;
  lastSentBytes: number | null;
  lastReceivedBytes: number | null;
  lastStatsAtMs: number | null;
}

export interface TransmissionStatsSample {
  currentRoundTripTimeMs?: number | null;
  inboundJitterMs?: number | null;
  jitterBufferDelayMs?: number | null;
  jitterBufferEmittedCount?: number | null;
  packetsLost?: number | null;
  packetsReceived?: number | null;
  concealedSamples?: number | null;
  concealmentEvents?: number | null;
  sentBytes?: number | null;
  receivedBytes?: number | null;
  codecName?: string | null;
}

export const INITIAL_TRANSMISSION_CALIBRATION: TransmissionCalibrationResult = {
  status: "idle",
  startedAtMs: null,
  completedAtMs: null,
  calibratedLoopbackMs: null,
  message: null,
};

export const INITIAL_TRANSMISSION_METRICS: TransmissionMetricsSnapshot = {
  captureDeviceId: null,
  captureDeviceName: null,
  captureSettings: null,
  codecName: null,
  currentRoundTripTimeMs: null,
  averageRoundTripTimeMs: null,
  maxRoundTripTimeMs: null,
  inboundJitterMs: null,
  avgJitterBufferDelayMs: null,
  packetsLost: null,
  packetsReceived: null,
  packetLossRate: null,
  concealedSamples: null,
  concealmentEvents: null,
  sendBitrateKbps: null,
  receiveBitrateKbps: null,
  appLiveLatencyMs: null,
  queueDepthMs: null,
  inferenceP95Ms: null,
  realtimeHealth: "idle",
  networkLoopbackEstimateMs: null,
  combinedEstimateMs: null,
  calibratedLoopbackMs: null,
  sessionSeconds: 0,
  receivedRms: 0,
  receivedPeak: 0,
  receivedWaveform: [],
  permissionState: "unknown",
  message: null,
};

export const INITIAL_TRANSMISSION_STATS: TransmissionStatsAggregate = {
  samples: 0,
  rttSumMs: 0,
  maxRoundTripTimeMs: null,
  lastSentBytes: null,
  lastReceivedBytes: null,
  lastStatsAtMs: null,
};

const VIRTUAL_CABLE_ALIASES = ["cable output", "vb-audio virtual cable", "virtual cable"];

export function normalizeTransmissionDeviceLabel(value?: string | null): string {
  return (value ?? "").trim().toLowerCase().replace(/\s+/g, " ");
}

export function matchesTransmissionRecordingDevice(
  deviceLabel: string,
  virtualMicStatus: VirtualMicStatus | null,
): boolean {
  const normalized = normalizeTransmissionDeviceLabel(deviceLabel);
  if (!normalized) {
    return false;
  }

  const preferred = normalizeTransmissionDeviceLabel(virtualMicStatus?.recordingDeviceName);
  if (preferred && normalized.includes(preferred)) {
    return true;
  }

  return VIRTUAL_CABLE_ALIASES.every((alias) => normalized.includes(alias))
    || (normalized.includes("cable output") && normalized.includes("virtual cable"));
}

export function resolveTransmissionRecordingDevice(
  devices: MediaDeviceInfo[],
  virtualMicStatus: VirtualMicStatus | null,
): MediaDeviceInfo | null {
  const audioInputs = devices.filter((device) => device.kind === "audioinput");
  const exact = audioInputs.find((device) =>
    normalizeTransmissionDeviceLabel(device.label) === normalizeTransmissionDeviceLabel(virtualMicStatus?.recordingDeviceName),
  );
  if (exact) {
    return exact;
  }

  return audioInputs.find((device) => matchesTransmissionRecordingDevice(device.label, virtualMicStatus)) ?? null;
}

export function derivePacketLossRate(
  packetsLost?: number | null,
  packetsReceived?: number | null,
): number | null {
  if (packetsLost == null || packetsReceived == null) {
    return null;
  }
  const total = packetsLost + packetsReceived;
  if (total <= 0) {
    return 0;
  }
  return packetsLost / total;
}

export function deriveAverageJitterBufferDelayMs(
  jitterBufferDelayMs?: number | null,
  jitterBufferEmittedCount?: number | null,
): number | null {
  if (jitterBufferDelayMs == null || jitterBufferEmittedCount == null || jitterBufferEmittedCount <= 0) {
    return null;
  }
  return jitterBufferDelayMs / jitterBufferEmittedCount;
}

export function deriveNetworkLoopbackEstimateMs(
  avgJitterBufferDelayMs?: number | null,
  currentRoundTripTimeMs?: number | null,
): number | null {
  if (avgJitterBufferDelayMs == null && currentRoundTripTimeMs == null) {
    return null;
  }
  if (avgJitterBufferDelayMs == null) {
    return currentRoundTripTimeMs != null ? currentRoundTripTimeMs / 2 : null;
  }
  if (currentRoundTripTimeMs == null) {
    return avgJitterBufferDelayMs;
  }
  return avgJitterBufferDelayMs + currentRoundTripTimeMs / 2;
}

export function deriveCombinedEstimateMs(
  appLiveLatencyMs?: number | null,
  networkLoopbackEstimateMs?: number | null,
): number | null {
  if (appLiveLatencyMs == null && networkLoopbackEstimateMs == null) {
    return null;
  }
  return (appLiveLatencyMs ?? 0) + (networkLoopbackEstimateMs ?? 0);
}

export function bitrateFromDeltaKbps(
  bytesDelta?: number | null,
  elapsedMs?: number | null,
): number | null {
  if (bytesDelta == null || elapsedMs == null || elapsedMs <= 0) {
    return null;
  }
  return (bytesDelta * 8) / elapsedMs;
}

export function createTransmissionWaveform(
  frequencyData: Uint8Array,
  bins = 24,
): number[] {
  if (!frequencyData.length || bins <= 0) {
    return [];
  }

  const values: number[] = [];
  const step = Math.max(1, Math.floor(frequencyData.length / bins));
  for (let index = 0; index < bins; index += 1) {
    const start = index * step;
    const end = Math.min(frequencyData.length, start + step);
    let sum = 0;
    let count = 0;
    for (let cursor = start; cursor < end; cursor += 1) {
      sum += frequencyData[cursor];
      count += 1;
    }
    values.push(count ? sum / count / 255 : 0);
  }
  return values;
}

export function computeRmsAndPeak(timeDomainData: Uint8Array): { rms: number; peak: number } {
  if (!timeDomainData.length) {
    return { rms: 0, peak: 0 };
  }

  let sumSquares = 0;
  let peak = 0;
  for (const sample of timeDomainData) {
    const centered = (sample - 128) / 128;
    sumSquares += centered * centered;
    peak = Math.max(peak, Math.abs(centered));
  }

  return {
    rms: Math.sqrt(sumSquares / timeDomainData.length),
    peak,
  };
}

export function mergeTransmissionMetrics(
  current: TransmissionMetricsSnapshot,
  patch: Partial<TransmissionMetricsSnapshot>,
): TransmissionMetricsSnapshot {
  return { ...current, ...patch };
}

export function applyTransmissionStatsSample(
  metrics: TransmissionMetricsSnapshot,
  aggregate: TransmissionStatsAggregate,
  sample: TransmissionStatsSample,
  timestampMs: number,
): {
  metrics: TransmissionMetricsSnapshot;
  aggregate: TransmissionStatsAggregate;
} {
  const currentRoundTripTimeMs = sample.currentRoundTripTimeMs ?? metrics.currentRoundTripTimeMs;
  const inboundJitterMs = sample.inboundJitterMs ?? metrics.inboundJitterMs;
  const avgJitterBufferDelayMs = deriveAverageJitterBufferDelayMs(
    sample.jitterBufferDelayMs,
    sample.jitterBufferEmittedCount,
  ) ?? metrics.avgJitterBufferDelayMs;
  const packetsLost = sample.packetsLost ?? metrics.packetsLost;
  const packetsReceived = sample.packetsReceived ?? metrics.packetsReceived;
  const packetLossRate = derivePacketLossRate(packetsLost, packetsReceived);
  const concealedSamples = sample.concealedSamples ?? metrics.concealedSamples;
  const concealmentEvents = sample.concealmentEvents ?? metrics.concealmentEvents;

  const nextSamples = currentRoundTripTimeMs != null ? aggregate.samples + 1 : aggregate.samples;
  const nextRttSumMs =
    currentRoundTripTimeMs != null ? aggregate.rttSumMs + currentRoundTripTimeMs : aggregate.rttSumMs;
  const averageRoundTripTimeMs = nextSamples > 0 ? nextRttSumMs / nextSamples : metrics.averageRoundTripTimeMs;
  const maxRoundTripTimeMs =
    currentRoundTripTimeMs == null
      ? aggregate.maxRoundTripTimeMs ?? metrics.maxRoundTripTimeMs
      : Math.max(aggregate.maxRoundTripTimeMs ?? 0, currentRoundTripTimeMs);

  const elapsedMs = aggregate.lastStatsAtMs != null ? timestampMs - aggregate.lastStatsAtMs : null;
  const sendBitrateKbps =
    sample.sentBytes != null && aggregate.lastSentBytes != null
      ? bitrateFromDeltaKbps(sample.sentBytes - aggregate.lastSentBytes, elapsedMs)
      : metrics.sendBitrateKbps;
  const receiveBitrateKbps =
    sample.receivedBytes != null && aggregate.lastReceivedBytes != null
      ? bitrateFromDeltaKbps(sample.receivedBytes - aggregate.lastReceivedBytes, elapsedMs)
      : metrics.receiveBitrateKbps;

  const networkLoopbackEstimateMs = deriveNetworkLoopbackEstimateMs(
    avgJitterBufferDelayMs,
    currentRoundTripTimeMs,
  );

  const nextMetrics = mergeTransmissionMetrics(metrics, {
    codecName: sample.codecName ?? metrics.codecName,
    currentRoundTripTimeMs,
    averageRoundTripTimeMs,
    maxRoundTripTimeMs,
    inboundJitterMs,
    avgJitterBufferDelayMs,
    packetsLost,
    packetsReceived,
    packetLossRate,
    concealedSamples,
    concealmentEvents,
    sendBitrateKbps,
    receiveBitrateKbps,
    networkLoopbackEstimateMs,
    combinedEstimateMs: deriveCombinedEstimateMs(metrics.appLiveLatencyMs, networkLoopbackEstimateMs),
  });

  return {
    metrics: nextMetrics,
    aggregate: {
      samples: nextSamples,
      rttSumMs: nextRttSumMs,
      maxRoundTripTimeMs,
      lastSentBytes: sample.sentBytes ?? aggregate.lastSentBytes,
      lastReceivedBytes: sample.receivedBytes ?? aggregate.lastReceivedBytes,
      lastStatsAtMs: timestampMs,
    },
  };
}

export function createAppLiveMetricsPatch(
  liveStatus: LiveStatusEvent | null,
  calibration: TransmissionCalibrationResult,
): Partial<TransmissionMetricsSnapshot> {
  return {
    appLiveLatencyMs: liveStatus?.estimatedLatencyMs ?? null,
    queueDepthMs: liveStatus?.queueDepthMs ?? null,
    inferenceP95Ms: liveStatus?.inferenceMsP95 ?? null,
    realtimeHealth: liveStatus?.realtimeHealth ?? "idle",
    calibratedLoopbackMs: calibration.calibratedLoopbackMs ?? null,
  };
}
