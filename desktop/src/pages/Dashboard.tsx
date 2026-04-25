import HeaderBar from "@/components/HeaderBar";
import CategorySelector from "@/components/desktop/CategorySelector";
import PresetStrip from "@/components/desktop/PresetStrip";
import SignalMeter from "@/components/desktop/SignalMeter";
import { useDesktopRuntime } from "@/contexts/DesktopRuntimeContext";

const formatMillis = (value?: number | null) => {
  if (value == null || Number.isNaN(value)) {
    return "--";
  }
  return `${value.toFixed(0)} ms`;
};

const healthTone = (health?: string | null) => {
  switch (health) {
    case "ok":
      return "text-accent";
    case "warning":
      return "text-[hsl(var(--neon-orange))]";
    case "overloaded":
      return "text-destructive";
    default:
      return "text-muted-foreground";
  }
};

const Dashboard = () => {
  const {
    categories,
    presets,
    devices,
    runtimeMetrics,
    virtualMicStatus,
    selectedCategories,
    aggressiveness,
    lookaheadMs,
    outputMode,
    inputDeviceId,
    outputDeviceId,
    inputPath,
    outputPath,
    debugInputEnabled,
    debugInputPath,
    recordEnabled,
    recordOutputPath,
    liveStatus,
    liveMeter,
    offlineProgress,
    activeLiveSessionId,
    activeOfflineJobId,
    isLoading,
    isStartingLive,
    isOfflineRunning,
    error,
    toggleCategory,
    applyPreset,
    setAggressiveness,
    setLookaheadMs,
    setOutputMode,
    setInputDeviceId,
    setOutputDeviceId,
    setInputPath,
    setOutputPath,
    setDebugInputEnabled,
    setDebugInputPath,
    setRecordEnabled,
    setRecordOutputPath,
    browseInputPath,
    browseOutputPath,
    browseDebugInputPath,
    browseRecordOutputPath,
    refreshDevices,
    refreshVirtualMicStatus,
    refreshRuntimeMetrics,
    startOffline,
    cancelOffline,
    startLive,
    stopLive,
    clearError,
  } = useDesktopRuntime();

  const inputDevices = devices.filter((device) => device.direction === "input");
  const outputDevices = devices.filter((device) => device.direction === "output");
  const virtualMicReady = Boolean(virtualMicStatus?.installed && virtualMicStatus.playbackDeviceId);
  const virtualMicPlaybackName = virtualMicStatus?.playbackDeviceName ?? "CABLE Input";
  const virtualMicRecordingName = virtualMicStatus?.recordingDeviceName ?? "CABLE Output";
  const liveStartDisabled = isStartingLive || isLoading || (outputMode === "virtualMic" && !virtualMicReady);
  const liveTitle = outputMode === "virtualMic"
    ? "Mic -> suppress -> virtual mic"
    : "Mic -> suppress -> monitor";

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background transition-colors duration-300">
      <HeaderBar />

      <main className="flex-1 overflow-y-auto px-5 py-5">
        <div className="mx-auto flex max-w-7xl flex-col gap-5">
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
              <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                Runtime
              </div>
              <div className="mt-3 text-2xl font-semibold text-foreground">
                {runtimeMetrics?.provider ?? "loading"}
              </div>
              <div className="mt-2 text-sm text-muted-foreground">
                {runtimeMetrics?.warmed ? "session warmed" : "awaiting warmup"}
              </div>
            </div>

            <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
              <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                Live Queue
              </div>
              <div className="mt-3 text-2xl font-semibold text-foreground">
                {formatMillis(liveStatus?.queueDepthMs)}
              </div>
              <div className="mt-2 text-sm text-muted-foreground">
                <span className={healthTone(liveStatus?.realtimeHealth)}>
                  {liveStatus?.realtimeHealth ?? "idle"}
                </span>{" "}
                / xruns {liveStatus?.xruns ?? 0}
              </div>
            </div>

            <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
              <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                Inference
              </div>
              <div className="mt-3 text-2xl font-semibold text-foreground">
                {formatMillis(liveStatus?.inferenceMs)}
              </div>
              <div className="mt-2 text-sm text-muted-foreground">
                estimated {formatMillis(liveStatus?.estimatedLatencyMs)} / lookahead {lookaheadMs} ms
              </div>
            </div>

            <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
              <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                Targets
              </div>
              <div className="mt-3 text-2xl font-semibold text-foreground">
                {selectedCategories.length}
              </div>
              <div className="mt-2 text-sm text-muted-foreground">
                active model categories selected
              </div>
            </div>
          </section>

          {error && (
            <section className="rounded-2xl border border-destructive/35 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              <div className="flex items-center justify-between gap-4">
                <span>{error}</span>
                <button
                  type="button"
                  onClick={clearError}
                  className="rounded-lg border border-destructive/35 px-2 py-1 text-xs font-semibold uppercase tracking-wide"
                >
                  dismiss
                </button>
              </div>
            </section>
          )}

          <section className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
            <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                    Model Target Surface
                  </div>
                  <h2 className="mt-2 text-2xl font-semibold text-foreground">
                    Live suppression profile
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                    The desktop app now reads its target surface and presets from the packaged model definition, and
                    the same selection drives both offline and live processing.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    void refreshDevices();
                    void refreshRuntimeMetrics();
                  }}
                  className="rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-foreground/80 transition-colors hover:border-primary/30 hover:bg-primary/10"
                >
                  refresh
                </button>
              </div>

              <div className="mt-5">
                <PresetStrip
                  presets={presets}
                  selectedCategories={selectedCategories}
                  onApply={applyPreset}
                />
              </div>

              <div className="mt-5">
                <CategorySelector
                  categories={categories}
                  selected={selectedCategories}
                  onToggle={toggleCategory}
                />
              </div>
            </div>

            <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
              <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                Shared Controls
              </div>
              <h2 className="mt-2 text-2xl font-semibold text-foreground">Inference tuning</h2>

              <div className="mt-5 space-y-5">
                <label className="block">
                  <div className="mb-2 flex items-center justify-between text-sm font-semibold text-foreground">
                    <span>Aggressiveness</span>
                    <span className="font-mono text-muted-foreground">x{aggressiveness.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min={1}
                    max={3}
                    step={0.05}
                    value={aggressiveness}
                    onChange={(event) => setAggressiveness(Number(event.target.value))}
                    className="w-full accent-[hsl(var(--primary))]"
                  />
                </label>

                <label className="block">
                  <div className="mb-2 flex items-center justify-between text-sm font-semibold text-foreground">
                    <span>Live lookahead</span>
                    <span className="font-mono text-muted-foreground">{lookaheadMs} ms</span>
                  </div>
                  <input
                    type="range"
                    min={120}
                    max={1000}
                    step={10}
                    value={lookaheadMs}
                    onChange={(event) => setLookaheadMs(Number(event.target.value))}
                    className="w-full accent-[hsl(var(--accent))]"
                  />
                </label>

                <div className="rounded-2xl border border-border bg-muted/30 p-4">
                  <div className="text-sm font-semibold text-foreground">Runtime health</div>
                  <div className="mt-3 grid gap-3 text-sm text-muted-foreground">
                    <div className="flex items-center justify-between gap-4">
                      <span>Model</span>
                      <span className="text-right font-mono text-foreground/80">
                        {runtimeMetrics?.displayName ?? "--"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span>Runtime</span>
                      <span className="text-right font-mono text-foreground/80">
                        {runtimeMetrics?.runtimeKind ?? "--"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span>Available providers</span>
                      <span className="text-right font-mono text-foreground/80">
                        {runtimeMetrics?.availableProviders.join(", ") || "--"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span>Active sessions</span>
                      <span className="font-mono text-foreground/80">{runtimeMetrics?.activeLiveSessions ?? 0}</span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span>Active jobs</span>
                      <span className="font-mono text-foreground/80">{runtimeMetrics?.activeJobs ?? 0}</span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span>Model categories</span>
                      <span className="font-mono text-foreground/80">{runtimeMetrics?.categoryCount ?? 0}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="grid gap-5 xl:grid-cols-2">
            <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                    Live Monitor
                  </div>
                  <h2 className="mt-2 text-2xl font-semibold text-foreground">
                    {liveTitle}
                  </h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Windows-only buffered live path. Audio threads stay lightweight while the active model runtime
                    handles suppression on the latest captured audio blocks.
                  </p>
                </div>
                <div
                  className={`rounded-full border px-3 py-1 text-[11px] font-mono uppercase tracking-[0.18em] ${
                    activeLiveSessionId
                      ? "border-accent/35 bg-accent/15 text-accent"
                      : "border-border bg-muted/35 text-muted-foreground"
                  }`}
                >
                  {activeLiveSessionId ? "running" : "stopped"}
                </div>
              </div>

              <div className="mt-5 rounded-2xl border border-border bg-muted/30 p-1">
                <div className="grid grid-cols-2 gap-1">
                  <button
                    type="button"
                    onClick={() => setOutputMode("monitor")}
                    disabled={Boolean(activeLiveSessionId)}
                    className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                      outputMode === "monitor"
                        ? "bg-card text-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-card/70 hover:text-foreground"
                    }`}
                  >
                    Listen locally
                  </button>
                  <button
                    type="button"
                    onClick={() => setOutputMode("virtualMic")}
                    disabled={Boolean(activeLiveSessionId) || !virtualMicReady}
                    className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                      outputMode === "virtualMic"
                        ? "bg-card text-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-card/70 hover:text-foreground"
                    }`}
                  >
                    Virtual mic
                  </button>
                </div>
              </div>

              <div className="mt-4 rounded-2xl border border-border bg-muted/30 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="text-sm font-semibold text-foreground">
                      {virtualMicReady ? `${virtualMicStatus?.provider} ready` : `${virtualMicStatus?.provider ?? "VB-CABLE"} not detected`}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {virtualMicReady
                        ? `Rendering to ${virtualMicPlaybackName}; choose ${virtualMicRecordingName} as the mic in the target app.`
                        : virtualMicStatus?.message ?? "Install VB-CABLE, then refresh devices."}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void refreshVirtualMicStatus()}
                      className="rounded-xl border border-border bg-card px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
                    >
                      check
                    </button>
                    {!virtualMicReady && (
                      <a
                        href={virtualMicStatus?.setupUrl ?? "https://vb-audio.com/Cable/"}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-xl border border-primary/35 bg-primary/12 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary transition-colors hover:bg-primary/18"
                      >
                        setup
                      </a>
                    )}
                  </div>
                </div>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <label className="block">
                  <div className="mb-2 text-sm font-semibold text-foreground">Input device</div>
                  <select
                    value={inputDeviceId}
                    onChange={(event) => setInputDeviceId(event.target.value)}
                    disabled={debugInputEnabled}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
                  >
                    <option value="">System default</option>
                    {inputDevices.map((device) => (
                      <option key={device.id} value={device.id}>
                        {device.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="block">
                  <div className="mb-2 text-sm font-semibold text-foreground">
                    {outputMode === "virtualMic" ? "Clean audio sink" : "Monitor device"}
                  </div>
                  <select
                    value={outputMode === "virtualMic" ? virtualMicStatus?.playbackDeviceId ?? "" : outputDeviceId}
                    onChange={(event) => setOutputDeviceId(event.target.value)}
                    disabled={outputMode === "virtualMic"}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
                  >
                    <option value="">System default</option>
                    {outputDevices.map((device) => (
                      <option key={device.id} value={device.id}>
                        {device.name}
                        {device.virtualCable?.role === "playback" ? " -> virtual mic" : ""}
                      </option>
                    ))}
                  </select>
                  {outputMode === "virtualMic" && (
                    <div className="mt-2 text-xs text-muted-foreground">
                      {virtualMicPlaybackName}
                    </div>
                  )}
                </label>
              </div>

              <div className="mt-4 rounded-2xl border border-border bg-muted/30 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-semibold text-foreground">Debug WAV mic source</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {debugInputEnabled ? "Live input is the selected WAV." : "Live input is the selected device."}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDebugInputEnabled(!debugInputEnabled)}
                    className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${
                      debugInputEnabled
                        ? "border-primary/35 bg-primary/15 text-primary"
                        : "border-border bg-card text-muted-foreground"
                    }`}
                  >
                    {debugInputEnabled ? "on" : "off"}
                  </button>
                </div>

                {debugInputEnabled && (
                  <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                    <input
                      value={debugInputPath}
                      onChange={(event) => setDebugInputPath(event.target.value)}
                      placeholder="C:\\path\\to\\debug_source.wav"
                      className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
                    />
                    <button
                      type="button"
                      onClick={() => void browseDebugInputPath()}
                      className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
                    >
                      choose wav
                    </button>
                  </div>
                )}
              </div>

              <div className="mt-4 rounded-2xl border border-border bg-muted/30 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-semibold text-foreground">Record clean live session</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Optional WAV capture of the monitored clean output.
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setRecordEnabled(!recordEnabled)}
                    className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${
                      recordEnabled
                        ? "border-primary/35 bg-primary/15 text-primary"
                        : "border-border bg-card text-muted-foreground"
                    }`}
                  >
                    {recordEnabled ? "on" : "off"}
                  </button>
                </div>

                {recordEnabled && (
                  <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                    <input
                      value={recordOutputPath}
                      onChange={(event) => setRecordOutputPath(event.target.value)}
                      placeholder="C:\\path\\to\\live_clean.wav"
                      className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
                    />
                    <button
                      type="button"
                      onClick={() => void browseRecordOutputPath()}
                      className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
                    >
                      choose wav
                    </button>
                  </div>
                )}
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                {activeLiveSessionId ? (
                  <button
                    type="button"
                    onClick={() => void stopLive()}
                    className="rounded-2xl border border-destructive/35 bg-destructive/12 px-5 py-3 text-sm font-semibold text-destructive transition-colors hover:bg-destructive/18"
                  >
                    Stop live monitor
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void startLive()}
                    disabled={liveStartDisabled}
                    className="rounded-2xl border border-primary/35 bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isStartingLive
                      ? "Starting..."
                      : outputMode === "virtualMic"
                        ? "Start virtual mic"
                        : "Start live monitor"}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void refreshDevices()}
                  className="rounded-2xl border border-border bg-card px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-accent/30 hover:bg-accent/10"
                >
                  Refresh devices
                </button>
              </div>

              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                <SignalMeter
                  title="input monitor"
                  waveform={liveMeter?.waveformIn ?? []}
                  peak={liveMeter?.peakIn ?? 0}
                  rms={liveMeter?.rmsIn ?? 0}
                  accentClass="bg-gradient-to-t from-[hsl(var(--neon-orange))] to-[hsl(var(--neon-pink))]"
                />
                <SignalMeter
                  title="clean monitor"
                  waveform={liveMeter?.waveformOut ?? []}
                  peak={liveMeter?.peakOut ?? 0}
                  rms={liveMeter?.rmsOut ?? 0}
                  accentClass="bg-gradient-to-t from-[hsl(var(--accent))] to-[hsl(var(--primary))]"
                />
              </div>
            </div>

            <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                    Offline Render
                  </div>
                  <h2 className="mt-2 text-2xl font-semibold text-foreground">
                    {"File -> suppress -> WAV"}
                  </h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Symphonia decode, packaged-model suppression, and float32 WAV export with original sample rate and
                    channel count preserved.
                  </p>
                </div>
                <div
                  className={`rounded-full border px-3 py-1 text-[11px] font-mono uppercase tracking-[0.18em] ${
                    activeOfflineJobId
                      ? "border-primary/35 bg-primary/12 text-primary"
                      : "border-border bg-muted/35 text-muted-foreground"
                  }`}
                >
                  {activeOfflineJobId ? "job active" : "idle"}
                </div>
              </div>

              <div className="mt-5 space-y-4">
                <div>
                  <div className="mb-2 text-sm font-semibold text-foreground">Input audio path</div>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <input
                      value={inputPath}
                      onChange={(event) => setInputPath(event.target.value)}
                      placeholder="C:\\path\\to\\input.wav"
                      className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
                    />
                    <button
                      type="button"
                      onClick={() => void browseInputPath()}
                      className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
                    >
                      browse
                    </button>
                  </div>
                </div>

                <div>
                  <div className="mb-2 text-sm font-semibold text-foreground">Output WAV path</div>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <input
                      value={outputPath}
                      onChange={(event) => setOutputPath(event.target.value)}
                      placeholder="C:\\path\\to\\clean.wav"
                      className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
                    />
                    <button
                      type="button"
                      onClick={() => void browseOutputPath()}
                      className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
                    >
                      save as
                    </button>
                  </div>
                </div>
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => void startOffline()}
                  disabled={isOfflineRunning || isLoading}
                  className="rounded-2xl border border-accent/35 bg-accent px-5 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isOfflineRunning ? "Rendering..." : "Render clean WAV"}
                </button>
                <button
                  type="button"
                  onClick={() => void cancelOffline()}
                  disabled={!activeOfflineJobId}
                  className="rounded-2xl border border-border bg-card px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-destructive/35 hover:bg-destructive/8 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Cancel job
                </button>
              </div>

              <div className="mt-5 rounded-2xl border border-border bg-muted/30 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="text-sm font-semibold text-foreground">
                    {offlineProgress?.stage ?? "waiting"}
                  </div>
                  <div className="text-xs font-mono uppercase tracking-[0.16em] text-muted-foreground">
                    {Math.max(0, offlineProgress?.progress ?? 0).toFixed(0)}%
                  </div>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-border/70">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-[hsl(var(--accent))] to-[hsl(var(--primary))]"
                    style={{ width: `${Math.min(100, Math.max(0, offlineProgress?.progress ?? 0))}%` }}
                  />
                </div>
                <div className="mt-3 grid gap-2 text-sm text-muted-foreground">
                  <div className="flex items-center justify-between gap-4">
                    <span>ETA</span>
                    <span className="font-mono text-foreground/80">
                      {offlineProgress?.etaSeconds != null ? `${offlineProgress.etaSeconds.toFixed(1)} s` : "--"}
                    </span>
                  </div>
                  <div className="flex items-start justify-between gap-4">
                    <span>Message</span>
                    <span className="max-w-[65%] text-right text-foreground/80">
                      {offlineProgress?.message ?? "Waiting for a render job."}
                    </span>
                  </div>
                  <div className="flex items-start justify-between gap-4">
                    <span>Output</span>
                    <span className="max-w-[65%] break-all text-right font-mono text-foreground/80">
                      {offlineProgress?.outputPath || outputPath || "--"}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
