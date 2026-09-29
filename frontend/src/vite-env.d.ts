/// <reference types="vite/client" />

// Values come from the single project-wide `.env` at the repository root.
interface ImportMetaEnv {
  /** Absolute API base when the API is on another origin; empty = same origin. */
  readonly VITE_API_URL?: string;
  /** Injected from API_PREFIX by vite.config.ts. */
  readonly VITE_API_PREFIX?: string;
  readonly VITE_API_TIMEOUT_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
