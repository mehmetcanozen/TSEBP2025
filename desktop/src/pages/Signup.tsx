import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { AudioWaveform, UserPlus, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const Signup = () => {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const { signup } = useAuth();

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !email || !password || password.length < 8 || isSubmitting) {
      return;
    }
    setError("");
    setIsSubmitting(true);
    try {
      await signup(name, email, password);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{
      background: "linear-gradient(135deg, hsl(228 18% 8%) 0%, hsl(174 30% 10%) 40%, hsl(228 18% 10%) 100%)",
    }}>
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/3 right-1/4 w-96 h-96 rounded-full opacity-10" style={{ background: "radial-gradient(circle, hsl(174 72% 56%), transparent 70%)" }} />
        <div className="absolute bottom-1/3 left-1/4 w-80 h-80 rounded-full opacity-8" style={{ background: "radial-gradient(circle, hsl(262 83% 68%), transparent 70%)" }} />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="glass-panel w-full max-w-md p-8 relative z-10"
      >
        <div className="flex flex-col items-center mb-8">
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
            className="w-16 h-16 rounded-2xl bg-accent/20 flex items-center justify-center glow-teal mb-4"
          >
            <AudioWaveform className="w-8 h-8 text-accent" />
          </motion.div>
          <h1 className="text-2xl font-bold text-foreground font-display">Join SNC</h1>
          <p className="text-sm text-muted-foreground mt-1">Create your audio workspace</p>
        </div>

        <form onSubmit={handleSignup} className="space-y-4">
          <div>
            <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1.5 block">Full Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="John Doe"
              className="w-full h-11 rounded-xl bg-surface-2/80 border border-border/40 px-4 text-sm text-foreground placeholder:text-muted-foreground/50 outline-none focus:border-accent/60 focus:ring-1 focus:ring-accent/30 transition-all font-display"
            />
          </div>
          <div>
            <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1.5 block">Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full h-11 rounded-xl bg-surface-2/80 border border-border/40 px-4 text-sm text-foreground placeholder:text-muted-foreground/50 outline-none focus:border-accent/60 focus:ring-1 focus:ring-accent/30 transition-all font-display"
            />
          </div>
          <div>
            <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1.5 block">Password</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Min 8 characters"
                className="w-full h-11 rounded-xl bg-surface-2/80 border border-border/40 px-4 pr-10 text-sm text-foreground placeholder:text-muted-foreground/50 outline-none focus:border-accent/60 focus:ring-1 focus:ring-accent/30 transition-all font-display"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {password.length > 0 && password.length < 8 && (
              <p className="text-[10px] text-destructive mt-1 font-mono">Password must be at least 8 characters</p>
            )}
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
            className="w-full h-11 rounded-xl bg-accent text-accent-foreground font-semibold text-sm font-display glow-teal hover:bg-accent/90 transition-colors flex items-center justify-center gap-2"
          >
            <UserPlus className="w-4 h-4" />
            {isSubmitting ? "Creating..." : "Sign Up"}
          </motion.button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-sm text-muted-foreground">
            Already have an account?{" "}
            <motion.button
              whileHover={{ scale: 1.05 }}
              onClick={() => navigate("/login")}
              className="text-accent hover:text-accent/80 font-medium transition-colors"
            >
              Login
            </motion.button>
          </p>
        </div>
      </motion.div>
    </div>
  );
};

export default Signup;
