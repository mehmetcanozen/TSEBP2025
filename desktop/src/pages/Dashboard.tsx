import HeaderBar from "@/components/HeaderBar";
import CategorySelector from "@/components/desktop/CategorySelector";
import PresetStrip from "@/components/desktop/PresetStrip";
import SignalMeter from "@/components/desktop/SignalMeter";
import { useDesktopRuntime } from "@/contexts/DesktopRuntimeContext";
import { AudioWaveform, RefreshCw, Scissors, UserRound } from "lucide-react";

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

const formatDuration = (durationMs?: number | null) => {
  if (!durationMs || Number.isNaN(durationMs)) {
    return "--";
  }
  return `${(durationMs / 1000).toFixed(1)} s`;
};

const Dashboard = () => {
  const {
    categories,
    presets,
    devices,
    runtimeMetrics,
    targetSpeakerInfo,
    speakerProfiles,
    virtualMicStatus,
    desktopMode,
    selectedCategories,
    aggressiveness,
    speakerInputPath,
    speakerReferencePath,
    speakerOutputPath,
    speakerEngine,
    speakerOutputMode,
    speakerRemovalScale,
    selectedSpeakerProfileId,
    speakerProfileName,
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
    setDesktopMode,
    toggleCategory,
    applyPreset,
    setAggressiveness,
    setSpeakerInputPath,
    setSpeakerReferencePath,
    setSpeakerOutputPath,
    setSpeakerEngine,
    setSpeakerOutputMode,
    setSpeakerRemovalScale,
    setSelectedSpeakerProfileId,
    setSpeakerProfileName,
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
    browseSpeakerInputPath,
    browseSpeakerReferencePath,
    browseSpeakerOutputPath,
    browseDebugInputPath,
    browseRecordOutputPath,
    refreshDevices,
    refreshVirtualMicStatus,
    refreshRuntimeMetrics,
    refreshTargetSpeakerInfo,
    refreshSpeakerProfiles,
    startOffline,
    startSpeakerSuppression,
    saveCurrentSpeakerProfile,
    deleteSelectedSpeakerProfile,
    cancelOffline,
    startLive,
    stopLive,
    clearError,
  } = useDesktopRuntime();

  const inputDevices = devices.filter((device) => device.direction === "input");
  const outputDevices = devices.filter((device) => device.direction === "output");
  const selectedInputDevice = inputDevices.find((device) => device.id === inputDeviceId);
  const virtualMicReady = Boolean(virtualMicStatus?.installed && virtualMicStatus.playbackDeviceId);
  const virtualMicPlaybackName = virtualMicStatus?.playbackDeviceName ?? "CABLE Input";
  const virtualMicRecordingName = virtualMicStatus?.recordingDeviceName ?? "CABLE Output";
  const selectedSpeakerProfile = speakerProfiles.find((profile) => profile.id === selectedSpeakerProfileId);
  const liveStartDisabled = isStartingLive || isLoading || (outputMode === "virtualMic" && !virtualMicReady);
  const speakerLiveMicUsesVirtualCableInput =
    desktopMode === "speakerSuppression" &&
    outputMode === "virtualMic" &&
    !debugInputEnabled &&
    selectedInputDevice?.virtualCable?.role === "recording";
  const liveTitle = desktopMode === "speakerSuppression"
    ? outputMode === "virtualMic"
      ? "Mic -> speaker profile -> virtual mic"
      : "Mic -> speaker profile -> monitor"
    : outputMode === "virtualMic"
      ? "Mic -> suppress -> virtual mic"
      : "Mic -> suppress -> monitor";
  const speakerEngineLabel = speakerEngine === "tsextract_onnx" ? "Fast ONNX" : "Quality Bundle";
  const speakerOutputLabel = speakerOutputMode === "remove_target" ? "Suppress speaker" : "Extract target";
  const speakerActionLabel =
    speakerOutputMode === "remove_target" ? "Suppress referenced speaker" : "Extract referenced speaker";
  const speakerLiveActionLabel = outputMode === "virtualMic" ? "Start speaker virtual mic" : "Start speaker realtime";
  const speakerReferenceReady = Boolean(speakerReferencePath.trim());
  const speakerRealtimeBlockReason = speakerEngine !== "tsextract_onnx"
    ? "Realtime uses Fast ONNX."
    : speakerLiveMicUsesVirtualCableInput
      ? "Choose a real microphone as input. CABLE Output is for the target app."
    : !speakerReferenceReady
      ? "Choose a reference clip or saved profile."
      : null;
  const speakerRealtimeDisabled =
    liveStartDisabled ||
    !speakerReferenceReady ||
    speakerEngine !== "tsextract_onnx" ||
    speakerLiveMicUsesVirtualCableInput;
  const activeOutputPath = desktopMode === "speakerSuppression" ? speakerOutputPath : outputPath;

  const renderSpeakerReferenceControls = () => (
    <div className="rounded-2xl border border-border bg-muted/30 p-4">
      <div className="grid gap-3 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
        <label className="block">
          <div className="mb-2 text-sm font-semibold text-foreground">Saved speaker profile</div>
          <select
            value={selectedSpeakerProfileId}
            onChange={(event) => setSelectedSpeakerProfileId(event.target.value)}
            className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
          >
            <option value="">No saved profile</option>
            {speakerProfiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <div className="mb-2 text-sm font-semibold text-foreground">Profile name</div>
          <input
            value={speakerProfileName}
            onChange={(event) => setSpeakerProfileName(event.target.value)}
            placeholder="Speaker name"
            className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void saveCurrentSpeakerProfile()}
            disabled={!speakerReferenceReady || !speakerProfileName.trim()}
            className="rounded-xl border border-accent/35 bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Save profile
          </button>
          <button
            type="button"
            onClick={() => void deleteSelectedSpeakerProfile()}
            disabled={!selectedSpeakerProfileId}
            className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-destructive/35 hover:bg-destructive/8 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Delete
          </button>
          <button
            type="button"
            onClick={() => void refreshSpeakerProfiles()}
            className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="mt-4">
        <div className="mb-2 text-sm font-semibold text-foreground">Reference speaker clip</div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            value={speakerReferencePath}
            onChange={(event) => setSpeakerReferencePath(event.target.value)}
            placeholder="C:\\path\\to\\speaker_reference.wav"
            className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
          />
          <button
            type="button"
            onClick={() => void browseSpeakerReferencePath()}
            className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
          >
            browse
          </button>
        </div>
      </div>

      <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-3">
        <div>
          Profiles <span className="font-mono text-foreground/80">{speakerProfiles.length}</span>
        </div>
        <div>
          Duration{" "}
          <span className="font-mono text-foreground/80">
            {formatDuration(selectedSpeakerProfile?.durationMs)}
          </span>
        </div>
        <div className="truncate">
          Active{" "}
          <span className="font-mono text-foreground/80">
            {selectedSpeakerProfile?.name ?? (speakerReferencePath ? "manual clip" : "--")}
          </span>
        </div>
      </div>
    </div>
  );

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
                p95 {formatMillis(liveStatus?.inferenceMsP95)} / hop{" "}
                {formatMillis(runtimeMetrics?.preferredLiveHopMs)}
              </div>
            </div>

            <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
              <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                {desktopMode === "speakerSuppression" ? "Speaker Tool" : "Targets"}
              </div>
              <div className="mt-3 text-2xl font-semibold text-foreground">
                {desktopMode === "speakerSuppression" ? speakerEngineLabel : selectedCategories.length}
              </div>
              <div className="mt-2 text-sm text-muted-foreground">
                {desktopMode === "speakerSuppression"
                  ? speakerOutputLabel
                  : selectedCategories.length > 2
                    ? "realtime warning budget"
                    : "realtime target budget ok"}
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

          <section className="rounded-3xl border border-border bg-card/85 p-2 shadow-sm">
            <div className="grid gap-2 md:grid-cols-2">
              <button
                type="button"
                onClick={() => setDesktopMode("semanticSuppression")}
                className={`flex min-h-[92px] items-center gap-4 rounded-2xl border px-4 py-3 text-left transition-colors ${
                  desktopMode === "semanticSuppression"
                    ? "border-primary/35 bg-primary/12 text-foreground"
                    : "border-transparent text-muted-foreground hover:bg-muted/45 hover:text-foreground"
                }`}
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border bg-background">
                  <AudioWaveform className="h-5 w-5" />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">Semantic Suppression</span>
                  <span className="mt-1 block text-xs leading-5">
                    Waveformer live and offline category suppression.
                  </span>
                </span>
              </button>
              <button
                type="button"
                onClick={() => setDesktopMode("speakerSuppression")}
                className={`flex min-h-[92px] items-center gap-4 rounded-2xl border px-4 py-3 text-left transition-colors ${
                  desktopMode === "speakerSuppression"
                    ? "border-accent/35 bg-accent/12 text-foreground"
                    : "border-transparent text-muted-foreground hover:bg-muted/45 hover:text-foreground"
                }`}
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border bg-background">
                  <Scissors className="h-5 w-5" />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">Speaker Suppression</span>
                  <span className="mt-1 block text-xs leading-5">
                    Remove the speaker matching a reference clip from files or live audio.
                  </span>
                </span>
              </button>
            </div>
          </section>

          {desktopMode === "speakerSuppression" && (
            <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                      Speaker Realtime
                    </div>
                    <h2 className="mt-2 text-2xl font-semibold text-foreground">
                      {liveTitle}
                    </h2>
                    <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                      Fast ONNX uses the active reference clip or saved profile for live speaker suppression.
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

                <div className="mt-4">
                  {renderSpeakerReferenceControls()}
                </div>

                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <div className="rounded-2xl border border-border bg-muted/30 p-1">
                    <div className="grid grid-cols-2 gap-1">
                      <button
                        type="button"
                        onClick={() => setSpeakerEngine("tsextract_onnx")}
                        disabled={Boolean(activeLiveSessionId)}
                        className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                          speakerEngine === "tsextract_onnx"
                            ? "bg-card text-foreground shadow-sm"
                            : "text-muted-foreground hover:bg-card/70 hover:text-foreground"
                        }`}
                      >
                        Fast ONNX
                      </button>
                      <button
                        type="button"
                        disabled
                        title="Quality Bundle is available for file upload, not speaker realtime."
                        className="rounded-xl px-3 py-2 text-sm font-semibold text-muted-foreground opacity-50"
                      >
                        Quality Bundle
                      </button>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border bg-muted/30 p-1">
                    <div className="grid grid-cols-2 gap-1">
                      <button
                        type="button"
                        onClick={() => setSpeakerOutputMode("remove_target")}
                        disabled={Boolean(activeLiveSessionId)}
                        className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                          speakerOutputMode === "remove_target"
                            ? "bg-card text-foreground shadow-sm"
                            : "text-muted-foreground hover:bg-card/70 hover:text-foreground"
                        }`}
                      >
                        Suppress speaker
                      </button>
                      <button
                        type="button"
                        onClick={() => setSpeakerOutputMode("extract_target")}
                        disabled={Boolean(activeLiveSessionId)}
                        className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                          speakerOutputMode === "extract_target"
                            ? "bg-card text-foreground shadow-sm"
                            : "text-muted-foreground hover:bg-card/70 hover:text-foreground"
                        }`}
                      >
                        Extract target
                      </button>
                    </div>
                  </div>
                </div>

                {speakerOutputMode === "remove_target" && (
                  <label className="mt-4 block rounded-2xl border border-border bg-muted/30 p-4">
                    <div className="mb-2 flex items-center justify-between text-sm font-semibold text-foreground">
                      <span>Removal strength</span>
                      <span className="font-mono text-muted-foreground">x{speakerRemovalScale.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min={0.25}
                      max={2}
                      step={0.05}
                      value={speakerRemovalScale}
                      onChange={(event) => setSpeakerRemovalScale(Number(event.target.value))}
                      disabled={Boolean(activeLiveSessionId)}
                      className="w-full accent-[hsl(var(--accent))] disabled:opacity-60"
                    />
                  </label>
                )}

                <div className="mt-4 rounded-2xl border border-border bg-muted/30 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-sm font-semibold text-foreground">Realtime input source</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {debugInputEnabled
                          ? "Debug WAV is used as the live input."
                          : outputMode === "virtualMic"
                            ? `Your mic is processed and sent to ${virtualMicPlaybackName}.`
                            : "Your mic is processed and played to the monitor device."}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-border bg-background/70 p-1">
                      <div className="grid grid-cols-2 gap-1">
                        <button
                          type="button"
                          onClick={() => setDebugInputEnabled(false)}
                          disabled={Boolean(activeLiveSessionId)}
                          className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                            !debugInputEnabled
                              ? "bg-card text-foreground shadow-sm"
                              : "text-muted-foreground hover:bg-card/70 hover:text-foreground"
                          }`}
                        >
                          Live mic
                        </button>
                        <button
                          type="button"
                          onClick={() => setDebugInputEnabled(true)}
                          disabled={Boolean(activeLiveSessionId)}
                          className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                            debugInputEnabled
                              ? "bg-card text-foreground shadow-sm"
                              : "text-muted-foreground hover:bg-card/70 hover:text-foreground"
                          }`}
                        >
                          Debug WAV
                        </button>
                      </div>
                    </div>
                  </div>
                  {!debugInputEnabled && outputMode === "virtualMic" && (
                    <div className="mt-3 rounded-xl border border-primary/20 bg-primary/8 px-3 py-2 text-xs text-muted-foreground">
                      App input is your physical mic. App output is {virtualMicPlaybackName}. Target app mic is {virtualMicRecordingName}.
                    </div>
                  )}
                </div>

                <div className="mt-5 grid gap-4 md:grid-cols-2">
                  <label className="block">
                    <div className="mb-2 text-sm font-semibold text-foreground">Live mic device</div>
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
                    {!debugInputEnabled && outputMode === "virtualMic" && (
                      <div className={`mt-2 text-xs ${speakerLiveMicUsesVirtualCableInput ? "text-destructive" : "text-muted-foreground"}`}>
                        {speakerLiveMicUsesVirtualCableInput
                          ? "CABLE Output would feed the virtual mic back into itself. Select your real microphone."
                          : "Use your real microphone here; other apps should use CABLE Output."}
                      </div>
                    )}
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

                {debugInputEnabled && (
                  <div className="mt-4 rounded-2xl border border-border bg-muted/30 p-4">
                    <div className="text-sm font-semibold text-foreground">Debug WAV file</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Selected WAV replaces the live mic.
                    </div>
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
                  </div>
                )}

                <div className="mt-4 rounded-2xl border border-border bg-muted/30 p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="text-sm font-semibold text-foreground">Record clean live session</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        Optional WAV capture of the speaker-suppressed output.
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
                        placeholder="C:\\path\\to\\speaker_live_clean.wav"
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
                      Stop speaker realtime
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void startLive()}
                      disabled={speakerRealtimeDisabled}
                      className="rounded-2xl border border-primary/35 bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isStartingLive ? "Starting..." : speakerLiveActionLabel}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void refreshDevices()}
                    className="rounded-2xl border border-border bg-card px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-accent/30 hover:bg-accent/10"
                  >
                    Refresh devices
                  </button>
                  {speakerRealtimeBlockReason && (
                    <div className="flex items-center text-sm text-muted-foreground">
                      {speakerRealtimeBlockReason}
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
                <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                  Live Signal
                </div>
                <h2 className="mt-2 text-2xl font-semibold text-foreground">Profile monitor</h2>

                <div className="mt-5 grid gap-4">
                  <SignalMeter
                    title="input monitor"
                    waveform={liveMeter?.waveformIn ?? []}
                    peak={liveMeter?.peakIn ?? 0}
                    rms={liveMeter?.rmsIn ?? 0}
                    accentClass="bg-gradient-to-t from-[hsl(var(--neon-orange))] to-[hsl(var(--neon-pink))]"
                  />
                  <SignalMeter
                    title="speaker-suppressed"
                    waveform={liveMeter?.waveformOut ?? []}
                    peak={liveMeter?.peakOut ?? 0}
                    rms={liveMeter?.rmsOut ?? 0}
                    accentClass="bg-gradient-to-t from-[hsl(var(--accent))] to-[hsl(var(--primary))]"
                  />
                </div>

                <div className="mt-5 grid gap-3 text-sm text-muted-foreground">
                  <div className="flex items-center justify-between gap-4">
                    <span>Profile</span>
                    <span className="max-w-[62%] truncate text-right font-mono text-foreground/80">
                      {selectedSpeakerProfile?.name ?? (speakerReferencePath ? "manual clip" : "--")}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span>Engine</span>
                    <span className="font-mono text-foreground/80">Fast ONNX</span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span>Output</span>
                    <span className="font-mono text-foreground/80">{speakerOutputLabel}</span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span>Inference</span>
                    <span className="font-mono text-foreground/80">{formatMillis(liveStatus?.inferenceMs)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span>Health</span>
                    <span className={healthTone(liveStatus?.realtimeHealth)}>
                      {liveStatus?.realtimeHealth ?? "idle"}
                    </span>
                  </div>
                </div>
              </div>
            </section>
          )}

          {desktopMode === "semanticSuppression" ? (
            <>
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
                      <span>Model rate</span>
                      <span className="font-mono text-foreground/80">
                        {runtimeMetrics?.modelSampleRate ? `${runtimeMetrics.modelSampleRate} Hz` : "--"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span>Chunk</span>
                      <span className="font-mono text-foreground/80">
                        {runtimeMetrics?.chunkSamples
                          ? `${runtimeMetrics.chunkSamples} samples`
                          : "--"}
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
                    <div className="flex items-center justify-between gap-4">
                      <span>Validation</span>
                      <span className="max-w-[55%] truncate text-right font-mono text-foreground/80">
                        {runtimeMetrics?.validationStatus ?? "--"}
                      </span>
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
            </>
          ) : (
            <section className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
              <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                      Speaker File Upload
                    </div>
                    <h2 className="mt-2 text-2xl font-semibold text-foreground">
                      {"Mixture WAV -> speaker-suppressed WAV"}
                    </h2>
                    <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                      The selected engine extracts the referenced speaker internally, then writes the mixture with that
                      speaker removed.
                    </p>
                  </div>
                  <div
                    className={`rounded-full border px-3 py-1 text-[11px] font-mono uppercase tracking-[0.18em] ${
                      activeOfflineJobId
                        ? "border-accent/35 bg-accent/15 text-accent"
                        : "border-border bg-muted/35 text-muted-foreground"
                    }`}
                  >
                    {activeOfflineJobId ? "job active" : "offline"}
                  </div>
                </div>

                <div className="mt-5 grid gap-4">
                  {renderSpeakerReferenceControls()}

                  <div>
                    <div className="mb-2 text-sm font-semibold text-foreground">File upload mixture path</div>
                    <div className="flex flex-col gap-3 sm:flex-row">
                      <input
                        value={speakerInputPath}
                        onChange={(event) => setSpeakerInputPath(event.target.value)}
                        placeholder="C:\\path\\to\\mixture.wav"
                        className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
                      />
                      <button
                        type="button"
                        onClick={() => void browseSpeakerInputPath()}
                        className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
                      >
                        browse
                      </button>
                    </div>
                  </div>

                  <div>
                    <div className="mb-2 text-sm font-semibold text-foreground">Suppressed output WAV path</div>
                    <div className="flex flex-col gap-3 sm:flex-row">
                      <input
                        value={speakerOutputPath}
                        onChange={(event) => setSpeakerOutputPath(event.target.value)}
                        placeholder="C:\\path\\to\\speaker_suppressed.wav"
                        className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
                      />
                      <button
                        type="button"
                        onClick={() => void browseSpeakerOutputPath()}
                        className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
                      >
                        save as
                      </button>
                    </div>
                  </div>
                </div>

                <div className="mt-5 grid gap-4 lg:grid-cols-2">
                  <div className="rounded-2xl border border-border bg-muted/30 p-1">
                    <div className="grid grid-cols-2 gap-1">
                      <button
                        type="button"
                        onClick={() => setSpeakerEngine("tsextract_onnx")}
                        className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${
                          speakerEngine === "tsextract_onnx"
                            ? "bg-card text-foreground shadow-sm"
                            : "text-muted-foreground hover:bg-card/70 hover:text-foreground"
                        }`}
                      >
                        Fast ONNX
                      </button>
                      <button
                        type="button"
                        onClick={() => setSpeakerEngine("clearvoice_bundle")}
                        disabled={!targetSpeakerInfo?.clearvoiceReady}
                        className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                          speakerEngine === "clearvoice_bundle"
                            ? "bg-card text-foreground shadow-sm"
                            : "text-muted-foreground hover:bg-card/70 hover:text-foreground"
                        }`}
                      >
                        Quality Bundle
                      </button>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border bg-muted/30 p-1">
                    <div className="grid grid-cols-2 gap-1">
                      <button
                        type="button"
                        onClick={() => setSpeakerOutputMode("remove_target")}
                        className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${
                          speakerOutputMode === "remove_target"
                            ? "bg-card text-foreground shadow-sm"
                            : "text-muted-foreground hover:bg-card/70 hover:text-foreground"
                        }`}
                      >
                        Suppress speaker
                      </button>
                      <button
                        type="button"
                        onClick={() => setSpeakerOutputMode("extract_target")}
                        className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${
                          speakerOutputMode === "extract_target"
                            ? "bg-card text-foreground shadow-sm"
                            : "text-muted-foreground hover:bg-card/70 hover:text-foreground"
                        }`}
                      >
                        Extract target
                      </button>
                    </div>
                  </div>
                </div>

                {speakerOutputMode === "remove_target" && (
                  <label className="mt-5 block">
                    <div className="mb-2 flex items-center justify-between text-sm font-semibold text-foreground">
                      <span>Removal strength</span>
                      <span className="font-mono text-muted-foreground">x{speakerRemovalScale.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min={0.25}
                      max={2}
                      step={0.05}
                      value={speakerRemovalScale}
                      onChange={(event) => setSpeakerRemovalScale(Number(event.target.value))}
                      className="w-full accent-[hsl(var(--accent))]"
                    />
                  </label>
                )}

                <div className="mt-5 flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => void startSpeakerSuppression()}
                    disabled={isOfflineRunning || isLoading}
                    className="rounded-2xl border border-accent/35 bg-accent px-5 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isOfflineRunning ? "Processing..." : speakerActionLabel}
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
              </div>

              <div className="space-y-5">
                <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                        Target Runtime
                      </div>
                      <h2 className="mt-2 text-2xl font-semibold text-foreground">
                        {targetSpeakerInfo?.displayName ?? "Target Speaker"}
                      </h2>
                    </div>
                    <button
                      type="button"
                      onClick={() => void refreshTargetSpeakerInfo()}
                      className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-muted/40 text-foreground/80 transition-colors hover:border-primary/30 hover:bg-primary/10"
                      aria-label="Refresh target speaker runtime"
                      title="Refresh target speaker runtime"
                    >
                      <RefreshCw className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="mt-5 grid gap-3 text-sm text-muted-foreground">
                    <div className="flex items-center justify-between gap-4">
                      <span>Engine</span>
                      <span className="font-mono text-foreground/80">{speakerEngineLabel}</span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span>Model rate</span>
                      <span className="font-mono text-foreground/80">
                        {targetSpeakerInfo?.modelSampleRate ?? 8000} Hz
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span>Window</span>
                      <span className="font-mono text-foreground/80">
                        {targetSpeakerInfo?.mixtureSamples ?? 80000} samples
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span>Reference</span>
                      <span className="font-mono text-foreground/80">
                        {targetSpeakerInfo?.referenceSamples ?? 24000} samples
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span>ONNX sidecar</span>
                      <span className={targetSpeakerInfo?.onnxSidecarPresent ? "text-accent" : "text-destructive"}>
                        {targetSpeakerInfo?.onnxSidecarPresent ? "ready" : "missing"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span>ClearVoice</span>
                      <span className={targetSpeakerInfo?.clearvoiceReady ? "text-accent" : "text-muted-foreground"}>
                        {targetSpeakerInfo?.clearvoiceReady ? "ready" : "setup needed"}
                      </span>
                    </div>
                    <div className="flex items-start justify-between gap-4">
                      <span>Validation</span>
                      <span className="max-w-[58%] truncate text-right font-mono text-foreground/80">
                        {targetSpeakerInfo?.validationStatus ?? "--"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="rounded-3xl border border-border bg-card/85 p-5 shadow-sm">
                  <div className="flex items-center gap-3">
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-background">
                      <UserRound className="h-4 w-4" />
                    </span>
                    <div>
                      <div className="text-sm font-semibold text-foreground">
                        {offlineProgress?.stage ?? "waiting"}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {Math.max(0, offlineProgress?.progress ?? 0).toFixed(0)}% complete
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 h-2 overflow-hidden rounded-full bg-border/70">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-[hsl(var(--accent))] to-[hsl(var(--primary))]"
                      style={{ width: `${Math.min(100, Math.max(0, offlineProgress?.progress ?? 0))}%` }}
                    />
                  </div>
                  <div className="mt-4 grid gap-2 text-sm text-muted-foreground">
                    <div className="flex items-start justify-between gap-4">
                      <span>Message</span>
                      <span className="max-w-[65%] text-right text-foreground/80">
                        {offlineProgress?.message ?? "Waiting for a speaker suppression job."}
                      </span>
                    </div>
                    <div className="flex items-start justify-between gap-4">
                      <span>Output</span>
                      <span className="max-w-[65%] break-all text-right font-mono text-foreground/80">
                        {offlineProgress?.outputPath || activeOutputPath || "--"}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
