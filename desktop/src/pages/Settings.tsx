import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, LogOut } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import HeaderBar from "@/components/HeaderBar";

const ToggleRow = ({ label, active, onToggle }: { label: string; active: boolean; onToggle: () => void }) => (
  <div className="flex items-center justify-between py-3">
    <span className="text-sm font-display text-foreground/90">{label}</span>
    <motion.button
      whileTap={{ scale: 0.9 }}
      onClick={onToggle}
      className={`relative w-11 h-6 rounded-full transition-colors ${active ? "bg-primary/30" : "bg-surface-3"}`}
    >
      <motion.div
        className={`absolute top-0.5 w-5 h-5 rounded-full ${active ? "bg-primary glow-purple" : "bg-muted-foreground/50"}`}
        animate={{ left: active ? "22px" : "2px" }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
      />
    </motion.button>
  </div>
);

const SliderRow = ({ label, value, onChange, min = 0, max = 100, unit = "%" }: {
  label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; unit?: string;
}) => (
  <div className="py-3">
    <div className="flex items-center justify-between mb-2">
      <span className="text-sm font-display text-foreground/90">{label}</span>
      <span className="text-xs font-mono text-primary">{value}{unit}</span>
    </div>
    <input
      type="range"
      min={min}
      max={max}
      value={value}
      onChange={e => onChange(Number(e.target.value))}
      className="w-full h-1.5 rounded-full appearance-none bg-surface-3 cursor-pointer
        [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
        [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:cursor-pointer
        [&::-webkit-slider-thumb]:shadow-[0_0_8px_hsl(262_83%_68%/0.4)]"
    />
  </div>
);

const Settings = () => {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [sensitivity, setSensitivity] = useState(65);
  const [noiseReduction, setNoiseReduction] = useState(75);
  const [filterSpeech, setFilterSpeech] = useState(true);
  const [filterMusic, setFilterMusic] = useState(true);
  const [filterAmbient, setFilterAmbient] = useState(false);
  const [filterTyping, setFilterTyping] = useState(true);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <HeaderBar />
      <main className="flex-1 overflow-y-auto flex items-start justify-center p-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel w-full max-w-lg p-8"
        >
          <button
            onClick={() => navigate("/dashboard")}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-6"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="font-display">Back</span>
          </button>

          <h2 className="text-lg font-bold text-foreground font-display mb-6">Settings</h2>

          {/* Audio */}
          <div className="mb-6">
            <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-2">Audio Processing</p>
            <SliderRow label="Audio Sensitivity" value={sensitivity} onChange={setSensitivity} />
            <SliderRow label="Noise Reduction Strength" value={noiseReduction} onChange={setNoiseReduction} />
          </div>

          {/* Category Filters */}
          <div className="mb-6 border-t border-border/30 pt-4">
            <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-2">Category Filters</p>
            <ToggleRow label="Speech" active={filterSpeech} onToggle={() => setFilterSpeech(!filterSpeech)} />
            <ToggleRow label="Music" active={filterMusic} onToggle={() => setFilterMusic(!filterMusic)} />
            <ToggleRow label="Ambient Noise" active={filterAmbient} onToggle={() => setFilterAmbient(!filterAmbient)} />
            <ToggleRow label="Typing" active={filterTyping} onToggle={() => setFilterTyping(!filterTyping)} />
          </div>

          {/* Logout */}
          <div className="border-t border-border/30 pt-4">
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleLogout}
              className="w-full h-11 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive font-semibold text-sm font-display hover:bg-destructive/20 transition-colors flex items-center justify-center gap-2"
            >
              <LogOut className="w-4 h-4" />
              Logout
            </motion.button>
          </div>
        </motion.div>
      </main>
    </div>
  );
};

export default Settings;
