import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api/* to FastAPI, so the browser only talks to one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": process.env.VITE_API_PROXY_TARGET || "http://localhost:8000",
    },
  },
});
