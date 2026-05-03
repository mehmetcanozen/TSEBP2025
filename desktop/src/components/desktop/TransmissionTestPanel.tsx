import SignalMeter from "@/components/desktop/SignalMeter";
import { useDesktopRuntime } from "@/contexts/DesktopRuntimeContext";
import { Activity, RadioTower, RefreshCw } from "lucide-react";

const formatMillis = (value?: number | null, digits = 0) => {
  if (value == null || Number.isNaN(value)) {
    return "--";
  }
  return `${value.toFixed(digits)} ms`;
};

const formatRate = (value?: number | null, digits = 1, suffix = "kbps") => {
  if (value == null || Number.isNaN(value)) {
    return "--";
  }
  return `${value.toFixed(digits)} ${suffix}`;
};

const formatPercent = (value?: number | null) => {
  if (value == null || Number.isNaN(value)) {
    return "--";
  }
  return `${(value * 100).toFixed(1)}%`;
};

const formatSeconds = (value?: number | null) => {
  if (value == null || Number.isNaN(value)) {
    return "--";
  }
  return `${value.toFixed(1)} s`;
};

const stateTone = (state: string) => {
  switch (state) {
    case "running":
    case "ready":
      return "border-accent/35 bg-accent/15 text-accent";
    case "calibrating":
      return "border-primary/35 bg-primary/12 text-primary";
    case "error":
      return "border-destructive/35 bg-destructive/12 text-destructive";
    case "requestingPermission":
      return "border-[hsl(var(--neon-orange))]/35 bg-[hsl(var(--neon-orange))]/12 text-[hsl(var(--neon-orange))]";
    default:
      return "border-border bg-muted/35 text-muted-foreground";
  }
};

const TransmissionTestPanel = () => {
  const {
    desktopMode,
    debugInputEnabled,
    liveStatus,
    activeLiveSessionId,
    virtualMicStatus,
    transmissionReady,
    transmissionTestState,
    transmissionMetrics,
    transmissionCalibration,
    playReceivedAudio,
    setPlayReceivedAudio,
    startTransmissionTest,
    stopTransmissionTest,
    runTransmissionCalibration,
    refreshVirtualMicStatus,
  } = useDesktopRuntime();

  const liveModeLabel = desktopMode === "speakerSuppression" ? "speaker" : "semantic";
  const liveSessionReady = Boolean(activeLiveSessionId) && liveStatus?.state === "running";
  const canStartTransmission =
    liveSessionReady
    && transmissionReady
    && transmissionTestState !== "requestingPermission"
    && transmissionTestState !== "running"
    && transmissionTestState !== "calibrating";
  const canStopTransmission =
    transmissionTestState === "running"
    || transmissionTestState === "calibrating"
    || transmissionTestState === "requestingPermission";
  const canCalibrate = transmissionTestState === "running";

  return (
    <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
      <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
              Transmission Test
            </div>
            <h2 className="mt-2 text-2xl font-semibold text-foreground">
              VB-CABLE mic -&gt; WebRTC loopback -&gt; local playback
            </h2>
            <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
              Captures the same VB-CABLE recording endpoint a real target app would use, sends it through a local
              WebRTC hop, and lets us inspect timing and transport behavior on the desktop.
            </p>
          </div>
          <div
            className={`rounded-full border px-3 py-1 text-[11px] font-mono uppercase tracking-[0.18em] ${stateTone(transmissionTestState)}`}
          >
            {transmissionTestState}
          </div>
        </div>

        <div className="mt-5 rounded-2xl border border-border bg-muted/30 p-4">
          <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-center">
            <div>
              <div className="text-sm font-semibold text-foreground">Observed route</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {debugInputEnabled
                  ? `Debug WAV ${liveModeLabel} realtime writes into ${virtualMicStatus?.recordingDeviceName ?? "CABLE Output"}, then the browser loopback captures it.`
                  : `Live mic ${liveModeLabel} realtime writes into ${virtualMicStatus?.recordingDeviceName ?? "CABLE Output"}, then the browser loopback captures it.`}
              </div>
            </div>
            <div className="rounded-xl border border-primary/25 bg-primary/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary">
              same-machine loopback
            </div>
          </div>
          <div className="mt-3 rounded-xl border border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground">
            Captured browser input: {transmissionMetrics.captureDeviceName ?? (virtualMicStatus?.recordingDeviceName || "--")}
          </div>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-border bg-muted/30 p-4">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-background">
                <RadioTower className="h-4 w-4" />
              </span>
              <div>
                <div className="text-sm font-semibold text-foreground">Capture status</div>
                <div className="text-xs text-muted-foreground">
                  {!transmissionReady
                    ? "VB-CABLE recording endpoint is not available to the desktop app yet."
                    : liveSessionReady
                      ? "A live desktop suppression route is active."
                      : "Start semantic or speaker realtime first."}
                </div>
              </div>
            </div>
            <div className="mt-4 grid gap-2 text-sm text-muted-foreground">
              <div className="flex items-center justify-between gap-4">
                <span>Permission</span>
                <span className="font-mono text-foreground/80">{transmissionMetrics.permissionState}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Capture rate</span>
                <span className="font-mono text-foreground/80">
                  {transmissionMetrics.captureSettings?.sampleRate
                    ? `${transmissionMetrics.captureSettings.sampleRate} Hz`
                    : "--"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Channels</span>
                <span className="font-mono text-foreground/80">
                  {transmissionMetrics.captureSettings?.channelCount ?? "--"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Session</span>
                <span className="font-mono text-foreground/80">{formatSeconds(transmissionMetrics.sessionSeconds)}</span>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-muted/30 p-4">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-background">
                <Activity className="h-4 w-4" />
              </span>
              <div>
                <div className="text-sm font-semibold text-foreground">Calibration</div>
                <div className="text-xs text-muted-foreground">
                  Short explicit tone injection for a stronger loopback-delay reading.
                </div>
              </div>
            </div>
            <div className="mt-4 grid gap-2 text-sm text-muted-foreground">
              <div className="flex items-center justify-between gap-4">
                <span>Status</span>
                <span className="font-mono text-foreground/80">{transmissionCalibration.status}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Measured delay</span>
                <span className="font-mono text-foreground/80">
                  {formatMillis(transmissionCalibration.calibratedLoopbackMs)}
                </span>
              </div>
              <div className="flex items-start justify-between gap-4">
                <span>Note</span>
                <span className="max-w-[65%] text-right text-foreground/80">
                  {transmissionCalibration.message ?? "Run ping calibration after the loopback is live."}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void startTransmissionTest()}
            disabled={!canStartTransmission}
            title={!liveSessionReady ? "Start semantic or speaker realtime first." : undefined}
            className="rounded-2xl border border-accent/35 bg-accent px-5 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {liveSessionReady ? "Start loopback test" : "Start live route first"}
          </button>
          <button
            type="button"
            onClick={() => void stopTransmissionTest()}
            disabled={!canStopTransmission}
            className="rounded-2xl border border-border bg-card px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-destructive/35 hover:bg-destructive/8 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Stop test
          </button>
          <button
            type="button"
            onClick={() => setPlayReceivedAudio(!playReceivedAudio)}
            disabled={transmissionTestState === "idle" || transmissionTestState === "requestingPermission"}
            className={`rounded-2xl border px-5 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
              playReceivedAudio
                ? "border-primary/35 bg-primary/12 text-primary"
                : "border-border bg-card text-foreground"
            }`}
          >
            {playReceivedAudio ? "Pause received audio" : "Play received audio"}
          </button>
          <button
            type="button"
            onClick={() => void runTransmissionCalibration()}
            disabled={!canCalibrate}
            className="rounded-2xl border border-border bg-card px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Run ping calibration
          </button>
          <button
            type="button"
            onClick={() => void refreshVirtualMicStatus()}
            className="flex items-center gap-2 rounded-2xl border border-border bg-card px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh cable
          </button>
        </div>

        <div
          className={`mt-4 rounded-2xl border px-4 py-3 text-sm ${
            transmissionReady
              ? liveSessionReady
                ? "border-primary/20 bg-primary/8 text-muted-foreground"
                : "border-border bg-muted/30 text-muted-foreground"
              : "border-destructive/25 bg-destructive/10 text-destructive"
          }`}
        >
          {transmissionMetrics.message
            ?? (!transmissionReady
              ? "VB-CABLE recording endpoint is not ready for browser capture yet."
              : !liveSessionReady
                ? "VB-CABLE browser capture is available. Start semantic or speaker realtime, then run the loopback test."
                : "The browser loopback will capture the VB-CABLE mic endpoint, not your real microphone.")}
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <div className="rounded-2xl border border-border bg-muted/30 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.16em] text-muted-foreground">App live</div>
            <div className="mt-3 grid gap-2 text-sm text-muted-foreground">
              <div className="flex items-center justify-between gap-4">
                <span>Estimated latency</span>
                <span className="font-mono text-foreground/80">{formatMillis(transmissionMetrics.appLiveLatencyMs)}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Queue depth</span>
                <span className="font-mono text-foreground/80">{formatMillis(transmissionMetrics.queueDepthMs)}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Inference p95</span>
                <span className="font-mono text-foreground/80">{formatMillis(transmissionMetrics.inferenceP95Ms)}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Health</span>
                <span className="font-mono text-foreground/80">{transmissionMetrics.realtimeHealth}</span>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-muted/30 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.16em] text-muted-foreground">WebRTC path</div>
            <div className="mt-3 grid gap-2 text-sm text-muted-foreground">
              <div className="flex items-center justify-between gap-4">
                <span>RTT current</span>
                <span className="font-mono text-foreground/80">{formatMillis(transmissionMetrics.currentRoundTripTimeMs)}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>RTT avg / max</span>
                <span className="font-mono text-foreground/80">
                  {formatMillis(transmissionMetrics.averageRoundTripTimeMs)} / {formatMillis(transmissionMetrics.maxRoundTripTimeMs)}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Inbound jitter</span>
                <span className="font-mono text-foreground/80">{formatMillis(transmissionMetrics.inboundJitterMs, 1)}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Jitter buffer</span>
                <span className="font-mono text-foreground/80">{formatMillis(transmissionMetrics.avgJitterBufferDelayMs, 1)}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Codec</span>
                <span className="font-mono text-foreground/80">{transmissionMetrics.codecName ?? "--"}</span>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-muted/30 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.16em] text-muted-foreground">Transport health</div>
            <div className="mt-3 grid gap-2 text-sm text-muted-foreground">
              <div className="flex items-center justify-between gap-4">
                <span>Packets lost</span>
                <span className="font-mono text-foreground/80">
                  {transmissionMetrics.packetsLost ?? "--"} / {formatPercent(transmissionMetrics.packetLossRate)}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Concealed samples</span>
                <span className="font-mono text-foreground/80">{transmissionMetrics.concealedSamples ?? "--"}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Concealment events</span>
                <span className="font-mono text-foreground/80">{transmissionMetrics.concealmentEvents ?? "--"}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Send / receive</span>
                <span className="font-mono text-foreground/80">
                  {formatRate(transmissionMetrics.sendBitrateKbps)} / {formatRate(transmissionMetrics.receiveBitrateKbps)}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Combined estimate</span>
                <span className="font-mono text-foreground/80">{formatMillis(transmissionMetrics.combinedEstimateMs)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
        <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
          Loopback Monitor
        </div>
        <h2 className="mt-2 text-2xl font-semibold text-foreground">Received stream</h2>

        <div className="mt-5">
          <SignalMeter
            title="webrtc receive"
            waveform={transmissionMetrics.receivedWaveform}
            peak={transmissionMetrics.receivedPeak}
            rms={transmissionMetrics.receivedRms}
            accentClass="bg-gradient-to-t from-[hsl(var(--primary))] to-[hsl(var(--accent))]"
          />
        </div>

        <div className="mt-5 grid gap-3 text-sm text-muted-foreground">
          <div className="flex items-center justify-between gap-4">
            <span>Route source</span>
            <span className="font-mono text-foreground/80">{debugInputEnabled ? "Debug WAV" : "Live mic"}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span>Desktop mode</span>
            <span className="font-mono text-foreground/80">{liveModeLabel}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span>Network estimate</span>
            <span className="font-mono text-foreground/80">{formatMillis(transmissionMetrics.networkLoopbackEstimateMs)}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span>Calibrated loopback</span>
            <span className="font-mono text-foreground/80">{formatMillis(transmissionMetrics.calibratedLoopbackMs)}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span>Playback</span>
            <span className="font-mono text-foreground/80">{playReceivedAudio ? "local speakers" : "muted"}</span>
          </div>
        </div>
      </div>
    </section>
  );
};

export default TransmissionTestPanel;
