import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type DisplayMode = "flyout" | "fullscreen";

interface DisplayModeContextValue {
  mode: DisplayMode;
  setMode: (mode: DisplayMode) => void;
  toggleMode: () => void;
}

const DisplayModeContext = createContext<DisplayModeContextValue | undefined>(undefined);

const STORAGE_KEY = "displayMode";

const getInitialMode = (): DisplayMode => {
  if (typeof window === "undefined") return "fullscreen";
  const params = new URLSearchParams(window.location.search);
  const param = params.get("mode");
  if (param === "flyout" || param === "fullscreen") return param;
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "flyout" || stored === "fullscreen") return stored;
  return "fullscreen";
};

export const DisplayModeProvider = ({ children }: { children: ReactNode }) => {
  const [mode, setModeState] = useState<DisplayMode>(getInitialMode);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, mode);
    document.documentElement.dataset.displayMode = mode;
  }, [mode]);

  const setMode = (m: DisplayMode) => setModeState(m);
  const toggleMode = () => setModeState(m => (m === "flyout" ? "fullscreen" : "flyout"));

  return (
    <DisplayModeContext.Provider value={{ mode, setMode, toggleMode }}>
      {children}
    </DisplayModeContext.Provider>
  );
};

export const useDisplayMode = () => {
  const ctx = useContext(DisplayModeContext);
  if (!ctx) throw new Error("useDisplayMode must be used within DisplayModeProvider");
  return ctx;
};
