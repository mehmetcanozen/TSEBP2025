import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { useTransmissionTest } from "@/hooks/useTransmissionTest";
import {
  applyTransmissionStatsSample,
  INITIAL_TRANSMISSION_CALIBRATION,
  INITIAL_TRANSMISSION_METRICS,
  INITIAL_TRANSMISSION_STATS,
  resolveTransmissionRecordingDevice,
} from "@/lib/transmission-test";

const virtualMicStatus = {
  provider: "VB-CABLE",
  installed: true,
  playbackDeviceId: "playback-1",
  playbackDeviceName: "Speakers (VB-Audio Virtual Cable)",
  recordingDeviceName: "CABLE Output (VB-Audio Virtual Cable)",
  setupUrl: "https://vb-audio.com/Cable/",
  message: "ready",
};

describe("transmission-test helpers", () => {
  it("resolves the VB-CABLE recording endpoint from browser device labels", () => {
    const devices = [
      { deviceId: "mic-1", kind: "audioinput", label: "Microphone (Realtek)", groupId: "g1", toJSON: () => ({}) },
      {
        deviceId: "cable-1",
        kind: "audioinput",
        label: "CABLE Output (2- VB-Audio Virtual Cable)",
        groupId: "g2",
        toJSON: () => ({}),
      },
    ] as MediaDeviceInfo[];

    const resolved = resolveTransmissionRecordingDevice(devices, virtualMicStatus);
    expect(resolved?.deviceId).toBe("cable-1");
  });

  it("derives network metrics and bitrate from WebRTC stats samples", () => {
    const result = applyTransmissionStatsSample(
      INITIAL_TRANSMISSION_METRICS,
      {
        ...INITIAL_TRANSMISSION_STATS,
        lastSentBytes: 1000,
        lastReceivedBytes: 2000,
        lastStatsAtMs: 1000,
      },
      {
        currentRoundTripTimeMs: 40,
        inboundJitterMs: 6,
        jitterBufferDelayMs: 120,
        jitterBufferEmittedCount: 4,
        packetsLost: 2,
        packetsReceived: 98,
        concealedSamples: 512,
        concealmentEvents: 3,
        sentBytes: 5000,
        receivedBytes: 10000,
        codecName: "opus",
      },
      2000,
    );

    expect(result.metrics.averageRoundTripTimeMs).toBe(40);
    expect(result.metrics.avgJitterBufferDelayMs).toBe(30);
    expect(result.metrics.packetLossRate).toBeCloseTo(0.02, 6);
    expect(result.metrics.sendBitrateKbps).toBe(32);
    expect(result.metrics.receiveBitrateKbps).toBe(64);
    expect(result.metrics.networkLoopbackEstimateMs).toBe(50);
    expect(result.metrics.codecName).toBe("opus");
  });
});

describe("useTransmissionTest", () => {
  const originalMediaDevices = navigator.mediaDevices;
  const originalPermissions = navigator.permissions;
  const originalRtcPeerConnection = window.RTCPeerConnection;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: originalMediaDevices,
    });
    Object.defineProperty(navigator, "permissions", {
      configurable: true,
      value: originalPermissions,
    });
    Object.defineProperty(window, "RTCPeerConnection", {
      configurable: true,
      value: originalRtcPeerConnection,
    });
  });

  it("moves to error when no live session is active", async () => {
    const { result } = renderHook(() =>
      useTransmissionTest({
        liveSessionActive: false,
        liveStatus: null,
        virtualMicStatus,
      }),
    );

    await act(async () => {
      await result.current.startTransmissionTest();
    });

    expect(result.current.transmissionTestState).toBe("error");
    expect(result.current.transmissionMetrics.message).toContain("Start a desktop live suppression session");

    await act(async () => {
      await result.current.stopTransmissionTest();
    });

    expect(result.current.transmissionTestState).toBe("idle");
  });

  it("surfaces microphone permission denial cleanly", async () => {
    Object.defineProperty(window, "RTCPeerConnection", {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(navigator, "permissions", {
      configurable: true,
      value: {
        query: vi.fn().mockResolvedValue({ state: "prompt" }),
      },
    });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        enumerateDevices: vi.fn().mockResolvedValue([
          {
            deviceId: "cable-1",
            kind: "audioinput",
            label: "CABLE Output (VB-Audio Virtual Cable)",
            groupId: "g2",
            toJSON: () => ({}),
          },
        ]),
        getUserMedia: vi.fn().mockRejectedValue(new DOMException("denied", "NotAllowedError")),
      },
    });

    const { result } = renderHook(() =>
      useTransmissionTest({
        liveSessionActive: true,
        liveStatus: null,
        virtualMicStatus,
      }),
    );

    await act(async () => {
      await result.current.startTransmissionTest();
    });

    await waitFor(() => {
      expect(result.current.transmissionTestState).toBe("error");
    });
    expect(result.current.transmissionMetrics.permissionState).toBe("denied");
  });
});
