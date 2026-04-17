import { useState, useEffect, useRef } from "react";
import {
  Play, Pause, Mic, Square, Circle, Upload, FileAudio, X,
  Sparkles, Wand2, ChevronDown,
  Volume2, Download,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import HeaderBar from "@/components/HeaderBar";


/* ───── Waveform Visualizer ───── */
const WaveformDisplay = ({ isRecording }: { isRecording: boolean }) => {
  const [bars, setBars] = useState<number[]>(Array(80).fill(0.12));
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (isRecording) {
      intervalRef.current = setInterval(() => {
        setBars(prev => prev.map(() => 0.08 + Math.random() * 0.92));
      }, 70);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
      setBars(prev => prev.map(() => 0.06 + Math.random() * 0.1));
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [isRecording]);

  return (
    <div className="relative h-44 rounded-2xl bg-muted/50 border border-border overflow-hidden flex items-center justify-center px-3 gap-[2px]">
      {isRecording && (
        <div className="absolute inset-0 pointer-events-none opacity-20"
          style={{ background: "linear-gradient(90deg, hsl(207 90% 54% / 0.15), hsl(174 72% 50% / 0.2), hsl(207 90% 54% / 0.15))" }}
        />
      )}
      {bars.map((h, i) => (
        <motion.div
          key={i}
          className="rounded-full flex-1 min-w-[2px] max-w-[4px]"
          style={{
            background: isRecording
              ? "linear-gradient(180deg, hsl(207 90% 54%), hsl(174 72% 50%))"
              : "hsl(var(--muted-foreground) / 0.25)",
          }}
          animate={{ height: `${h * 100}%` }}
          transition={{ duration: 0.07, ease: "easeOut" }}
        />
      ))}
      <div className="absolute left-0 right-0 h-[1px] bg-border/30 top-1/2" />
    </div>
  );
};

/* ───── Sound Categories Data ───── */
const soundGroups = [
  { header: "Background Noise", items: ["Wind", "Rain", "Traffic", "Crowd Chatter", "Construction", "AC / HVAC", "Fan Noise", "Street Noise"] },
  { header: "Voice & Speech", items: ["Background Voices", "Echo / Reverb", "Breathing", "Mouth Clicks", "Plosives", "Sibilance", "Mumbling"] },
  { header: "Electronic & Device", items: ["Keyboard Typing", "Mouse Clicks", "Computer Fan", "Electrical Hum 60Hz", "Electrical Hum 50Hz", "Microphone Buzz", "Notification Sounds", "TV / Radio Bleed"] },
  { header: "Music & Tones", items: ["Background Music", "Low Frequency Bass", "High Frequency Hiss", "White Noise", "Pink Noise", "Static"] },
  { header: "Environment", items: ["Office Noise", "Cafe Noise", "Airport Noise", "Restaurant Noise", "Nature Sounds", "Animal Sounds", "Church / Hall Reverb"] },
  { header: "Recording Artifacts", items: ["Clipping", "Distortion", "Popping", "Crackling", "Room Tone", "Tape Hiss"] },
];

/* ───── Sounds Dropdown ───── */
const SoundsDropdown = ({ selected, onChange }: { selected: string[]; onChange: (s: string[]) => void }) => {
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
        className={`w-full flex items-center justify-between px-4 py-3 rounded-xl border text-sm font-display transition-all ${
          open
            ? "border-primary bg-primary/5 text-foreground"
            : "border-border bg-card text-muted-foreground hover:border-primary/40"
        }`}
      >
        <span className={selected.length > 0 ? "text-foreground" : ""}>{label}</span>
        <ChevronDown className={`w-4 h-4 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute z-50 mt-2 w-full max-h-72 overflow-y-auto rounded-xl border border-border bg-card shadow-lg"
          >
            {soundGroups.map(group => (
              <div key={group.header}>
                <div className="px-3 py-2 text-[10px] font-mono uppercase tracking-wider text-muted-foreground bg-muted/40 sticky top-0">
                  {group.header}
                </div>
                {group.items.map(item => (
                  <button
                    key={item}
                    onClick={() => toggle(item)}
                    className={`w-full text-left px-4 py-2 text-sm font-display transition-colors ${
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

      {/* Chips */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {selected.map(item => (
            <motion.span
              key={item}
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary/10 border border-primary/30 text-xs font-display text-primary"
            >
              {item}
              <button onClick={() => toggle(item)} className="hover:text-destructive transition-colors">
                <X className="w-3 h-3" />
              </button>
            </motion.span>
          ))}
        </div>
      )}
    </div>
  );
};

/* ───── Mini Player ───── */
const MiniPlayer = ({ label, color, gradient }: { label: string; color: string; gradient: string }) => {
  const [playing, setPlaying] = useState(false);
  const bars = Array(50).fill(0).map(() => 0.1 + Math.random() * 0.9);

  return (
    <div className="flex-1 p-4 rounded-2xl bg-card border border-border">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-2 h-2 rounded-full" style={{ background: color }} />
        <span className="text-xs font-mono text-muted-foreground uppercase tracking-wider">{label}</span>
      </div>
      <div className="flex items-center gap-3">
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          onClick={() => setPlaying(!playing)}
          className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 border transition-colors"
          style={{
            background: playing ? `${color}18` : "transparent",
            borderColor: `${color}50`,
            color,
          }}
        >
          {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
        </motion.button>
        <div className="flex items-center h-12 gap-[1.5px] flex-1 overflow-hidden">
          {bars.map((h, i) => (
            <div
              key={i}
              className="rounded-full flex-1 min-w-[1.5px]"
              style={{
                height: `${h * 100}%`,
                background: gradient,
                opacity: playing ? 0.8 : 0.3,
                transition: "opacity 0.3s",
              }}
            />
          ))}
        </div>
        <span className="text-[10px] font-mono text-muted-foreground shrink-0">0:32</span>
      </div>
    </div>
  );
};

/* ───── File Import Section ───── */
const FileImport = () => {
  const [dragOver, setDragOver] = useState(false);
  const [files, setFiles] = useState<string[]>([]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    setFiles(prev => [...prev, "audio_sample.wav"]);
  };

  return (
    <div className="p-4 rounded-2xl bg-card border border-border">
      <div className="flex items-center gap-2 mb-3">
        <FileAudio className="w-4 h-4 text-primary" />
        <h3 className="text-sm font-semibold font-display text-foreground">Import Audio</h3>
      </div>
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => setFiles(prev => [...prev, `recording_${prev.length + 1}.wav`])}
        className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-all ${
          dragOver
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/40 hover:bg-muted/30"
        }`}
      >
        <Upload className="w-5 h-5 mx-auto mb-2 text-muted-foreground" />
        <p className="text-xs text-muted-foreground font-display">
          Drop audio files or <span className="text-primary font-medium">browse</span>
        </p>
        <p className="text-[10px] text-muted-foreground/60 mt-1 font-mono">.wav .mp3 .flac .ogg</p>
      </div>
      <AnimatePresence>
        {files.map((f, i) => (
          <motion.div
            key={`${f}-${i}`}
            initial={{ x: -8, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center justify-between p-2 mt-2 rounded-lg bg-muted/50 border border-border"
          >
            <div className="flex items-center gap-2">
              <FileAudio className="w-3.5 h-3.5 text-primary" />
              <span className="text-xs font-mono text-foreground/80">{f}</span>
            </div>
            <button
              onClick={e => { e.stopPropagation(); setFiles(prev => prev.filter((_, j) => j !== i)); }}
              className="text-muted-foreground hover:text-destructive transition-colors"
            >
              <X className="w-3 h-3" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
};

/* ───── Noise Removal ───── */
const NoiseRemoval = () => {
  const [active, setActive] = useState(false);
  const makeBars = (variant: "before" | "after") =>
    Array(40).fill(0).map(() => variant === "before" ? 0.15 + Math.random() * 0.85 : 0.1 + Math.random() * 0.45);

  return (
    <div className="p-4 rounded-2xl bg-card border border-border">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Wand2 className="w-4 h-4 text-accent" />
          <h3 className="text-sm font-semibold font-display text-foreground">Noise Removal</h3>
        </div>
        <motion.button
          whileTap={{ scale: 0.9 }}
          onClick={() => setActive(!active)}
          className={`relative w-11 h-6 rounded-full transition-colors ${active ? "bg-accent/30" : "bg-muted"}`}
        >
          <motion.div
            className={`absolute top-0.5 w-5 h-5 rounded-full shadow ${active ? "bg-accent" : "bg-muted-foreground/50"}`}
            animate={{ left: active ? "22px" : "2px" }}
            transition={{ type: "spring", stiffness: 500, damping: 30 }}
          />
        </motion.button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {(["before", "after"] as const).map(variant => (
          <div key={variant} className="rounded-xl bg-muted/40 border border-border p-3">
            <div className="flex items-center gap-1.5 mb-2">
              <div className={`w-1.5 h-1.5 rounded-full ${variant === "before" ? "bg-neon-orange" : "bg-accent"}`} />
              <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">{variant}</span>
              {variant === "after" && active && <Sparkles className="w-3 h-3 text-accent ml-auto animate-float" />}
            </div>
            <div className="flex items-center h-12 gap-[2px] px-1">
              {makeBars(variant).map((h, i) => (
                <div key={i} className="rounded-full flex-1 min-w-[2px]"
                  style={{
                    height: `${h * 100}%`,
                    background: variant === "before"
                      ? `hsl(var(--neon-orange) / ${0.4 + h * 0.6})`
                      : `hsl(var(--accent) / ${0.4 + h * 0.6})`,
                  }}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        className="w-full mt-3 py-2.5 rounded-xl bg-accent/10 border border-accent/30 text-accent text-xs font-semibold font-display flex items-center justify-center gap-2 hover:bg-accent/20 transition-all"
      >
        <Sparkles className="w-3.5 h-3.5" />
        Clean Audio
      </motion.button>
    </div>
  );
};

/* ═══════════ DASHBOARD ═══════════ */
const Dashboard = () => {
  
  const [isRecording, setIsRecording] = useState(false);
  const [selectedSounds, setSelectedSounds] = useState<string[]>([]);
  const status = isRecording ? "Recording" : "Idle";

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background transition-colors duration-300">
      <HeaderBar />




      <main className="flex-1 overflow-y-auto p-5">
        <div className="max-w-7xl mx-auto space-y-5">

          {/* ─── Top: Waveform + Categories ─── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Left: Waveform & Controls */}
            <div className="lg:col-span-2 space-y-4">
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
                className="p-5 rounded-2xl bg-card border border-border shadow-sm">
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
                    <span className={`px-2 py-0.5 rounded-full ${isRecording ? "bg-destructive/10 text-destructive" : "bg-muted"}`}>
                      {status}
                    </span>
                    <span>48kHz · 16-bit</span>
                  </div>
                </div>

                <WaveformDisplay isRecording={isRecording} />

                <div className="flex items-center justify-center mt-4">
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => setIsRecording(!isRecording)}
                    className={`flex items-center gap-2.5 px-8 py-3 rounded-2xl font-display font-semibold text-sm transition-all shadow-sm ${
                      isRecording
                        ? "bg-destructive/15 text-destructive border border-destructive/40"
                        : "bg-primary text-primary-foreground border border-primary hover:bg-primary/90"
                    }`}
                  >
                    {isRecording ? (
                      <><Square className="w-4 h-4 fill-current" />Stop Processing</>
                    ) : (
                      <><Mic className="w-4 h-4" />Start Processing</>
                    )}
                  </motion.button>
                </div>
              </motion.div>

              {/* File Import */}
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
                <FileImport />
              </motion.div>
            </div>

            {/* Right: Sounds to Remove */}
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
              className="space-y-4">
              <div className="p-5 rounded-2xl bg-card border border-border shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <Volume2 className="w-4 h-4 text-primary" />
                  <h2 className="text-sm font-semibold text-foreground font-display">Sounds to Remove</h2>
                </div>
                <SoundsDropdown selected={selectedSounds} onChange={setSelectedSounds} />
              </div>

              {/* Noise Removal */}
              <NoiseRemoval />
            </motion.div>
          </div>

          {/* ─── Bottom: Audio Comparison ─── */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
            className="p-5 rounded-2xl bg-card border border-border shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <Wand2 className="w-4 h-4 text-accent" />
              <h2 className="text-sm font-semibold text-foreground font-display">Audio Comparison</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <MiniPlayer
                label="Original"
                color="hsl(var(--neon-orange))"
                gradient="linear-gradient(180deg, hsl(var(--neon-orange)), hsl(var(--neon-pink)))"
              />
              <div className="relative">
                <MiniPlayer
                  label="Cleaned"
                  color="hsl(var(--accent))"
                  gradient="linear-gradient(180deg, hsl(var(--accent)), hsl(var(--primary)))"
                />
                <div className="absolute top-2 right-3">
                  <Sparkles className="w-3.5 h-3.5 text-accent animate-float" />
                </div>
              </div>
            </div>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="mt-4 px-6 py-2.5 rounded-xl bg-primary/10 border border-primary/30 text-primary text-xs font-semibold font-display flex items-center gap-2 hover:bg-primary/20 transition-all mx-auto"
            >
              <Download className="w-3.5 h-3.5" />
              Export Clean Audio
            </motion.button>
          </motion.div>
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
