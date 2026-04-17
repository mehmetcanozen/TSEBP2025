import { useState } from "react";
import { SlidersHorizontal, ChevronLeft, ChevronRight } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const SliderControl = ({
  label,
  value,
  onChange,
  min = 0,
  max = 100,
  unit = "%",
  color = "primary",
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  unit?: string;
  color?: string;
}) => (
  <div className="mb-5">
    <div className="flex items-center justify-between mb-2">
      <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">{label}</span>
      <span className="text-[10px] font-mono text-primary">
        {value}{unit}
      </span>
    </div>
    <input
      type="range"
      min={min}
      max={max}
      value={value}
      onChange={e => onChange(Number(e.target.value))}
      className={`w-full h-1 rounded-full appearance-none bg-surface-3 cursor-pointer
        [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3
        [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-${color} [&::-webkit-slider-thumb]:cursor-pointer`}
    />
  </div>
);

const ToggleRow = ({ label, active, onToggle }: { label: string; active: boolean; onToggle: () => void }) => (
  <div className="flex items-center justify-between py-2">
    <span className="text-xs font-display text-foreground/80">{label}</span>
    <motion.button
      whileTap={{ scale: 0.9 }}
      onClick={onToggle}
      className={`relative w-9 h-5 rounded-full transition-colors ${active ? "bg-primary/30" : "bg-surface-3"}`}
    >
      <motion.div
        className={`absolute top-0.5 w-4 h-4 rounded-full ${active ? "bg-primary" : "bg-muted-foreground/50"}`}
        animate={{ left: active ? "18px" : "2px" }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
      />
    </motion.button>
  </div>
);

const SettingsSidebar = () => {
  const [open, setOpen] = useState(true);
  const [noiseThreshold, setNoiseThreshold] = useState(42);
  const [sensitivity, setSensitivity] = useState(65);
  const [sampleRate, setSampleRate] = useState(48);
  const [autoRecord, setAutoRecord] = useState(false);
  const [realtime, setRealtime] = useState(true);
  const [gpu, setGpu] = useState(true);

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 260, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="h-full border-l border-border/50 overflow-hidden flex-shrink-0"
            style={{ background: "hsl(228 18% 8%)" }}
          >
            <div className="p-5 w-[260px]">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                  <SlidersHorizontal className="w-4 h-4 text-primary" />
                  <h2 className="text-sm font-semibold text-foreground font-display">Settings</h2>
                </div>
                <motion.button
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={() => setOpen(false)}
                  className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </motion.button>
              </div>

              <div className="space-y-1">
                <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-3">Audio Processing</p>
                <SliderControl label="Noise Threshold" value={noiseThreshold} onChange={setNoiseThreshold} />
                <SliderControl label="Sensitivity" value={sensitivity} onChange={setSensitivity} />
                <SliderControl label="Sample Rate" value={sampleRate} onChange={setSampleRate} min={8} max={96} unit="kHz" />
              </div>

              <div className="border-t border-border/30 pt-4 mt-2">
                <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-3">Preferences</p>
                <ToggleRow label="Auto-record" active={autoRecord} onToggle={() => setAutoRecord(!autoRecord)} />
                <ToggleRow label="Real-time processing" active={realtime} onToggle={() => setRealtime(!realtime)} />
                <ToggleRow label="GPU acceleration" active={gpu} onToggle={() => setGpu(!gpu)} />
              </div>

              <div className="border-t border-border/30 pt-4 mt-4">
                <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-3">Output</p>
                <div className="space-y-2">
                  <select className="w-full bg-surface-2 border border-border/30 rounded-lg px-3 py-1.5 text-xs font-display text-foreground/80 outline-none focus:border-primary/40">
                    <option>WAV (Lossless)</option>
                    <option>MP3 (320kbps)</option>
                    <option>FLAC</option>
                    <option>OGG</option>
                  </select>
                  <select className="w-full bg-surface-2 border border-border/30 rounded-lg px-3 py-1.5 text-xs font-display text-foreground/80 outline-none focus:border-primary/40">
                    <option>Mono</option>
                    <option>Stereo</option>
                  </select>
                </div>
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {!open && (
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={() => setOpen(true)}
            className="fixed right-3 top-1/2 -translate-y-1/2 z-10 w-8 h-8 rounded-lg bg-card border border-border/50 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </motion.button>
        )}
      </AnimatePresence>
    </>
  );
};

export default SettingsSidebar;
