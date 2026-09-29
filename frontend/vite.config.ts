/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// The whole project shares one `.env` at the repository root.
const ENV_DIR = '..';

export default defineConfig(({ mode }) => {
  // Read every variable (not just VITE_*) for dev-server wiring; only VITE_* reach the bundle.
  const env = loadEnv(mode, ENV_DIR, '');
  const apiPrefix = '/' + (env.API_PREFIX || '/api/v1').replace(/^\/+|\/+$/g, '');
  const backendPort = env.APP_PORT || '8000';

  return {
    envDir: ENV_DIR,
    plugins: [react()],
    define: {
      // Same prefix the backend mounts its routes on (API_PREFIX), resolved at build time.
      'import.meta.env.VITE_API_PREFIX': JSON.stringify(apiPrefix),
    },
    server: {
      port: Number(env.FRONTEND_PORT || 5173),
      strictPort: true,
      // Same-origin API in development, mirroring the nginx proxy used in Docker.
      proxy: {
        [apiPrefix]: { target: env.VITE_DEV_PROXY_TARGET || `http://localhost:${backendPort}`, changeOrigin: false },
      },
    },
    preview: {
      port: Number(env.FRONTEND_PORT || 5173),
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
    },
  };
});
