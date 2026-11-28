import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Every request to /api/... is forwarded to the FastAPI server, so the browser
// never talks to another origin (no CORS problems in development).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
