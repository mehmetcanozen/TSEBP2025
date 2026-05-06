/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_API_URL?: string;
  readonly VITE_DESKTOP_UI_SURFACE?: "user" | "dev" | "debug" | "clean";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  __TAURI_INTERNALS__?: unknown;
}
