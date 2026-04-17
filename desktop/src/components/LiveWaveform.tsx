import { useState, useEffect, useRef } from "react";
import { Mic, Square, Circle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const LiveWaveform = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [bars, setBars] = useState<number[]>(Array(60).fill(0.15));
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (isRecording) {
      intervalRef.current = setInterval(() => {
        setBars(prev =>
          prev.map(() => 0.1 + Math.random() * 0.9)
        );
      }, 80);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
      setBars(prev => prev.map(() => 0.08 + Math.random() * 0.12));
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isRecording]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="glass-panel p-5"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground font-display">Live Audio</h2>
          <AnimatePresence>
            {isRecording && (
              <motion.div
                initial={{ opacity: 0, scale: 0 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0 }}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-destructive/15 border border-destructive/30"
              >
                <Circle className="w-2 h-2 fill-destructive text-destructive animate-pulse-glow" />
                <span className="text-[10px] font-mono text-destructive font-medium tracking-wider">REC</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
          <span>48kHz</span>
          <span className="text-border">|</span>
          <span>16-bit</span>
          <span className="text-border">|</span>
          <span>Stereo</span>
        </div>
      </div>

      <div className="relative h-32 rounded-lg bg-surface-2/60 border border-border/30 overflow-hidden flex items-center justify-center px-2 gap-[2px]">
        {/* Gradient overlay */}
        <div
          className="absolute inset-0 pointer-events-none opacity-30"
          style={{
            background: isRecording
              ? "linear-gradient(90deg, hsl(262 83% 68% / 0.1), hsl(174 72% 56% / 0.15), hsl(262 83% 68% / 0.1))"
              : "none",
          }}
        />
        {bars.map((h, i) => (
          <motion.div
            key={i}
            className="rounded-full"
            style={{
              width: "3px",
              background: isRecording
                ? `linear-gradient(180deg, hsl(174 72% 56%), hsl(262 83% 68%))`
                : `hsl(220 10% 30%)`,
            }}
            animate={{ height: `${h * 100}%` }}
            transition={{ duration: 0.08, ease: "easeOut" }}
          />
        ))}
        {/* Center line */}
        <div className="absolute left-0 right-0 h-[1px] bg-border/20 top-1/2" />
      </div>

      <div className="flex items-center justify-center mt-4">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => setIsRecording(!isRecording)}
          className={`flex items-center gap-2 px-6 py-2.5 rounded-full font-display font-medium text-sm transition-all ${
            isRecording
              ? "bg-destructive/15 text-destructive border border-destructive/40 glow-pink"
              : "bg-primary/15 text-primary border border-primary/40 glow-purple"
          }`}
        >
          {isRecording ? (
            <>
              <Square className="w-3.5 h-3.5 fill-current" />
              Stop Recording
            </>
          ) : (
            <>
              <Mic className="w-3.5 h-3.5" />
              Start Recording
            </>
          )}
        </motion.button>
      </div>
    </motion.div>
  );
};

export default LiveWaveform;
