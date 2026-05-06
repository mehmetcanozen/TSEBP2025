import { useEffect, useState, type ReactNode } from "react";
import HeaderBar from "@/components/HeaderBar";
import CategorySelector from "@/components/desktop/CategorySelector";
import PresetStrip from "@/components/desktop/PresetStrip";
import SignalMeter from "@/components/desktop/SignalMeter";
import TransmissionTestPanel from "@/components/desktop/TransmissionTestPanel";
import { useDesktopRuntime } from "@/contexts/DesktopRuntimeContext";
import {
  Activity,
  AlertTriangle,
  AudioWaveform,
  Bug,
  CircleStop,
  FileAudio,
  FolderOpen,
  Gauge,
  Play,
  RefreshCw,
  Scissors,
  Settings2,
  UserRound,
  Waves,
} from "lucide-react";

type DevTask = "semantic" | "speaker" | "transmission" | "runtime";

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

const devTasks: Array<{ id: DevTask; label: string; description: string; icon: typeof Bug }> = [
  { id: "semantic", label: "Semantic Debug", description: "Targets, routing, Debug WAV", icon: AudioWaveform },
  { id: "speaker", label: "Speaker Debug", description: "Reference, engine, routing", icon: Scissors },
  { id: "transmission", label: "Transmission", description: "Loopback and calibration", icon: Waves },
  { id: "runtime", label: "Runtime / Devices", description: "Provider and device truth", icon: Gauge },
];

const Panel = ({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
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
  disabled,
}: {
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onBrowse: () => void;
  disabled?: boolean;
}) => (
  <label className="block">
    <div className="mb-2 text-sm font-semibold text-foreground">{label}</div>
    <div className="flex flex-col gap-2 sm:flex-row">
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="min-w-0 flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground disabled:cursor-not-allowed disabled:opacity-60"
      />
      <button
        type="button"
        onClick={onBrowse}
        disabled={disabled}
        className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <FolderOpen className="h-4 w-4" />
        Browse
      </button>
    </div>
  </label>
);

const DevDashboard = () => {
  const [task, setTask] = useState<DevTask>("semantic");
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
    setInputDeviceId,
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

  useEffect(() => {
    if (task === "semantic" && desktopMode !== "semanticSuppression") {
      setDesktopMode("semanticSuppression");
    }
    if (task === "speaker" && desktopMode !== "speakerSuppression") {
      setDesktopMode("speakerSuppression");
    }
  }, [desktopMode, setDesktopMode, task]);

  const inputDevices = devices.filter((device) => device.direction === "input");
  const outputDevices = devices.filter((device) => device.direction === "output");
  const selectedInputDevice = inputDevices.find((device) => device.id === inputDeviceId);
  const effectiveInputDevice = selectedInputDevice ?? inputDevices.find((device) => device.default);
  const virtualMicReady = Boolean(virtualMicStatus?.installed && virtualMicStatus.playbackDeviceId);
  const virtualMicPlaybackName = virtualMicStatus?.playbackDeviceName ?? "CABLE Input";
  const virtualMicRecordingName = virtualMicStatus?.recordingDeviceName ?? "CABLE Output";
  const selectedSpeakerProfile = speakerProfiles.find((profile) => profile.id === selectedSpeakerProfileId);
  const liveMicUsesCableOutput = !debugInputEnabled && effectiveInputDevice?.virtualCable?.role === "recording";
  const speakerReferenceReady = Boolean(speakerReferencePath.trim());
  const activeOutputPath = desktopMode === "speakerSuppression" ? speakerOutputPath : outputPath;

  const semanticBlockReason = !virtualMicReady
    ? "VB-CABLE playback endpoint is required."
    : liveMicUsesCableOutput
      ? "Choose a real microphone. CABLE Output is the target app microphone."
      : selectedCategories.length === 0
        ? "Select at least one category."
        : debugInputEnabled && !debugInputPath.trim()
          ? "Choose a Debug WAV file."
          : null;

  const speakerBlockReason = !virtualMicReady
    ? "VB-CABLE playback endpoint is required."
    : speakerEngine !== "tsextract_onnx"
      ? "Realtime speaker debug uses Fast ONNX."
      : liveMicUsesCableOutput
        ? "Choose a real microphone. CABLE Output is the target app microphone."
        : !speakerReferenceReady
          ? "Choose a reference clip or saved profile."
          : debugInputEnabled && !debugInputPath.trim()
            ? "Choose a Debug WAV file."
            : null;

  const liveBlockReason = desktopMode === "speakerSuppression" ? speakerBlockReason : semanticBlockReason;
  const liveDisabled = isLoading || isStartingLive || Boolean(liveBlockReason);

  const selectTask = (nextTask: DevTask) => {
    setTask(nextTask);
    if (nextTask === "semantic") setDesktopMode("semanticSuppression");
    if (nextTask === "speaker") setDesktopMode("speakerSuppression");
  };

  const renderDebugSourceControls = () => (
    <Panel eyebrow="Source" title="Realtime source and capture">
      <div className="space-y-5">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <div className="mb-2 text-sm font-semibold text-foreground">Live microphone</div>
            <select
              value={inputDeviceId}
              onChange={(event) => setInputDeviceId(event.target.value)}
              disabled={debugInputEnabled || Boolean(activeLiveSessionId)}
              className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground disabled:cursor-not-allowed disabled:opacity-60"
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
            <div className="mb-2 text-sm font-semibold text-foreground">VB-CABLE sink</div>
            <select
              value={virtualMicStatus?.playbackDeviceId ?? ""}
              disabled
              className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground disabled:opacity-80"
            >
              <option value="">System default</option>
              {outputDevices.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.name}
                  {device.virtualCable?.role === "playback" ? " -> virtual mic" : ""}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <button
            type="button"
            onClick={() => setDebugInputEnabled(false)}
            disabled={Boolean(activeLiveSessionId)}
            className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
              !debugInputEnabled
                ? "border-primary/35 bg-primary/12 text-foreground"
                : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
            }`}
          >
            Live mic source
          </button>
          <button
            type="button"
            onClick={() => setDebugInputEnabled(true)}
            disabled={Boolean(activeLiveSessionId)}
            className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
              debugInputEnabled
                ? "border-primary/35 bg-primary/12 text-foreground"
                : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
            }`}
          >
            Debug WAV source
          </button>
        </div>

        {debugInputEnabled && (
          <PathInput
            label="Debug WAV file"
            value={debugInputPath}
            placeholder="C:\\path\\to\\debug_source.wav"
            onChange={setDebugInputPath}
            onBrowse={() => void browseDebugInputPath()}
            disabled={Boolean(activeLiveSessionId)}
          />
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <div className="mb-2 flex items-center justify-between text-sm font-semibold text-foreground">
              <span>Lookahead</span>
              <span className="font-mono text-muted-foreground">{lookaheadMs} ms</span>
            </div>
            <input
              type="range"
              min={120}
              max={500}
              step={10}
              value={lookaheadMs}
              onChange={(event) => setLookaheadMs(Number(event.target.value))}
              disabled={Boolean(activeLiveSessionId)}
              className="w-full accent-[hsl(var(--primary))] disabled:opacity-60"
            />
          </label>
          <div className="rounded-xl border border-border bg-muted/25 p-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-sm font-semibold text-foreground">Record live output</div>
                <div className="mt-1 text-xs text-muted-foreground">Save processed realtime output to WAV.</div>
              </div>
              <button
                type="button"
                onClick={() => setRecordEnabled(!recordEnabled)}
                disabled={Boolean(activeLiveSessionId)}
                className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] disabled:cursor-not-allowed disabled:opacity-60 ${
                  recordEnabled
                    ? "border-primary/35 bg-primary/15 text-primary"
                    : "border-border bg-card text-muted-foreground"
                }`}
              >
                {recordEnabled ? "on" : "off"}
              </button>
            </div>
          </div>
        </div>

        {recordEnabled && (
          <PathInput
            label="Record output WAV"
            value={recordOutputPath}
            placeholder="C:\\path\\to\\live_debug_output.wav"
            onChange={setRecordOutputPath}
            onBrowse={() => void browseRecordOutputPath()}
            disabled={Boolean(activeLiveSessionId)}
          />
        )}
      </div>
    </Panel>
  );

  const renderSpeakerReferenceControls = () => (
    <Panel eyebrow="Reference" title="Speaker target and profile">
      <div className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
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
          label="Reference speaker clip"
          value={speakerReferencePath}
          placeholder="C:\\path\\to\\speaker_reference.wav"
          onChange={setSpeakerReferencePath}
          onBrowse={() => void browseSpeakerReferencePath()}
        />

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void saveCurrentSpeakerProfile()}
            disabled={!speakerReferenceReady || !speakerProfileName.trim()}
            className="rounded-2xl border border-accent/35 bg-accent px-5 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Save profile
          </button>
          <button
            type="button"
            onClick={() => void deleteSelectedSpeakerProfile()}
            disabled={!selectedSpeakerProfileId}
            className="rounded-2xl border border-border bg-card px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-destructive/35 hover:bg-destructive/8 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Delete selected
          </button>
        </div>
      </div>
    </Panel>
  );

  const renderLiveActions = (label: string) => (
    <Panel
      eyebrow="Live session"
      title={label}
      action={
        <span
          className={`rounded-full border px-3 py-1 text-[11px] font-mono uppercase tracking-[0.16em] ${
            activeLiveSessionId
              ? "border-accent/35 bg-accent/15 text-accent"
              : "border-border bg-muted/35 text-muted-foreground"
          }`}
        >
          {activeLiveSessionId ? "running" : "stopped"}
        </span>
      }
    >
      <div className="space-y-4">
        <div className="rounded-xl border border-border bg-muted/25 p-4">
          <div className="text-sm font-semibold text-foreground">
            {debugInputEnabled ? "Debug WAV" : "Live mic"} {"->"} {virtualMicPlaybackName}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Target apps should capture from {virtualMicRecordingName}.
          </div>
        </div>

        {liveBlockReason && (
          <div className="rounded-xl border border-border bg-muted/25 px-4 py-3 text-sm text-muted-foreground">
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
              Stop live route
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void startLive()}
              disabled={liveDisabled}
              className="inline-flex items-center gap-2 rounded-2xl border border-primary/35 bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Play className="h-4 w-4" />
              {isStartingLive ? "Starting..." : "Start live route"}
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
  );

  const renderSemanticDebug = () => (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-5">
        <Panel eyebrow="Semantic debug" title="Targets and inference tuning">
          <div className="space-y-5">
            <PresetStrip presets={presets} selectedCategories={selectedCategories} onApply={applyPreset} />
            <CategorySelector categories={categories} selected={selectedCategories} onToggle={toggleCategory} />
            <label className="block rounded-xl border border-border bg-muted/25 p-4">
              <div className="mb-2 flex items-center justify-between text-sm font-semibold text-foreground">
                <span>Aggressiveness</span>
                <span className="font-mono text-muted-foreground">x{aggressiveness.toFixed(2)}</span>
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
          </div>
        </Panel>
        {renderDebugSourceControls()}
        {renderLiveActions("Semantic realtime debug route")}
        <Panel eyebrow="Offline" title="Semantic offline render">
          <div className="space-y-4">
            <PathInput
              label="Input WAV"
              value={inputPath}
              placeholder="C:\\path\\to\\input.wav"
              onChange={setInputPath}
              onBrowse={() => void browseInputPath()}
            />
            <PathInput
              label="Output WAV"
              value={outputPath}
              placeholder="C:\\path\\to\\clean.wav"
              onChange={setOutputPath}
              onBrowse={() => void browseOutputPath()}
            />
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void startOffline()}
                disabled={isOfflineRunning || isLoading}
                className="rounded-2xl border border-accent/35 bg-accent px-5 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isOfflineRunning ? "Rendering..." : "Render semantic WAV"}
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
        </Panel>
      </div>
      {renderStatusRail()}
    </div>
  );

  const renderSpeakerDebug = () => (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-5">
        {renderSpeakerReferenceControls()}
        <Panel eyebrow="Speaker engine" title="Engine and output mode">
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-2">
              <button
                type="button"
                onClick={() => setSpeakerEngine("tsextract_onnx")}
                disabled={Boolean(activeLiveSessionId)}
                className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
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
                disabled={Boolean(activeLiveSessionId) || !targetSpeakerInfo?.clearvoiceReady}
                className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                  speakerEngine === "clearvoice_bundle"
                    ? "border-accent/35 bg-accent/12 text-foreground"
                    : "border-border bg-background/60 text-muted-foreground hover:bg-muted/45 hover:text-foreground"
                }`}
              >
                Quality Bundle
              </button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
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
            <label className="block rounded-xl border border-border bg-muted/25 p-4">
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
          </div>
        </Panel>
        {renderDebugSourceControls()}
        {renderLiveActions("Speaker realtime debug route")}
        <Panel eyebrow="Offline" title="Speaker offline render">
          <div className="space-y-4">
            <PathInput
              label="Mixture WAV"
              value={speakerInputPath}
              placeholder="C:\\path\\to\\mixture.wav"
              onChange={setSpeakerInputPath}
              onBrowse={() => void browseSpeakerInputPath()}
            />
            <PathInput
              label="Output WAV"
              value={speakerOutputPath}
              placeholder="C:\\path\\to\\speaker_processed.wav"
              onChange={setSpeakerOutputPath}
              onBrowse={() => void browseSpeakerOutputPath()}
            />
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void startSpeakerSuppression()}
                disabled={isOfflineRunning || isLoading}
                className="rounded-2xl border border-accent/35 bg-accent px-5 py-3 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isOfflineRunning ? "Processing..." : "Process speaker WAV"}
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
        </Panel>
      </div>
      {renderStatusRail()}
    </div>
  );

  const renderTransmission = () => (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <TransmissionTestPanel />
      {renderStatusRail()}
    </div>
  );

  const renderRuntimeDevices = () => (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-5">
        <Panel
          eyebrow="Runtime"
          title="Model and provider state"
          action={
            <button
              type="button"
              onClick={() => {
                void refreshRuntimeMetrics();
                void refreshTargetSpeakerInfo();
                void refreshVirtualMicStatus();
              }}
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          }
        >
          <div className="grid gap-3 md:grid-cols-2">
            {[
              ["Model", runtimeMetrics?.displayName ?? "--"],
              ["Provider", runtimeMetrics?.provider ?? "--"],
              ["Runtime", runtimeMetrics?.runtimeKind ?? "--"],
              ["Model rate", runtimeMetrics?.modelSampleRate ? `${runtimeMetrics.modelSampleRate} Hz` : "--"],
              ["Hop", formatMillis(runtimeMetrics?.preferredLiveHopMs)],
              ["Chunk", runtimeMetrics?.chunkSamples ? `${runtimeMetrics.chunkSamples} samples` : "--"],
              ["Providers", runtimeMetrics?.availableProviders.join(", ") || "--"],
              ["Validation", runtimeMetrics?.validationStatus ?? "--"],
              ["Active live", `${runtimeMetrics?.activeLiveSessions ?? 0}`],
              ["Active jobs", `${runtimeMetrics?.activeJobs ?? 0}`],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-border bg-muted/25 p-4">
                <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
                <div className="mt-1 break-words text-sm font-semibold text-foreground">{value}</div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel eyebrow="Target speaker" title={targetSpeakerInfo?.displayName ?? "Target speaker runtime"}>
          <div className="grid gap-3 md:grid-cols-2">
            {[
              ["Default engine", targetSpeakerInfo?.defaultEngine ?? "--"],
              ["Available engines", targetSpeakerInfo?.availableEngines.join(", ") || "--"],
              ["Model rate", targetSpeakerInfo?.modelSampleRate ? `${targetSpeakerInfo.modelSampleRate} Hz` : "--"],
              ["Mixture window", targetSpeakerInfo?.mixtureSamples ? `${targetSpeakerInfo.mixtureSamples} samples` : "--"],
              ["Reference window", targetSpeakerInfo?.referenceSamples ? `${targetSpeakerInfo.referenceSamples} samples` : "--"],
              ["ONNX sidecar", targetSpeakerInfo?.onnxSidecarPresent ? "ready" : "missing"],
              ["ClearVoice", targetSpeakerInfo?.clearvoiceReady ? "ready" : "setup needed"],
              ["Validation", targetSpeakerInfo?.validationStatus ?? "--"],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-border bg-muted/25 p-4">
                <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
                <div className="mt-1 break-words text-sm font-semibold text-foreground">{value}</div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          eyebrow="Devices"
          title="Audio endpoint inventory"
          action={
            <button
              type="button"
              onClick={() => void refreshDevices()}
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary/30 hover:bg-primary/10"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh devices
            </button>
          }
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <div className="mb-3 text-sm font-semibold text-foreground">Inputs</div>
              <div className="space-y-2">
                {inputDevices.map((device) => (
                  <div key={device.id} className="rounded-xl border border-border bg-muted/25 p-3">
                    <div className="break-words text-sm font-semibold text-foreground">{device.name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {device.default ? "default / " : ""}
                      {device.virtualCable?.role ?? "input"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-3 text-sm font-semibold text-foreground">Outputs</div>
              <div className="space-y-2">
                {outputDevices.map((device) => (
                  <div key={device.id} className="rounded-xl border border-border bg-muted/25 p-3">
                    <div className="break-words text-sm font-semibold text-foreground">{device.name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {device.default ? "default / " : ""}
                      {device.virtualCable?.role ?? "output"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Panel>
      </div>
      {renderStatusRail()}
    </div>
  );

  function renderStatusRail() {
    const targetLabel =
      desktopMode === "speakerSuppression"
        ? selectedSpeakerProfile?.name ?? (speakerReferencePath ? "manual clip" : "no reference")
        : selectedCategories.length
          ? `${selectedCategories.length} categories`
          : "no categories";

    return (
      <aside className="space-y-5 xl:sticky xl:top-5 xl:self-start">
        <section className="rounded-2xl border border-border bg-card/90 p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground">Dev state</div>
              <div className="mt-1 text-lg font-semibold text-foreground">
                {desktopMode === "speakerSuppression" ? "Speaker" : "Semantic"}
              </div>
            </div>
            <Bug className="h-5 w-5 text-muted-foreground" />
          </div>
          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-border bg-muted/25 p-3">
              <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">Target</div>
              <div className="mt-1 break-words text-sm font-semibold text-foreground">{targetLabel}</div>
            </div>
            <div className="rounded-xl border border-border bg-muted/25 p-3">
              <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">Source</div>
              <div className="mt-1 break-words text-sm text-foreground/80">
                {debugInputEnabled ? debugInputPath || "Debug WAV not selected" : effectiveInputDevice?.name ?? "System default"}
              </div>
            </div>
            <div className="rounded-xl border border-border bg-muted/25 p-3">
              <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">Target app mic</div>
              <div className={`mt-1 break-words text-sm ${virtualMicReady ? "text-accent" : "text-destructive"}`}>
                {virtualMicReady ? virtualMicRecordingName : "not ready"}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-border bg-muted/25 p-3">
                <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">Inference</div>
                <div className="mt-1 font-mono text-sm text-foreground/80">{formatMillis(liveStatus?.inferenceMs)}</div>
              </div>
              <div className="rounded-xl border border-border bg-muted/25 p-3">
                <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground">Health</div>
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
              title="processed"
              waveform={liveMeter?.waveformOut ?? []}
              peak={liveMeter?.peakOut ?? 0}
              rms={liveMeter?.rmsOut ?? 0}
              accentClass="bg-gradient-to-t from-[hsl(var(--accent))] to-[hsl(var(--primary))]"
            />
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-card/90 p-5 shadow-sm">
          <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground">Job progress</div>
          <div className="mt-3 text-sm font-semibold text-foreground">{offlineProgress?.stage ?? "No active job"}</div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-border/70">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[hsl(var(--accent))] to-[hsl(var(--primary))]"
              style={{ width: formatPercent(offlineProgress?.progress) }}
            />
          </div>
          <div className="mt-3 break-all text-xs text-muted-foreground">
            {offlineProgress?.outputPath || activeOutputPath || "No output path selected."}
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
                  Developer diagnostics
                </div>
                <h1 className="mt-2 text-2xl font-semibold text-foreground">Debug console</h1>
                <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                  Debug one subsystem at a time: semantic routing, speaker routing, transmission, or runtime/device truth.
                </p>
              </div>
              <div className="grid gap-2 sm:grid-cols-4 lg:min-w-[720px]">
                {devTasks.map(({ id, label, description, icon: Icon }) => (
                  <button
                    type="button"
                    key={id}
                    onClick={() => selectTask(id)}
                    className={`min-h-[80px] rounded-xl border p-3 text-left transition-colors ${
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
                <span className="inline-flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  {error}
                </span>
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

          {task === "semantic" && renderSemanticDebug()}
          {task === "speaker" && renderSpeakerDebug()}
          {task === "transmission" && renderTransmission()}
          {task === "runtime" && renderRuntimeDevices()}
        </div>
      </main>
    </div>
  );
};

export default DevDashboard;
