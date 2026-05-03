import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/upload":   "http://localhost:8000",
      "/generate": "http://localhost:8000",
      "/health":   "http://localhost:8000",
    },
  },
});
