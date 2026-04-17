import { useNavigate, useLocation } from "react-router-dom";
import { Settings, Sun, Moon, User, AudioWaveform, LayoutDashboard, Minimize2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/hooks/useTheme";
import { useDisplayMode } from "@/contexts/DisplayModeContext";

const HeaderBar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const { isDark, toggle } = useTheme();
  const { setMode } = useDisplayMode();

  const initials = user?.name
    ? user.name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2)
    : "?";

  const navItems = [
    { icon: LayoutDashboard, label: "Dashboard", path: "/dashboard" },
    { icon: Settings, label: "Settings", path: "/settings" },
    { icon: User, label: "Profile", path: "/profile" },
  ];

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="flex items-center justify-between px-6 py-3 border-b border-border/50 bg-card/80 backdrop-blur-xl transition-colors duration-300"
    >
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-primary/20 flex items-center justify-center glow-purple">
          <AudioWaveform className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h1 className="text-base font-semibold text-foreground tracking-tight font-display">
            SNC
          </h1>
          <p className="text-[10px] text-muted-foreground font-mono tracking-widest uppercase">
            Semantic Noise Cancellation
          </p>
        </div>
      </div>

      <div className="flex items-center gap-1">
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.95 }}
          onClick={toggle}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors"
          title="Toggle theme"
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={isDark ? "moon" : "sun"}
              initial={{ y: -10, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 10, opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="flex items-center justify-center"
            >
              {isDark ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
            </motion.span>
          </AnimatePresence>
        </motion.button>
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => setMode("flyout")}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors"
          title="Minimize to flyout"
        >
          <Minimize2 className="w-4 h-4" />
        </motion.button>
        <div className="w-px h-5 bg-border/50 mx-1" />
        {navItems.map(({ icon: Icon, label, path }) => (
          <motion.button
            key={label}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => navigate(path)}
            className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
              location.pathname === path
                ? "text-primary bg-primary/10"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"
            }`}
            title={label}
          >
            <Icon className="w-4 h-4" />
          </motion.button>
        ))}
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => navigate("/profile")}
          className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-accent ml-2 flex items-center justify-center text-xs font-bold text-primary-foreground"
        >
          {initials}
        </motion.button>
      </div>
    </motion.header>
  );
};

export default HeaderBar;
