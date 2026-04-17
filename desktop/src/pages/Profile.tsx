import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Camera, Save } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import HeaderBar from "@/components/HeaderBar";

const Profile = () => {
  const { user, updateProfile } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState(user?.name || "");
  const [bio, setBio] = useState(user?.bio || "");
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    updateProfile({ name, bio });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const initials = name ? name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2) : "?";

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

          <div className="flex flex-col items-center mb-8">
            <div className="relative mb-4">
              <div className="w-24 h-24 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center text-2xl font-bold text-primary-foreground font-display">
                {initials}
              </div>
              <motion.button
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                className="absolute -bottom-1 -right-1 w-8 h-8 rounded-full bg-card border border-border/50 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
              >
                <Camera className="w-3.5 h-3.5" />
              </motion.button>
            </div>
            <p className="text-xs text-muted-foreground font-mono">{user?.email}</p>
          </div>

          <div className="space-y-4">
            <div>
              <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1.5 block">Name</label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                className="w-full h-11 rounded-xl bg-surface-2/80 border border-border/40 px-4 text-sm text-foreground outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/30 transition-all font-display"
              />
            </div>
            <div>
              <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1.5 block">Bio</label>
              <textarea
                value={bio}
                onChange={e => setBio(e.target.value)}
                rows={3}
                placeholder="Tell us about yourself..."
                className="w-full rounded-xl bg-surface-2/80 border border-border/40 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground/50 outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/30 transition-all font-display resize-none"
              />
            </div>

            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleSave}
              className="w-full h-11 rounded-xl bg-primary text-primary-foreground font-semibold text-sm font-display glow-purple hover:bg-primary/90 transition-colors flex items-center justify-center gap-2"
            >
              <Save className="w-4 h-4" />
              {saved ? "Saved!" : "Save Profile"}
            </motion.button>
          </div>
        </motion.div>
      </main>
    </div>
  );
};

export default Profile;
