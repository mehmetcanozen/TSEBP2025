import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { LiveStatusEvent, VirtualMicStatus } from "@/lib/desktop-api";
import {
  applyTransmissionStatsSample,
  computeRmsAndPeak,
  createAppLiveMetricsPatch,
  createTransmissionWaveform,
  deriveCombinedEstimateMs,
  INITIAL_TRANSMISSION_CALIBRATION,
  INITIAL_TRANSMISSION_METRICS,
  INITIAL_TRANSMISSION_STATS,
  mergeTransmissionMetrics,
  resolveTransmissionRecordingDevice,
  type TransmissionCalibrationResult,
  type TransmissionMetricsSnapshot,
  type TransmissionPermissionState,
  type TransmissionStatsAggregate,
  type TransmissionTestState,
} from "@/lib/transmission-test";

interface UseTransmissionTestOptions {
  liveSessionActive: boolean;
  liveStatus: LiveStatusEvent | null;
  virtualMicStatus: VirtualMicStatus | null;
}

interface ActiveTransmissionResources {
  audioContext: AudioContext;
  captureStream: MediaStream;
  mixedDestination: MediaStreamAudioDestinationNode;
  remoteStream: MediaStream;
  localPeer: RTCPeerConnection;
  remotePeer: RTCPeerConnection;
  remoteAnalyser: AnalyserNode;
  remoteAudio: HTMLAudioElement;
}

const STATS_POLL_MS = 1000;
const CALIBRATION_TIMEOUT_MS = 5000;
const CALIBRATION_TONE_HZ = 1500;

async function queryMicrophonePermission(): Promise<TransmissionPermissionState> {
  if (!navigator.permissions?.query) {
    return "unknown";
  }

  try {
    const status = await navigator.permissions.query({ name: "microphone" as PermissionName });
    if (status.state === "granted" || status.state === "denied" || status.state === "prompt") {
      return status.state;
    }
  } catch {
    return "unknown";
  }

  return "unknown";
}

function createLoopbackPeers(): { localPeer: RTCPeerConnection; remotePeer: RTCPeerConnection } {
  const localPeer = new RTCPeerConnection();
  const remotePeer = new RTCPeerConnection();

  localPeer.onicecandidate = (event) => {
    if (event.candidate) {
      void remotePeer.addIceCandidate(event.candidate);
    }
  };

  remotePeer.onicecandidate = (event) => {
    if (event.candidate) {
      void localPeer.addIceCandidate(event.candidate);
    }
  };

  return { localPeer, remotePeer };
}

async function connectLoopbackPeers(
  localPeer: RTCPeerConnection,
  remotePeer: RTCPeerConnection,
): Promise<void> {
  const offer = await localPeer.createOffer();
  await localPeer.setLocalDescription(offer);
  await remotePeer.setRemoteDescription(offer);

  const answer = await remotePeer.createAnswer();
  await remotePeer.setLocalDescription(answer);
  await localPeer.setRemoteDescription(answer);
}

function extractCodecName(report: RTCStatsReport, codecId?: string | null): string | null {
  if (!codecId) {
    return null;
  }
  const codec = report.get(codecId) as RTCCodecStats | undefined;
  if (!codec) {
    return null;
  }
  return codec.mimeType?.replace("audio/", "") ?? null;
}

function findSelectedCandidatePair(report: RTCStatsReport): RTCIceCandidatePairStats | null {
  for (const stat of report.values()) {
    if (stat.type !== "candidate-pair") {
      continue;
    }
    const candidatePair = stat as RTCIceCandidatePairStats & { selected?: boolean; nominated?: boolean };
    if (candidatePair.selected || candidatePair.nominated) {
      return candidatePair;
    }
  }
  return null;
}

function collectLoopbackStats(
  senderReport: RTCStatsReport,
  receiverReport: RTCStatsReport,
): {
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
} {
  let codecName: string | null = null;
  let sentBytes: number | null = null;
  let receivedBytes: number | null = null;
  let inboundJitterMs: number | null = null;
  let jitterBufferDelayMs: number | null = null;
  let jitterBufferEmittedCount: number | null = null;
  let packetsLost: number | null = null;
  let packetsReceived: number | null = null;
  let concealedSamples: number | null = null;
  let concealmentEvents: number | null = null;

  const selectedPair = findSelectedCandidatePair(senderReport);
  const currentRoundTripTimeMs =
    selectedPair?.currentRoundTripTime != null ? selectedPair.currentRoundTripTime * 1000 : null;

  for (const stat of senderReport.values()) {
    if (stat.type !== "outbound-rtp") {
      continue;
    }
    const outbound = stat as RTCOutboundRtpStreamStats;
    if (outbound.kind !== "audio") {
      continue;
    }
    sentBytes = outbound.bytesSent ?? sentBytes;
    codecName = extractCodecName(senderReport, outbound.codecId) ?? codecName;
  }

  for (const stat of receiverReport.values()) {
    if (stat.type !== "inbound-rtp") {
      continue;
    }
    const inbound = stat as RTCInboundRtpStreamStats;
    if (inbound.kind !== "audio") {
      continue;
    }
    receivedBytes = inbound.bytesReceived ?? receivedBytes;
    inboundJitterMs = inbound.jitter != null ? inbound.jitter * 1000 : inboundJitterMs;
    jitterBufferDelayMs =
      inbound.jitterBufferDelay != null ? inbound.jitterBufferDelay * 1000 : jitterBufferDelayMs;
    jitterBufferEmittedCount = inbound.jitterBufferEmittedCount ?? jitterBufferEmittedCount;
    packetsLost = inbound.packetsLost ?? packetsLost;
    packetsReceived = inbound.packetsReceived ?? packetsReceived;
    concealedSamples = inbound.concealedSamples ?? concealedSamples;
    concealmentEvents = inbound.concealmentEvents ?? concealmentEvents;
    codecName = extractCodecName(receiverReport, inbound.codecId) ?? codecName;
  }

  return {
    currentRoundTripTimeMs,
    inboundJitterMs,
    jitterBufferDelayMs,
    jitterBufferEmittedCount,
    packetsLost,
    packetsReceived,
    concealedSamples,
    concealmentEvents,
    sentBytes,
    receivedBytes,
    codecName,
  };
}

export function useTransmissionTest({
  liveSessionActive,
  liveStatus,
  virtualMicStatus,
}: UseTransmissionTestOptions) {
  const [transmissionTestState, setTransmissionTestState] = useState<TransmissionTestState>("idle");
  const [transmissionMetrics, setTransmissionMetrics] =
    useState<TransmissionMetricsSnapshot>(INITIAL_TRANSMISSION_METRICS);
  const [transmissionCalibration, setTransmissionCalibration] =
    useState<TransmissionCalibrationResult>(INITIAL_TRANSMISSION_CALIBRATION);
  const [playReceivedAudio, setPlayReceivedAudio] = useState(true);

  const resourcesRef = useRef<ActiveTransmissionResources | null>(null);
  const statsRef = useRef<TransmissionStatsAggregate>(INITIAL_TRANSMISSION_STATS);
  const statsTimerRef = useRef<number | null>(null);
  const meterFrameRef = useRef<number | null>(null);
  const sessionStartedAtRef = useRef<number | null>(null);
  const playReceivedAudioRef = useRef(playReceivedAudio);

  useEffect(() => {
    playReceivedAudioRef.current = playReceivedAudio;
    if (resourcesRef.current) {
      resourcesRef.current.remoteAudio.muted = !playReceivedAudio;
      if (playReceivedAudio) {
        void resourcesRef.current.remoteAudio.play().catch(() => undefined);
      } else {
        resourcesRef.current.remoteAudio.pause();
      }
    }
  }, [playReceivedAudio]);

  useEffect(() => {
    setTransmissionMetrics((current) =>
      mergeTransmissionMetrics(current, {
        ...createAppLiveMetricsPatch(liveStatus, transmissionCalibration),
        combinedEstimateMs: deriveCombinedEstimateMs(
          liveStatus?.estimatedLatencyMs ?? null,
          current.networkLoopbackEstimateMs,
        ),
      }),
    );
  }, [liveStatus, transmissionCalibration]);

  const stopTransmissionTest = useCallback(async () => {
    if (meterFrameRef.current != null) {
      cancelAnimationFrame(meterFrameRef.current);
      meterFrameRef.current = null;
    }
    if (statsTimerRef.current != null) {
      window.clearInterval(statsTimerRef.current);
      statsTimerRef.current = null;
    }

    const resources = resourcesRef.current;
    resourcesRef.current = null;
    statsRef.current = INITIAL_TRANSMISSION_STATS;
    sessionStartedAtRef.current = null;

    if (resources) {
      resources.captureStream.getTracks().forEach((track) => track.stop());
      resources.remoteStream.getTracks().forEach((track) => track.stop());
      resources.localPeer.close();
      resources.remotePeer.close();
      resources.remoteAudio.pause();
      resources.remoteAudio.srcObject = null;
      await resources.audioContext.close().catch(() => undefined);
    }

    setTransmissionCalibration((current) =>
      current.status === "running" ? INITIAL_TRANSMISSION_CALIBRATION : current,
    );
    setTransmissionTestState("idle");
    setTransmissionMetrics((current) =>
      mergeTransmissionMetrics(INITIAL_TRANSMISSION_METRICS, {
        appLiveLatencyMs: current.appLiveLatencyMs,
        queueDepthMs: current.queueDepthMs,
        inferenceP95Ms: current.inferenceP95Ms,
        realtimeHealth: current.realtimeHealth,
        calibratedLoopbackMs: current.calibratedLoopbackMs,
      }),
    );
  }, []);

  useEffect(() => {
    if (
      !liveSessionActive
      && (transmissionTestState === "running"
        || transmissionTestState === "calibrating"
        || transmissionTestState === "requestingPermission")
    ) {
      void stopTransmissionTest();
    }
  }, [liveSessionActive, stopTransmissionTest, transmissionTestState]);

  const startMeterLoop = useCallback(() => {
    const render = () => {
      const resources = resourcesRef.current;
      if (!resources) {
        return;
      }

      const timeDomain = new Uint8Array(resources.remoteAnalyser.fftSize);
      const frequencyData = new Uint8Array(resources.remoteAnalyser.frequencyBinCount);
      resources.remoteAnalyser.getByteTimeDomainData(timeDomain);
      resources.remoteAnalyser.getByteFrequencyData(frequencyData);
      const { rms, peak } = computeRmsAndPeak(timeDomain);

      setTransmissionMetrics((current) =>
        mergeTransmissionMetrics(current, {
          receivedRms: rms,
          receivedPeak: peak,
          receivedWaveform: createTransmissionWaveform(frequencyData),
          sessionSeconds: sessionStartedAtRef.current
            ? Math.max(0, (performance.now() - sessionStartedAtRef.current) / 1000)
            : current.sessionSeconds,
        }),
      );

      meterFrameRef.current = requestAnimationFrame(render);
    };

    meterFrameRef.current = requestAnimationFrame(render);
  }, []);

  const startStatsLoop = useCallback(() => {
    const poll = async () => {
      const resources = resourcesRef.current;
      if (!resources) {
        return;
      }

      try {
        const [senderReport, receiverReport] = await Promise.all([
          resources.localPeer.getStats(),
          resources.remotePeer.getStats(),
        ]);
        setTransmissionMetrics((current) => {
          const next = applyTransmissionStatsSample(
            current,
            statsRef.current,
            collectLoopbackStats(senderReport, receiverReport),
            performance.now(),
          );
          statsRef.current = next.aggregate;
          return mergeTransmissionMetrics(next.metrics, {
            appLiveLatencyMs: current.appLiveLatencyMs,
            queueDepthMs: current.queueDepthMs,
            inferenceP95Ms: current.inferenceP95Ms,
            realtimeHealth: current.realtimeHealth,
            calibratedLoopbackMs: transmissionCalibration.calibratedLoopbackMs ?? current.calibratedLoopbackMs,
          });
        });
      } catch (error) {
        setTransmissionTestState("error");
        setTransmissionMetrics((current) =>
          mergeTransmissionMetrics(current, {
            message: error instanceof Error ? error.message : "Unable to poll WebRTC stats.",
          }),
        );
      }
    };

    void poll();
    statsTimerRef.current = window.setInterval(() => {
      void poll();
    }, STATS_POLL_MS);
  }, [transmissionCalibration.calibratedLoopbackMs]);

  const startTransmissionTest = useCallback(async () => {
    if (!liveSessionActive) {
      setTransmissionTestState("error");
      setTransmissionMetrics((current) =>
        mergeTransmissionMetrics(current, {
          message: "Start a desktop live suppression session before running the transmission test.",
        }),
      );
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
      setTransmissionTestState("error");
      setTransmissionMetrics((current) =>
        mergeTransmissionMetrics(current, {
          message: "This desktop webview does not expose microphone capture and WebRTC loopback APIs.",
        }),
      );
      return;
    }

    await stopTransmissionTest();
    setTransmissionTestState("requestingPermission");
    setTransmissionCalibration(INITIAL_TRANSMISSION_CALIBRATION);

    try {
      let permissionState = await queryMicrophonePermission();
      let devices = await navigator.mediaDevices.enumerateDevices();
      let targetDevice = resolveTransmissionRecordingDevice(devices, virtualMicStatus);

      if (!targetDevice || devices.every((device) => !device.label)) {
        const primingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        primingStream.getTracks().forEach((track) => track.stop());
        permissionState = "granted";
        devices = await navigator.mediaDevices.enumerateDevices();
        targetDevice = resolveTransmissionRecordingDevice(devices, virtualMicStatus);
      }

      if (!targetDevice) {
        setTransmissionTestState("error");
        setTransmissionMetrics((current) =>
          mergeTransmissionMetrics(current, {
            permissionState,
            message: `VB-CABLE recording endpoint '${virtualMicStatus?.recordingDeviceName ?? "CABLE Output"}' was not found as a browser audio input.`,
          }),
        );
        return;
      }

      const captureStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: { exact: targetDevice.deviceId },
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          channelCount: 1,
          latency: 0,
        },
      });
      permissionState = "granted";

      const audioContext = new AudioContext({ latencyHint: "interactive" });
      const captureSource = audioContext.createMediaStreamSource(captureStream);
      const mixedDestination = audioContext.createMediaStreamDestination();
      captureSource.connect(mixedDestination);

      const { localPeer, remotePeer } = createLoopbackPeers();
      const remoteStream = new MediaStream();
      const remoteTrackReady = new Promise<MediaStream>((resolve) => {
        remotePeer.ontrack = (event) => {
          const stream = event.streams[0] ?? new MediaStream([event.track]);
          for (const track of stream.getTracks()) {
            if (!remoteStream.getTracks().some((existing) => existing.id === track.id)) {
              remoteStream.addTrack(track);
            }
          }
          resolve(stream);
        };
      });

      mixedDestination.stream.getTracks().forEach((track) => {
        localPeer.addTrack(track, mixedDestination.stream);
      });
      await connectLoopbackPeers(localPeer, remotePeer);
      const remoteInputStream = await remoteTrackReady;

      const remoteAudio = new Audio();
      remoteAudio.autoplay = true;
      remoteAudio.muted = !playReceivedAudioRef.current;
      remoteAudio.srcObject = remoteStream;
      if (playReceivedAudioRef.current) {
        await remoteAudio.play().catch(() => undefined);
      }

      const remoteSource = audioContext.createMediaStreamSource(remoteInputStream);
      const remoteAnalyser = audioContext.createAnalyser();
      remoteAnalyser.fftSize = 512;
      remoteAnalyser.smoothingTimeConstant = 0.75;
      remoteSource.connect(remoteAnalyser);

      resourcesRef.current = {
        audioContext,
        captureStream,
        mixedDestination,
        remoteStream,
        localPeer,
        remotePeer,
        remoteAnalyser,
        remoteAudio,
      };

      statsRef.current = INITIAL_TRANSMISSION_STATS;
      sessionStartedAtRef.current = performance.now();
      const trackSettings = captureStream.getAudioTracks()[0]?.getSettings?.();

      setTransmissionMetrics((current) =>
        mergeTransmissionMetrics(current, {
          ...createAppLiveMetricsPatch(liveStatus, INITIAL_TRANSMISSION_CALIBRATION),
          captureDeviceId: targetDevice.deviceId,
          captureDeviceName: targetDevice.label || virtualMicStatus?.recordingDeviceName || "VB-CABLE input",
          captureSettings: {
            channelCount: trackSettings?.channelCount ?? null,
            latency: trackSettings?.latency ?? null,
            sampleRate: trackSettings?.sampleRate ?? null,
            sampleSize: trackSettings?.sampleSize ?? null,
          },
          permissionState,
          message: "Capturing the VB-CABLE mic endpoint through a WebRTC loopback.",
        }),
      );

      setTransmissionTestState("running");
      startMeterLoop();
      startStatsLoop();
    } catch (error) {
      const denied = error instanceof DOMException && error.name === "NotAllowedError";
      setTransmissionTestState("error");
      setTransmissionMetrics((current) =>
        mergeTransmissionMetrics(current, {
          permissionState: denied ? "denied" : current.permissionState,
          message:
            error instanceof Error
              ? error.message
              : "Unable to start the transmission loopback test.",
        }),
      );
    }
  }, [liveSessionActive, liveStatus, startMeterLoop, startStatsLoop, stopTransmissionTest, virtualMicStatus]);

  const runTransmissionCalibration = useCallback(async () => {
    const resources = resourcesRef.current;
    if (!resources) {
      setTransmissionTestState("error");
      setTransmissionMetrics((current) =>
        mergeTransmissionMetrics(current, {
          message: "Start the transmission loopback before running calibration.",
        }),
      );
      return;
    }

    setTransmissionTestState("calibrating");
    const startedAtMs = performance.now();
    setTransmissionCalibration({
      status: "running",
      startedAtMs,
      completedAtMs: null,
      calibratedLoopbackMs: null,
      message: "Injecting a short calibration ping into the loopback stream.",
    });

    const analyser = resources.remoteAnalyser;
    const frequencyData = new Uint8Array(analyser.frequencyBinCount);
    const toneIndex = Math.max(
      1,
      Math.round((CALIBRATION_TONE_HZ / (resources.audioContext.sampleRate / 2)) * analyser.frequencyBinCount),
    );

    const oscillator = resources.audioContext.createOscillator();
    const gainNode = resources.audioContext.createGain();
    gainNode.gain.setValueAtTime(0.0001, resources.audioContext.currentTime);
    oscillator.frequency.setValueAtTime(CALIBRATION_TONE_HZ, resources.audioContext.currentTime);
    oscillator.type = "sine";
    oscillator.connect(gainNode);
    gainNode.connect(resources.mixedDestination);

    const scheduledStart = resources.audioContext.currentTime + 0.05;
    gainNode.gain.linearRampToValueAtTime(0.7, scheduledStart + 0.01);
    gainNode.gain.linearRampToValueAtTime(0.0001, scheduledStart + 0.1);
    oscillator.start(scheduledStart);
    oscillator.stop(scheduledStart + 0.12);

    await new Promise<void>((resolve) => {
      let finished = false;
      const detectionStart = performance.now() + 45;

      const conclude = (result: TransmissionCalibrationResult) => {
        if (finished) {
          return;
        }
        finished = true;
        setTransmissionCalibration(result);
        setTransmissionTestState("running");
        setTransmissionMetrics((current) =>
          mergeTransmissionMetrics(current, {
            calibratedLoopbackMs: result.calibratedLoopbackMs ?? null,
            combinedEstimateMs:
              current.networkLoopbackEstimateMs != null
                ? (current.appLiveLatencyMs ?? 0) + current.networkLoopbackEstimateMs
                : current.combinedEstimateMs,
            message: result.message,
          }),
        );
        resolve();
      };

      const timeout = window.setTimeout(() => {
        conclude({
          status: "failed",
          startedAtMs,
          completedAtMs: performance.now(),
          calibratedLoopbackMs: null,
          message: "Calibration tone was not detected on the received loopback stream.",
        });
      }, CALIBRATION_TIMEOUT_MS);

      const detect = () => {
        if (finished) {
          return;
        }
        analyser.getByteFrequencyData(frequencyData);
        const toneValue = frequencyData[Math.min(toneIndex, frequencyData.length - 1)] ?? 0;
        if (performance.now() >= detectionStart && toneValue >= 160) {
          window.clearTimeout(timeout);
          conclude({
            status: "completed",
            startedAtMs,
            completedAtMs: performance.now(),
            calibratedLoopbackMs: Math.max(0, performance.now() - detectionStart),
            message: "Calibration tone detected on the received loopback stream.",
          });
          return;
        }
        requestAnimationFrame(detect);
      };

      requestAnimationFrame(detect);
    });
  }, []);

  const transmissionReady = useMemo(
    () => Boolean(virtualMicStatus?.recordingDeviceName),
    [virtualMicStatus?.recordingDeviceName],
  );

  return {
    transmissionReady,
    transmissionTestState,
    transmissionMetrics,
    transmissionCalibration,
    playReceivedAudio,
    setPlayReceivedAudio,
    startTransmissionTest,
    stopTransmissionTest,
    runTransmissionCalibration,
  };
}
