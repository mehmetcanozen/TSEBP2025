import { useEffect, useMemo, useState, type ReactNode } from "react";
import HeaderBar from "@/components/HeaderBar";
import CategorySelector from "@/components/desktop/CategorySelector";
import PresetStrip from "@/components/desktop/PresetStrip";
import SignalMeter from "@/components/desktop/SignalMeter";
import { useDesktopRuntime } from "@/contexts/DesktopRuntimeContext";
import {
  Activity,
  AlertCircle,
  AudioWaveform,
  CheckCircle2,
  CircleStop,
  FileAudio,
  FolderOpen,
  Play,
  RefreshCw,
  Scissors,
  Settings2,
  UserRound,
  Wand2,
} from "lucide-react";

type UserTask = "live" | "files" | "profiles" | "status";

const formatMillis = (value?: number | null) => {
  if (value == null || Number.isNaN(value)) return "--";
  return `${value.toFixed(0)} ms`;
};

const formatPercent = (value?: number | null) => `${Math.min(100, Math.max(0, value ?? 0)).toFixed(0)}%`;

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

const taskItems: Array<{ id: UserTask; label: string; description: string; icon: typeof Play }> = [
  { id: "live", label: "Live", description: "Run realtime suppression", icon: Play },
  { id: "files", label: "File Render", description: "Clean a WAV file", icon: FileAudio },
  { id: "profiles", label: "Speaker Profiles", description: "Manage reference clips", icon: UserRound },
  { id: "status", label: "Status", description: "Audio and runtime health", icon: Activity },
];

const Panel = ({
  title,
  eyebrow,
  children,
  action,
}: {
  title: string;
  eyebrow: string;
  children: ReactNode;
  action?: ReactNode;
}) => (
  <section className="rounded-2xl border border-border bg-card/90 p-5 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground">{eyebrow}</div>
        <h2 className="mt-1 text-xl font-semibold text-foreground">{title}</h2>
      </div>
      {action}
    </div>
    <div className="mt-5">{children}</div>
  </section>
);

const PathInput = ({
  label,
  value,
  placeholder,
  onChange,
  onBrowse,
}: {
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onBrowse: () => void;
}) => (
  <label className="block">
    <div className="mb-2 text-sm font-semibold text-foreground">{label}</div>
    <div className="flex flex-col gap-2 sm:flex-row">
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="min-w-0 flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
      />
      <button
        type="button"
        onClick={onBrowse}
        className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
      >
        <FolderOpen className="h-4 w-4" />
        Browse
      </button>
    </div>
  </label>
);

const UserDashboard = () => {
  const [task, setTask] = useState<UserTask>("live");
  const runtime = useDesktopRuntime();
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
    inputDeviceId,
    inputPath,
    outputPath,
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
    setInputDeviceId,
    setInputPath,
    setOutputPath,
    setDebugInputEnabled,
    browseInputPath,
    browseOutputPath,
    browseSpeakerInputPath,
    browseSpeakerReferencePath,
    browseSpeakerOutputPath,
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
  } = runtime;

  useEffect(() => {
    setDebugInputEnabled(false);
  }, [setDebugInputEnabled]);

  const inputDevices = devices.filter((device) => device.direction === "input");
  const selectedInputDevice = inputDevices.find((device) => device.id === inputDeviceId);
  const effectiveInputDevice = selectedInputDevice ?? inputDevices.find((device) => device.default);
  const virtualMicReady = Boolean(virtualMicStatus?.installed && virtualMicStatus.playbackDeviceId);
  const virtualMicRecordingName = virtualMicStatus?.recordingDeviceName ?? "CABLE Output";
  const virtualMicPlaybackName = virtualMicStatus?.playbackDeviceName ?? "CABLE Input";
  const selectedSpeakerProfile = speakerProfiles.find((profile) => profile.id === selectedSpeakerProfileId);
  const realMicBlocked = effectiveInputDevice?.virtualCable?.role === "recording";
  const speakerReferenceReady = Boolean(speakerReferencePath.trim());
  const activeOutputPath = desktopMode === "speakerSuppression" ? speakerOutputPath : outputPath;

  const liveBlockReason = useMemo(() => {
    if (!virtualMicReady) return "Virtual microphone output is not ready.";
    if (realMicBlocked) return "Select a real microphone. The virtual microphone output is for other apps.";
    if (desktopMode === "semanticSuppression" && selectedCategories.length === 0) {
      return "Select at least one sound target.";
    }
    if (desktopMode === "speakerSuppression" && !speakerReferenceReady) {
      return "Choose a speaker reference clip or saved profile.";
    }
    if (desktopMode === "speakerSuppression" && speakerEngine !== "tsextract_onnx") {
      return "Realtime speaker mode uses Fast ONNX.";
    }
    return null;
  }, [
    desktopMode,
    realMicBlocked,
    selectedCategories.length,
    speakerEngine,
    speakerReferenceReady,
    virtualMicReady,
  ]);

  const liveDisabled = isLoading || isStartingLive || Boolean(liveBlockReason);
  const modeLabel = desktopMode === "speakerSuppression" ? "Speaker" : "Semantic";
  const routeLabel =
    desktopMode === "speakerSuppression"
      ? "Microphone -> speaker reference -> virtual microphone"
      : "Microphone -> selected sounds -> virtual microphone";

  const semanticReadyText = selectedCategories.length
    ? `${selectedCategories.length} target${selectedCategories.length === 1 ? "" : "s"} selected`
    : "No targets selected";
  const speakerReadyText = selectedSpeakerProfile?.name ?? (speakerReferencePath ? "Manual reference clip" : "No reference selected");

  const renderModeSelector = () => (
    <div className="grid gap-3 md:grid-cols-2">
      <button
        type="button"
        onClick={() => setDesktopMode("semanticSuppression")}
        className={`flex min-h-[84px] items-center gap-3 rounded-2xl border px-4 py-3 text-left transition-colors ${
          desktopMode === "semanticSuppression"
            ? "border-primary/35 bg-primary/12 text-foreground"
            : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
        }`}
      >
        <AudioWaveform className="h-5 w-5 shrink-0" />
        <span>
          <span className="block text-sm font-semibold">Semantic suppression</span>
          <span className="mt-1 block text-xs leading-5">Reduce selected sound categories.</span>
        </span>
      </button>
      <button
        type="button"
        onClick={() => {
          setDesktopMode("speakerSuppression");
          if (speakerEngine !== "tsextract_onnx") setSpeakerEngine("tsextract_onnx");
        }}
        className={`flex min-h-[84px] items-center gap-3 rounded-2xl border px-4 py-3 text-left transition-colors ${
          desktopMode === "speakerSuppression"
            ? "border-accent/35 bg-accent/12 text-foreground"
            : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
        }`}
      >
        <Scissors className="h-5 w-5 shrink-0" />
        <span>
          <span className="block text-sm font-semibold">Speaker suppression</span>
          <span className="mt-1 block text-xs leading-5">Suppress or extract a referenced voice.</span>
        </span>
      </button>
    </div>
  );

  const renderSpeakerReference = () => (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
        <label className="block">
          <div className="mb-2 text-sm font-semibold text-foreground">Saved profile</div>
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
        <button
          type="button"
          onClick={() => void refreshSpeakerProfiles()}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      <PathInput
        label="Reference clip"
        value={speakerReferencePath}
        onChange={setSpeakerReferencePath}
        onBrowse={() => void browseSpeakerReferencePath()}
        placeholder="C:\\path\\to\\reference.wav"
      />
    </div>
  );

  const renderLiveTask = () => (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-5">
        <Panel
          eyebrow="Realtime"
          title={`${modeLabel} live suppression`}
          action={
            <span
              className={`rounded-full border px-3 py-1 text-[11px] font-mono uppercase tracking-[0.16em] ${
                activeLiveSessionId
                  ? "border-accent/35 bg-accent/15 text-accent"
                  : "border-border bg-muted/35 text-muted-foreground"
              }`}
            >
              {activeLiveSessionId ? "running" : "ready"}
            </span>
          }
        >
          <div className="space-y-5">
            {renderModeSelector()}

            <div className="rounded-2xl border border-border bg-muted/25 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-foreground">{routeLabel}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Other apps should use {virtualMicRecordingName} as their microphone.
                  </div>
                </div>
                <span
                  className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${
                    virtualMicReady
                      ? "border-accent/35 bg-accent/12 text-accent"
                      : "border-destructive/30 bg-destructive/10 text-destructive"
                  }`}
                >
                  {virtualMicReady ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                  {virtualMicReady ? "Virtual mic ready" : "Setup needed"}
                </span>
              </div>
            </div>

            {desktopMode === "semanticSuppression" ? (
              <div className="space-y-4">
                <PresetStrip presets={presets} selectedCategories={selectedCategories} onApply={applyPreset} />
                <CategorySelector categories={categories} selected={selectedCategories} onToggle={toggleCategory} />
                <details className="rounded-2xl border border-border bg-muted/25 p-4">
                  <summary className="cursor-pointer text-sm font-semibold text-foreground">Advanced sound strength</summary>
                  <label className="mt-4 block">
                    <div className="mb-2 flex items-center justify-between text-sm text-muted-foreground">
                      <span>Suppression strength</span>
                      <span className="font-mono text-foreground/80">x{aggressiveness.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min={0.5}
                      max={2.5}
                      step={0.05}
                      value={aggressiveness}
                      onChange={(event) => setAggressiveness(Number(event.target.value))}
                      className="w-full accent-[hsl(var(--primary))]"
                    />
                  </label>
                </details>
              </div>
            ) : (
              <div className="space-y-5">
                {renderSpeakerReference()}
                <div className="grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => setSpeakerOutputMode("remove_target")}
                    className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors ${
                      speakerOutputMode === "remove_target"
                        ? "border-accent/35 bg-accent/12 text-foreground"
                        : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
                    }`}
                  >
                    Suppress speaker
                  </button>
                  <button
                    type="button"
                    onClick={() => setSpeakerOutputMode("extract_target")}
                    className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors ${
                      speakerOutputMode === "extract_target"
                        ? "border-accent/35 bg-accent/12 text-foreground"
                        : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
                    }`}
                  >
                    Extract target
                  </button>
                </div>
              </div>
            )}

            <details className="rounded-2xl border border-border bg-muted/25 p-4">
              <summary className="cursor-pointer text-sm font-semibold text-foreground">Advanced microphone settings</summary>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="block">
                  <div className="mb-2 text-sm font-semibold text-foreground">Input microphone</div>
                  <select
                    value={inputDeviceId}
                    onChange={(event) => setInputDeviceId(event.target.value)}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
                  >
                    <option value="">System default</option>
                    {inputDevices.map((device) => (
                      <option key={device.id} value={device.id} disabled={device.virtualCable?.role === "recording"}>
                        {device.name}
                        {device.virtualCable?.role === "recording" ? " (target app mic)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <div className="mb-2 flex items-center justify-between text-sm font-semibold text-foreground">
                    <span>Responsiveness</span>
                    <span className="font-mono text-muted-foreground">{lookaheadMs} ms</span>
                  </div>
                  <input
                    type="range"
                    min={120}
                    max={500}
                    step={10}
                    value={lookaheadMs}
                    onChange={(event) => setLookaheadMs(Number(event.target.value))}
                    className="w-full accent-[hsl(var(--primary))]"
                  />
                </label>
              </div>
            </details>

            {liveBlockReason && (
              <div className="rounded-2xl border border-border bg-muted/25 px-4 py-3 text-sm text-muted-foreground">
                {liveBlockReason}
              </div>
            )}

            <div className="flex flex-wrap gap-3">
              {activeLiveSessionId ? (
                <button
                  type="button"
                  onClick={() => void stopLive()}
                  className="inline-flex items-center gap-2 rounded-2xl border border-destructive/35 bg-destructive/12 px-5 py-3 text-sm font-semibold text-destructive transition-colors hover:bg-destructive/18"
                >
                  <CircleStop className="h-4 w-4" />
                  Stop live processing
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void startLive()}
                  disabled={liveDisabled}
                  className="inline-flex items-center gap-2 rounded-2xl border border-primary/35 bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Play className="h-4 w-4" />
                  {isStartingLive ? "Starting..." : "Start live processing"}
                </button>
              )}
              <button
                type="button"
                onClick={() => void refreshDevices()}
                className="inline-flex items-center gap-2 rounded-2xl border border-border bg-card px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
              >
                <RefreshCw className="h-4 w-4" />
                Refresh devices
              </button>
            </div>
          </div>
        </Panel>
      </div>
      {renderStatusRail()}
    </div>
  );

  const renderFileTask = () => (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-5">
        <Panel
          eyebrow="File Render"
          title={desktopMode === "speakerSuppression" ? "Speaker file processing" : "Semantic file processing"}
          action={
            <span
              className={`rounded-full border px-3 py-1 text-[11px] font-mono uppercase tracking-[0.16em] ${
                activeOfflineJobId
                  ? "border-primary/35 bg-primary/12 text-primary"
                  : "border-border bg-muted/35 text-muted-foreground"
              }`}
            >
              {activeOfflineJobId ? "job active" : "idle"}
            </span>
          }
        >
          <div className="space-y-5">
            {renderModeSelector()}
            {desktopMode === "semanticSuppression" ? (
              <>
                <div className="space-y-4">
                  <PresetStrip presets={presets} selectedCategories={selectedCategories} onApply={applyPreset} />
                  <CategorySelector categories={categories} selected={selectedCategories} onToggle={toggleCategory} compact />
                </div>
                <PathInput
                  label="Input WAV"
                  value={inputPath}
                  onChange={setInputPath}
                  onBrowse={() => void browseInputPath()}
                  placeholder="C:\\path\\to\\input.wav"
                />
                <PathInput
                  label="Output WAV"
                  value={outputPath}
                  onChange={setOutputPath}
                  onBrowse={() => void browseOutputPath()}
                  placeholder="C:\\path\\to\\clean.wav"
                />
                <button
                  type="button"
                  onClick={() => void startOffline()}
                  disabled={isOfflineRunning || isLoading}
                  className="inline-flex items-center gap-2 rounded-2xl border border-accent/35 bg-accent px-5 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Wand2 className="h-4 w-4" />
                  {isOfflineRunning ? "Rendering..." : "Render clean WAV"}
                </button>
              </>
            ) : (
              <>
                {renderSpeakerReference()}
                <PathInput
                  label="Mixture WAV"
                  value={speakerInputPath}
                  onChange={setSpeakerInputPath}
                  onBrowse={() => void browseSpeakerInputPath()}
                  placeholder="C:\\path\\to\\mixture.wav"
                />
                <PathInput
                  label="Output WAV"
                  value={speakerOutputPath}
                  onChange={setSpeakerOutputPath}
                  onBrowse={() => void browseSpeakerOutputPath()}
                  placeholder="C:\\path\\to\\speaker_processed.wav"
                />
                <div className="grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => setSpeakerOutputMode("remove_target")}
                    className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors ${
                      speakerOutputMode === "remove_target"
                        ? "border-accent/35 bg-accent/12 text-foreground"
                        : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
                    }`}
                  >
                    Suppress speaker
                  </button>
                  <button
                    type="button"
                    onClick={() => setSpeakerOutputMode("extract_target")}
                    className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors ${
                      speakerOutputMode === "extract_target"
                        ? "border-accent/35 bg-accent/12 text-foreground"
                        : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
                    }`}
                  >
                    Extract target
                  </button>
                </div>
                <details className="rounded-2xl border border-border bg-muted/25 p-4">
                  <summary className="cursor-pointer text-sm font-semibold text-foreground">Advanced file settings</summary>
                  <div className="mt-4 space-y-4">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <button
                        type="button"
                        onClick={() => setSpeakerEngine("tsextract_onnx")}
                        className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors ${
                          speakerEngine === "tsextract_onnx"
                            ? "border-accent/35 bg-accent/12 text-foreground"
                            : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
                        }`}
                      >
                        Fast ONNX
                      </button>
                      <button
                        type="button"
                        onClick={() => setSpeakerEngine("clearvoice_bundle")}
                        disabled={!targetSpeakerInfo?.clearvoiceReady}
                        className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                          speakerEngine === "clearvoice_bundle"
                            ? "border-accent/35 bg-accent/12 text-foreground"
                            : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
                        }`}
                      >
                        Quality Bundle
                      </button>
                    </div>
                    <label className="block">
                      <div className="mb-2 flex items-center justify-between text-sm font-semibold text-foreground">
                        <span>Suppression strength</span>
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
                  </div>
                </details>
                <button
                  type="button"
                  onClick={() => void startSpeakerSuppression()}
                  disabled={isOfflineRunning || isLoading}
                  className="inline-flex items-center gap-2 rounded-2xl border border-accent/35 bg-accent px-5 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Wand2 className="h-4 w-4" />
                  {isOfflineRunning ? "Processing..." : speakerOutputMode === "remove_target" ? "Suppress speaker" : "Extract target"}
                </button>
              </>
            )}

            <button
              type="button"
              onClick={() => void cancelOffline()}
              disabled={!activeOfflineJobId}
              className="inline-flex items-center gap-2 rounded-2xl border border-border bg-card px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-destructive/35 hover:bg-destructive/8 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <CircleStop className="h-4 w-4" />
              Cancel job
            </button>
          </div>
        </Panel>
      </div>
      {renderStatusRail()}
    </div>
  );

  const renderProfilesTask = () => (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Panel eyebrow="Profiles" title="Speaker reference library">
        <div className="space-y-5">
          {renderSpeakerReference()}
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void saveCurrentSpeakerProfile()}
              disabled={!speakerReferenceReady || !speakerProfileName.trim()}
              className="inline-flex items-center gap-2 rounded-2xl border border-accent/35 bg-accent px-5 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <UserRound className="h-4 w-4" />
              Save profile
            </button>
            <button
              type="button"
              onClick={() => void deleteSelectedSpeakerProfile()}
              disabled={!selectedSpeakerProfileId}
              className="inline-flex items-center gap-2 rounded-2xl border border-border bg-card px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-destructive/35 hover:bg-destructive/8 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <CircleStop className="h-4 w-4" />
              Delete selected
            </button>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {speakerProfiles.map((profile) => (
              <button
                type="button"
                key={profile.id}
                onClick={() => setSelectedSpeakerProfileId(profile.id)}
                className={`rounded-2xl border p-4 text-left transition-colors ${
                  selectedSpeakerProfileId === profile.id
                    ? "border-accent/35 bg-accent/12"
                    : "border-border bg-background/60 hover:bg-muted/45"
                }`}
              >
                <div className="text-sm font-semibold text-foreground">{profile.name}</div>
                <div className="mt-2 truncate font-mono text-xs text-muted-foreground">{profile.referencePath}</div>
              </button>
            ))}
          </div>
        </div>
      </Panel>
      {renderStatusRail()}
    </div>
  );

  const renderStatusTask = () => (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Panel
        eyebrow="Status"
        title="System readiness"
        action={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                void refreshDevices();
                void refreshVirtualMicStatus();
                void refreshRuntimeMetrics();
                void refreshTargetSpeakerInfo();
              }}
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        }
      >
        <div className="grid gap-4 md:grid-cols-2">
          {[
            ["Virtual microphone", virtualMicReady ? "Ready" : "Needs setup", virtualMicReady],
            ["Input microphone", realMicBlocked ? "Select real microphone" : effectiveInputDevice?.name ?? "System default", !realMicBlocked],
            ["Live health", liveStatus?.realtimeHealth ?? "Idle", liveStatus?.realtimeHealth !== "overloaded"],
            ["Current workflow", modeLabel, true],
            ["Selected target", desktopMode === "speakerSuppression" ? speakerReadyText : semanticReadyText, desktopMode === "speakerSuppression" ? speakerReferenceReady : selectedCategories.length > 0],
            ["File job", activeOfflineJobId ? "Running" : "Idle", true],
          ].map(([label, value, ok]) => (
            <div key={label as string} className="rounded-2xl border border-border bg-muted/25 p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-xs font-mono uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
                  <div className="mt-2 text-sm font-semibold text-foreground">{value}</div>
                </div>
                {ok ? <CheckCircle2 className="h-5 w-5 text-accent" /> : <AlertCircle className="h-5 w-5 text-destructive" />}
              </div>
            </div>
          ))}
        </div>
      </Panel>
      {renderStatusRail()}
    </div>
  );

  function renderStatusRail() {
    return (
      <aside className="space-y-5 xl:sticky xl:top-5 xl:self-start">
        <section className="rounded-2xl border border-border bg-card/90 p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground">Now</div>
              <div className="mt-1 text-lg font-semibold text-foreground">{modeLabel}</div>
            </div>
            <Settings2 className="h-5 w-5 text-muted-foreground" />
          </div>
          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-border bg-muted/25 p-3">
              <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">
                Targets
              </div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {desktopMode === "speakerSuppression" ? speakerReadyText : semanticReadyText}
              </div>
            </div>

            <div className="rounded-xl border border-border bg-muted/25 p-3">
              <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">
                Target app microphone
              </div>
              <div className={`mt-1 break-words text-sm leading-5 ${virtualMicReady ? "text-accent" : "text-destructive"}`}>
                {virtualMicReady ? virtualMicRecordingName : "Not ready"}
              </div>
            </div>

            <div className="rounded-xl border border-border bg-muted/25 p-3">
              <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">
                Output device
              </div>
              <div className="mt-1 break-words text-sm leading-5 text-foreground/80">
                {virtualMicPlaybackName}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-border bg-muted/25 p-3">
                <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">
                  Inference
                </div>
                <div className="mt-1 font-mono text-sm text-foreground/80">
                  {formatMillis(liveStatus?.inferenceMs)}
                </div>
              </div>
              <div className="rounded-xl border border-border bg-muted/25 p-3">
                <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">
                  Health
                </div>
                <div className={`mt-1 text-sm font-semibold ${healthTone(liveStatus?.realtimeHealth)}`}>
                  {liveStatus?.realtimeHealth ?? "idle"}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-card/90 p-5 shadow-sm">
          <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground">Signal</div>
          <div className="mt-4 grid gap-4">
            <SignalMeter
              title="input"
              waveform={liveMeter?.waveformIn ?? []}
              peak={liveMeter?.peakIn ?? 0}
              rms={liveMeter?.rmsIn ?? 0}
              accentClass="bg-gradient-to-t from-[hsl(var(--neon-orange))] to-[hsl(var(--neon-pink))]"
            />
            <SignalMeter
              title="clean"
              waveform={liveMeter?.waveformOut ?? []}
              peak={liveMeter?.peakOut ?? 0}
              rms={liveMeter?.rmsOut ?? 0}
              accentClass="bg-gradient-to-t from-[hsl(var(--accent))] to-[hsl(var(--primary))]"
            />
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-card/90 p-5 shadow-sm">
          <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground">File progress</div>
          <div className="mt-3 text-sm font-semibold text-foreground">{offlineProgress?.stage ?? "No active render"}</div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-border/70">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[hsl(var(--accent))] to-[hsl(var(--primary))]"
              style={{ width: formatPercent(offlineProgress?.progress) }}
            />
          </div>
          <div className="mt-3 break-all text-xs text-muted-foreground">
            {offlineProgress?.outputPath || activeOutputPath || "Choose an output path before rendering."}
          </div>
        </section>
      </aside>
    );
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background transition-colors duration-300">
      <HeaderBar />

      <main className="flex-1 overflow-y-auto px-5 py-5">
        <div className="mx-auto flex max-w-7xl flex-col gap-5">
          <section className="rounded-2xl border border-border bg-card/90 p-5 shadow-sm">
            <div className="grid gap-5 lg:grid-cols-[1fr_auto] lg:items-center">
              <div>
                <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
                  Semantic Noise Cancellation
                </div>
                <h1 className="mt-2 text-2xl font-semibold text-foreground">Clean audio workspace</h1>
                <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                  Choose the task you want, keep the route visible, and leave diagnostics out of the way.
                </p>
              </div>
              <div className="grid gap-2 sm:grid-cols-4 lg:min-w-[640px]">
                {taskItems.map(({ id, label, description, icon: Icon }) => (
                  <button
                    type="button"
                    key={id}
                    onClick={() => setTask(id)}
                    className={`min-h-[76px] rounded-xl border p-3 text-left transition-colors ${
                      task === id
                        ? "border-primary/35 bg-primary/12 text-foreground"
                        : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span className="mt-2 block text-sm font-semibold">{label}</span>
                    <span className="mt-1 block text-xs leading-4">{description}</span>
                  </button>
                ))}
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
                  Dismiss
                </button>
              </div>
            </section>
          )}

          {task === "live" && renderLiveTask()}
          {task === "files" && renderFileTask()}
          {task === "profiles" && renderProfilesTask()}
          {task === "status" && renderStatusTask()}
        </div>
      </main>
    </div>
  );
};

export default UserDashboard;
