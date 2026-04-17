import { useState } from "react";
import { Sparkles, Wand2 } from "lucide-react";
import { motion } from "framer-motion";

const MiniWaveform = ({ variant }: { variant: "before" | "after" }) => {
  const bars = Array(35)
    .fill(0)
    .map(() =>
      variant === "before"
        ? 0.15 + Math.random() * 0.85
        : 0.1 + Math.random() * 0.5
    );

  return (
    <div className="flex items-center h-14 gap-[2px] px-2">
      {bars.map((h, i) => (
        <div
          key={i}
          className="rounded-full"
          style={{
            width: "2.5px",
            height: `${h * 100}%`,
            background:
              variant === "before"
                ? `hsl(25 95% 62% / ${0.4 + h * 0.6})`
                : `hsl(174 72% 56% / ${0.4 + h * 0.6})`,
          }}
        />
      ))}
    </div>
  );
};

const NoiseRemovalPanel = () => {
  const [active, setActive] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="glass-panel p-5"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Wand2 className="w-4 h-4 text-neon-teal" />
          <h2 className="text-sm font-semibold text-foreground font-display">
            Noise Removal
          </h2>
        </div>
        <motion.button
          whileTap={{ scale: 0.9 }}
          onClick={() => setActive(!active)}
          className={`relative w-11 h-6 rounded-full transition-colors ${
            active ? "bg-neon-teal/30" : "bg-surface-3"
          }`}
        >
          <motion.div
            className={`absolute top-0.5 w-5 h-5 rounded-full ${
              active ? "bg-neon-teal glow-teal" : "bg-muted-foreground/50"
            }`}
            animate={{ left: active ? "22px" : "2px" }}
            transition={{ type: "spring", stiffness: 500, damping: 30 }}
          />
        </motion.button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-surface-2/60 border border-border/30 p-3">
          <div className="flex items-center gap-1.5 mb-2">
            <div className="w-1.5 h-1.5 rounded-full bg-neon-orange" />
            <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
              Before
            </span>
          </div>
          <MiniWaveform variant="before" />
        </div>
        <div className="rounded-lg bg-surface-2/60 border border-border/30 p-3 relative overflow-hidden">
          <div className="flex items-center gap-1.5 mb-2">
            <div className="w-1.5 h-1.5 rounded-full bg-neon-teal" />
            <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
              After
            </span>
          </div>
          <MiniWaveform variant="after" />
          {active && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="absolute top-2 right-2"
            >
              <Sparkles className="w-3.5 h-3.5 text-neon-teal animate-float" />
            </motion.div>
          )}
        </div>
      </div>

      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        className="w-full mt-3 py-2 rounded-lg bg-gradient-to-r from-neon-teal/15 to-primary/15 border border-neon-teal/30 text-neon-teal text-xs font-medium font-display flex items-center justify-center gap-2 hover:from-neon-teal/25 hover:to-primary/25 transition-all"
      >
        <Sparkles className="w-3.5 h-3.5" />
        Clean Audio
      </motion.button>
    </motion.div>
  );
};

export default NoiseRemovalPanel;
