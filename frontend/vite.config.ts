import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development the dev server proxies /api to the FastAPI backend. In
// production the backend serves the built assets from frontend/dist directly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
