/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";

export type DesktopUiSurface = "user" | "dev";

interface DesktopUiSurfaceContextValue {
  surface: DesktopUiSurface;
}

const DesktopUiSurfaceContext = createContext<DesktopUiSurfaceContextValue | undefined>(undefined);

const normalizeSurface = (value: string | null | undefined): DesktopUiSurface | null => {
  if (value === "dev" || value === "debug") return "dev";
  if (value === "user" || value === "clean") return "user";
  return null;
};

const getInitialSurface = (): DesktopUiSurface => {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = normalizeSurface(params.get("ui"));
    if (fromQuery) return fromQuery;
  }

  return normalizeSurface(import.meta.env.VITE_DESKTOP_UI_SURFACE) ?? "user";
};

export const DesktopUiSurfaceProvider = ({ children }: { children: ReactNode }) => {
  const surface = useMemo(getInitialSurface, []);

  useEffect(() => {
    document.documentElement.dataset.desktopUiSurface = surface;
  }, [surface]);

  return (
    <DesktopUiSurfaceContext.Provider value={{ surface }}>
      {children}
    </DesktopUiSurfaceContext.Provider>
  );
};

export const useDesktopUiSurface = () => {
  const ctx = useContext(DesktopUiSurfaceContext);
  if (!ctx) {
    throw new Error("useDesktopUiSurface must be used within DesktopUiSurfaceProvider");
  }
  return ctx;
};
