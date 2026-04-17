import { useState, useEffect } from "react";
import { Mic2, Music, Wind, Dog, Car, Bell, Volume2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const categories = [
  { name: "Speech", icon: Mic2, color: "hsl(262 83% 68%)", bgClass: "bg-primary/15 border-primary/30 text-primary" },
  { name: "Music", icon: Music, color: "hsl(330 80% 65%)", bgClass: "bg-neon-pink/15 border-neon-pink/30 text-neon-pink" },
  { name: "Ambient", icon: Wind, color: "hsl(174 72% 56%)", bgClass: "bg-neon-teal/15 border-neon-teal/30 text-neon-teal" },
  { name: "Animal", icon: Dog, color: "hsl(25 95% 62%)", bgClass: "bg-neon-orange/15 border-neon-orange/30 text-neon-orange" },
  { name: "Vehicle", icon: Car, color: "hsl(210 90% 62%)", bgClass: "bg-neon-blue/15 border-neon-blue/30 text-neon-blue" },
  { name: "Alert", icon: Bell, color: "hsl(142 70% 55%)", bgClass: "bg-neon-green/15 border-neon-green/30 text-neon-green" },
];

const SoundCategorization = () => {
  const [levels, setLevels] = useState<number[]>(categories.map(() => Math.random() * 100));
  const [sensitivity, setSensitivity] = useState(65);

  useEffect(() => {
    const interval = setInterval(() => {
      setLevels(prev => prev.map(v => Math.max(0, Math.min(100, v + (Math.random() - 0.5) * 30))));
    }, 800);
    return () => clearInterval(interval);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="glass-panel p-5"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Volume2 className="w-4 h-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground font-display">Sound Categories</h2>
        </div>
        <span className="text-[10px] font-mono text-muted-foreground">LIVE</span>
      </div>

      <div className="space-y-2">
        <AnimatePresence>
          {categories.map((cat, i) => {
            const level = levels[i];
            const detected = level > (100 - sensitivity);
            return (
              <motion.div
                key={cat.name}
                layout
                className={`flex items-center gap-3 p-2 rounded-lg border transition-colors ${
                  detected ? cat.bgClass : "bg-transparent border-transparent"
                }`}
              >
                <cat.icon className="w-4 h-4 shrink-0" style={{ color: cat.color }} />
                <span className="text-xs font-medium w-16 font-display">{cat.name}</span>
                <div className="flex-1 h-1.5 rounded-full bg-surface-3 overflow-hidden">
                  <motion.div
                    className="h-full rounded-full"
                    style={{ background: cat.color }}
                    animate={{ width: `${level}%` }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
                <span className="text-[10px] font-mono text-muted-foreground w-8 text-right">
                  {Math.round(level)}%
                </span>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      <div className="mt-4 pt-3 border-t border-border/30">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">Sensitivity</span>
          <span className="text-[10px] font-mono text-primary">{sensitivity}%</span>
        </div>
        <input
          type="range"
          min={10}
          max={95}
          value={sensitivity}
          onChange={e => setSensitivity(Number(e.target.value))}
          className="w-full h-1 rounded-full appearance-none bg-surface-3 cursor-pointer
            [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3
            [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:cursor-pointer
            [&::-webkit-slider-thumb]:shadow-[0_0_8px_hsl(262_83%_68%/0.4)]"
        />
      </div>
    </motion.div>
  );
};

export default SoundCategorization;
