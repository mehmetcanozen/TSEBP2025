import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Mic, AudioWaveform, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const Login = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password || isSubmitting) {
      return;
    }
    setError("");
    setIsSubmitting(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{
      background: "linear-gradient(135deg, hsl(228 18% 8%) 0%, hsl(262 30% 12%) 40%, hsl(228 18% 10%) 100%)",
    }}>
      {/* Ambient glow */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full opacity-10" style={{ background: "radial-gradient(circle, hsl(262 83% 68%), transparent 70%)" }} />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 rounded-full opacity-8" style={{ background: "radial-gradient(circle, hsl(174 72% 56%), transparent 70%)" }} />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="glass-panel w-full max-w-md p-8 relative z-10"
      >
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
            className="w-16 h-16 rounded-2xl bg-primary/20 flex items-center justify-center glow-purple mb-4"
          >
            <AudioWaveform className="w-8 h-8 text-primary" />
          </motion.div>
          <h1 className="text-2xl font-bold text-foreground font-display">SNC</h1>
          <p className="text-sm text-muted-foreground mt-1">Semantic Noise Cancellation</p>
        </div>

        {/* Waveform decoration */}
        <div className="flex items-center justify-center gap-[3px] h-8 mb-6 opacity-40">
          {Array(30).fill(0).map((_, i) => (
            <motion.div
              key={i}
              className="w-[2px] rounded-full bg-primary"
              animate={{ height: [4, 8 + Math.random() * 16, 4] }}
              transition={{ duration: 1.5 + Math.random(), repeat: Infinity, delay: i * 0.05 }}
            />
          ))}
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1.5 block">Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full h-11 rounded-xl bg-surface-2/80 border border-border/40 px-4 text-sm text-foreground placeholder:text-muted-foreground/50 outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/30 transition-all font-display"
            />
          </div>
          <div>
            <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1.5 block">Password</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full h-11 rounded-xl bg-surface-2/80 border border-border/40 px-4 pr-10 text-sm text-foreground placeholder:text-muted-foreground/50 outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/30 transition-all font-display"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {error && (
            <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </p>
          )}

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            type="submit"
            disabled={isSubmitting}
            className="w-full h-11 rounded-xl bg-primary text-primary-foreground font-semibold text-sm font-display glow-purple hover:bg-primary/90 transition-colors flex items-center justify-center gap-2"
          >
            <Mic className="w-4 h-4" />
            {isSubmitting ? "Logging in..." : "Login"}
          </motion.button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-sm text-muted-foreground">
            Don't have an account?{" "}
            <motion.button
              whileHover={{ scale: 1.05 }}
              onClick={() => navigate("/signup")}
              className="text-primary hover:text-primary/80 font-medium transition-colors"
            >
              Create Account
            </motion.button>
          </p>
        </div>
      </motion.div>
    </div>
  );
};

export default Login;
