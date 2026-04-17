import type { Hive15Preset } from "@/lib/desktop-api";

interface PresetStripProps {
  presets: Hive15Preset[];
  selectedCategories: string[];
  onApply: (presetId: string) => void;
  compact?: boolean;
}

const PresetStrip = ({
  presets,
  selectedCategories,
  onApply,
  compact = false,
}: PresetStripProps) => {
  return (
    <div className="flex flex-wrap gap-2">
      {presets.map((preset) => {
        const matchesPreset =
          preset.categories.length === selectedCategories.length &&
          preset.categories.every((category) => selectedCategories.includes(category));

        return (
          <button
            key={preset.id}
            type="button"
            onClick={() => onApply(preset.id)}
            className={`rounded-full border px-3 py-2 text-left transition-all ${
              matchesPreset
                ? "border-accent/40 bg-accent/15 text-foreground"
                : "border-border bg-card text-foreground/78 hover:border-accent/30 hover:bg-accent/8"
            } ${compact ? "w-full" : ""}`}
            title={preset.description}
          >
            <div className="text-xs font-semibold">{preset.name}</div>
            <div className="mt-1 text-[10px] font-mono uppercase tracking-[0.16em] text-muted-foreground">
              {preset.categories.length} categories
            </div>
          </button>
        );
      })}
    </div>
  );
};

export default PresetStrip;
