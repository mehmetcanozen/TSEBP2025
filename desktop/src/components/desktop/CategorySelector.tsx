import type { ModelCategory } from "@/lib/desktop-api";

interface CategorySelectorProps {
  categories: ModelCategory[];
  selected: string[];
  onToggle: (categoryId: string) => void;
  compact?: boolean;
}

const accentByCategory = (categoryId: string) => {
  if (categoryId.includes("alarm") || categoryId.includes("ringing")) {
    return "border-red-400/30 bg-red-500/10 text-red-100";
  }
  if (categoryId.includes("wind") || categoryId.includes("rain") || categoryId.includes("water")) {
    return "border-sky-400/30 bg-sky-500/10 text-sky-100";
  }
  if (categoryId.includes("keyboard") || categoryId.includes("door")) {
    return "border-amber-400/30 bg-amber-500/10 text-amber-100";
  }
  return "border-primary/25 bg-primary/10 text-foreground";
};

const CategorySelector = ({
  categories,
  selected,
  onToggle,
  compact = false,
}: CategorySelectorProps) => {
  return (
    <div
      className={`grid gap-2 ${
        compact ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3"
      }`}
    >
      {categories.map((category) => {
        const isSelected = selected.includes(category.id);

        return (
          <button
            key={category.id}
            type="button"
            onClick={() => onToggle(category.id)}
            className={`rounded-2xl border px-4 py-3 text-left transition-all ${
              isSelected
                ? accentByCategory(category.id)
                : "border-border bg-card/70 text-foreground/82 hover:border-primary/35 hover:bg-muted/45"
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold capitalize">{category.label}</div>
                <div className="mt-1 text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
                  default x{category.defaultAggressiveness.toFixed(1)}
                </div>
              </div>
              {category.transient && (
                <span className="rounded-full border border-amber-400/25 bg-amber-500/10 px-2 py-1 text-[10px] font-mono uppercase tracking-wide text-amber-300">
                  transient
                </span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
};

export default CategorySelector;
