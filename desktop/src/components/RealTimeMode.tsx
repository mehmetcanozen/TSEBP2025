import { useState, useEffect, useRef } from "react";
import { Mic, Square, Circle, ChevronDown, X, Volume2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const soundGroups = [
  { header: "Background Noise", items: ["Wind", "Rain", "Traffic", "Crowd Chatter", "Construction", "AC / HVAC", "Fan Noise", "Street Noise"] },
  { header: "Voice & Speech", items: ["Background Voices", "Echo / Reverb", "Breathing", "Mouth Clicks", "Plosives", "Sibilance", "Mumbling"] },
  { header: "Electronic & Device", items: ["Keyboard Typing", "Mouse Clicks", "Computer Fan", "Electrical Hum 60Hz", "Electrical Hum 50Hz", "Microphone Buzz", "Notification Sounds", "TV / Radio Bleed"] },
  { header: "Music & Tones", items: ["Background Music", "Low Frequency Bass", "High Frequency Hiss", "White Noise", "Pink Noise", "Static"] },
  { header: "Environment", items: ["Office Noise", "Cafe Noise", "Airport Noise", "Restaurant Noise", "Nature Sounds", "Animal Sounds", "Church / Hall Reverb"] },
  { header: "Recording Artifacts", items: ["Clipping", "Distortion", "Popping", "Crackling", "Room Tone", "Tape Hiss"] },
];

const CompactWaveform = ({ isRecording }: { isRecording: boolean }) => {
  const [bars, setBars] = useState<number[]>(Array(40).fill(0.12));
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (isRecording) {
      intervalRef.current = setInterval(() => {
        setBars(prev => prev.map(() => 0.08 + Math.random() * 0.92));
      }, 80);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
      setBars(prev => prev.map(() => 0.06 + Math.random() * 0.1));
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [isRecording]);

  return (
    <div className="relative h-20 rounded-xl bg-muted/50 border border-border overflow-hidden flex items-center justify-center px-2 gap-[2px]">
      {bars.map((h, i) => (
        <motion.div
          key={i}
          className="rounded-full flex-1 min-w-[2px]"
          style={{
            background: isRecording
              ? "linear-gradient(180deg, hsl(var(--primary)), hsl(var(--accent)))"
              : "hsl(var(--muted-foreground) / 0.25)",
          }}
          animate={{ height: `${h * 100}%` }}
          transition={{ duration: 0.08, ease: "easeOut" }}
        />
      ))}
    </div>
  );
};

const CompactSoundsDropdown = ({ selected, onChange }: { selected: string[]; onChange: (s: string[]) => void }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const toggle = (item: string) => {
    onChange(selected.includes(item) ? selected.filter(s => s !== item) : [...selected, item]);
  };

  const label = selected.length === 0
    ? "Select sounds to remove..."
    : selected.length === 1
      ? selected[0]
      : `${selected.length} sounds will be filtered`;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`w-full flex items-center justify-between px-3 py-2 rounded-lg border text-xs font-display transition-all ${
          open
            ? "border-primary bg-primary/5 text-foreground"
            : "border-border bg-card text-muted-foreground hover:border-primary/40"
        }`}
      >
        <span className={`truncate ${selected.length > 0 ? "text-foreground" : ""}`}>{label}</span>
        <ChevronDown className={`w-3.5 h-3.5 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute z-50 mt-1.5 w-full max-h-56 overflow-y-auto rounded-lg border border-border bg-card shadow-lg"
          >
            {soundGroups.map(group => (
              <div key={group.header}>
                <div className="px-2.5 py-1.5 text-[9px] font-mono uppercase tracking-wider text-muted-foreground bg-muted/40 sticky top-0">
                  {group.header}
                </div>
                {group.items.map(item => (
                  <button
                    key={item}
                    onClick={() => toggle(item)}
                    className={`w-full text-left px-3 py-1.5 text-xs font-display transition-colors ${
                      selected.includes(item)
                        ? "bg-primary/10 text-primary"
                        : "text-foreground/80 hover:bg-muted/50"
                    }`}
                  >
                    {item}
                  </button>
                ))}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {selected.map(item => (
            <span
              key={item}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 border border-primary/30 text-[10px] font-display text-primary"
            >
              {item}
              <button onClick={() => toggle(item)} className="hover:text-destructive transition-colors">
                <X className="w-2.5 h-2.5" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

const RealTimeMode = ({ compact = false }: { compact?: boolean }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [selectedSounds, setSelectedSounds] = useState<string[]>([]);
  const status = isRecording ? "Recording" : "Idle";

  return (
    <div className={compact ? "p-3 space-y-3" : "p-5 space-y-4"}>
      <div className="rounded-xl bg-card border border-border p-3 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-xs font-semibold text-foreground font-display">Live Audio</h2>
            <AnimatePresence>
              {isRecording && (
                <motion.div
                  initial={{ opacity: 0, scale: 0 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0 }}
                  className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-destructive/15 border border-destructive/30"
                >
                  <Circle className="w-1.5 h-1.5 fill-destructive text-destructive animate-pulse" />
                  <span className="text-[9px] font-mono text-destructive font-medium tracking-wider">REC</span>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded-full ${isRecording ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground"}`}>
            {status}
          </span>
        </div>

        <CompactWaveform isRecording={isRecording} />

        <motion.button
          whileTap={{ scale: 0.97 }}
          onClick={() => setIsRecording(!isRecording)}
          className={`w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-display font-semibold text-xs transition-all ${
            isRecording
              ? "bg-destructive/15 text-destructive border border-destructive/40"
              : "bg-primary text-primary-foreground border border-primary hover:bg-primary/90"
          }`}
        >
          {isRecording ? (
            <><Square className="w-3.5 h-3.5 fill-current" />Stop Processing</>
          ) : (
            <><Mic className="w-3.5 h-3.5" />Start Processing</>
          )}
        </motion.button>
      </div>

      <div className="rounded-xl bg-card border border-border p-3">
        <div className="flex items-center gap-1.5 mb-2">
          <Volume2 className="w-3.5 h-3.5 text-primary" />
          <h2 className="text-xs font-semibold text-foreground font-display">Sounds to Remove</h2>
        </div>
        <CompactSoundsDropdown selected={selectedSounds} onChange={setSelectedSounds} />
      </div>
    </div>
  );
};

export default RealTimeMode;
