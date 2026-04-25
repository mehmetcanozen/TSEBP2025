import CategorySelector from "@/components/desktop/CategorySelector";
import PresetStrip from "@/components/desktop/PresetStrip";
import SignalMeter from "@/components/desktop/SignalMeter";
import { useDesktopRuntime } from "@/contexts/DesktopRuntimeContext";

const RealTimeMode = ({ compact = false }: { compact?: boolean }) => {
  const {
    categories,
    presets,
    selectedCategories,
    outputMode,
    virtualMicStatus,
    liveStatus,
    liveMeter,
    lookaheadMs,
    isStartingLive,
    activeLiveSessionId,
    error,
    toggleCategory,
    applyPreset,
    startLive,
    stopLive,
  } = useDesktopRuntime();
  const virtualMicBlocked = outputMode === "virtualMic" && !virtualMicStatus?.installed;

  return (
    <div className={compact ? "space-y-3 p-3" : "space-y-4 p-5"}>
      <div className="rounded-2xl border border-border bg-card/90 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
              Live monitor
            </div>
            <div className="mt-1 text-lg font-semibold text-foreground">
              {activeLiveSessionId ? "Suppression running" : "Ready to start"}
            </div>
          </div>
          <div
            className={`rounded-full border px-3 py-1 text-[10px] font-mono uppercase tracking-[0.16em] ${
              activeLiveSessionId
                ? "border-accent/30 bg-accent/15 text-accent"
                : "border-border bg-muted/35 text-muted-foreground"
            }`}
          >
            {liveStatus?.state ?? "idle"}
          </div>
        </div>

        <div className="mt-3 text-xs text-muted-foreground">
          {outputMode === "virtualMic" ? "virtual mic" : "local monitor"} / lookahead {lookaheadMs} ms / inference{" "}
          {liveStatus?.inferenceMs?.toFixed(0) ?? "--"} ms / xruns {liveStatus?.xruns ?? 0}
        </div>

        {outputMode === "virtualMic" && (
          <div className="mt-2 text-xs text-muted-foreground">
            Target mic: {virtualMicStatus?.recordingDeviceName ?? "CABLE Output"}
          </div>
        )}

        {error && (
          <div className="mt-3 rounded-xl border border-destructive/35 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        )}

        <div className="mt-4">
          <PresetStrip
            presets={presets}
            selectedCategories={selectedCategories}
            onApply={applyPreset}
            compact
          />
        </div>

        <div className="mt-4">
          <CategorySelector
            categories={categories}
            selected={selectedCategories}
            onToggle={toggleCategory}
            compact
          />
        </div>

        <div className="mt-4 flex gap-3">
          {activeLiveSessionId ? (
            <button
              type="button"
              onClick={() => void stopLive()}
              className="flex-1 rounded-xl border border-destructive/35 bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive"
            >
              Stop processing
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void startLive()}
              disabled={isStartingLive || virtualMicBlocked}
              className="flex-1 rounded-xl border border-primary/35 bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-60"
            >
              {isStartingLive ? "Starting..." : "Start processing"}
            </button>
          )}
        </div>
      </div>

      <div className={`grid gap-3 ${compact ? "grid-cols-1" : "grid-cols-2"}`}>
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
    </div>
  );
};

export default RealTimeMode;
