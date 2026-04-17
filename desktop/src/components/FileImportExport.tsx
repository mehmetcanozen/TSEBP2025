import { useState } from "react";
import { Upload, Download, FileAudio, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const FileImportExport = () => {
  const [dragOver, setDragOver] = useState(false);
  const [files, setFiles] = useState<string[]>([]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    setFiles(prev => [...prev, "audio_sample.wav"]);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.4 }}
      className="glass-panel p-5"
    >
      <div className="flex items-center gap-2 mb-4">
        <FileAudio className="w-4 h-4 text-neon-blue" />
        <h2 className="text-sm font-semibold text-foreground font-display">Files</h2>
      </div>

      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => setFiles(prev => [...prev, `recording_${prev.length + 1}.wav`])}
        className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
          dragOver
            ? "border-primary bg-primary/5"
            : "border-border/50 hover:border-primary/40 hover:bg-surface-2/30"
        }`}
      >
        <Upload className="w-6 h-6 mx-auto mb-2 text-muted-foreground" />
        <p className="text-xs text-muted-foreground font-display">
          Drop audio files here or <span className="text-primary">browse</span>
        </p>
        <p className="text-[10px] text-muted-foreground/60 mt-1 font-mono">.wav .mp3 .flac .ogg</p>
      </div>

      <AnimatePresence>
        {files.length > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            className="mt-3 space-y-1.5"
          >
            {files.map((f, i) => (
              <motion.div
                key={`${f}-${i}`}
                initial={{ x: -10, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                className="flex items-center justify-between p-2 rounded-lg bg-surface-2/50 border border-border/20"
              >
                <div className="flex items-center gap-2">
                  <FileAudio className="w-3.5 h-3.5 text-neon-blue" />
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
          </motion.div>
        )}
      </AnimatePresence>

      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        className="w-full mt-3 py-2 rounded-lg bg-gradient-to-r from-neon-blue/15 to-primary/15 border border-neon-blue/30 text-neon-blue text-xs font-medium font-display flex items-center justify-center gap-2 hover:from-neon-blue/25 hover:to-primary/25 transition-all"
      >
        <Download className="w-3.5 h-3.5" />
        Export Clean Audio
      </motion.button>
    </motion.div>
  );
};

export default FileImportExport;
