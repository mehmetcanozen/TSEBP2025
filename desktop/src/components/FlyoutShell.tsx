import { ReactNode } from "react";
import { Maximize2, X, AudioWaveform } from "lucide-react";
import { motion } from "framer-motion";
import { useDisplayMode } from "@/contexts/DisplayModeContext";

interface FlyoutShellProps {
  children: ReactNode;
}

const FlyoutShell = ({ children }: FlyoutShellProps) => {
  const { setMode } = useDisplayMode();

  const handleClose = () => {
    // Best-effort close: try window.close, otherwise hide
    window.close();
  };

  return (
    <div className="fixed inset-0 bg-transparent pointer-events-none">
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 28 }}
        className="pointer-events-auto fixed bottom-4 right-4 w-[360px] h-[480px] rounded-2xl bg-card border border-border shadow-2xl flex flex-col overflow-hidden"
      >
        {/* Minimal header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-border/60 bg-card/80 backdrop-blur-xl shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-6 h-6 rounded-md bg-primary/20 flex items-center justify-center shrink-0">
              <AudioWaveform className="w-3.5 h-3.5 text-primary" />
            </div>
            <span className="text-xs font-semibold font-display text-foreground truncate">
              SNC
            </span>
          </div>
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => setMode("fullscreen")}
              className="w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors"
              title="Expand to fullscreen"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleClose}
              className="w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
              title="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-y-auto">{children}</div>
      </motion.div>
    </div>
  );
};

export default FlyoutShell;
