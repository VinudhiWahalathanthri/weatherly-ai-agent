import path from "path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/predict": "http://localhost:8000",
      "/agent":   "http://localhost:8000",
      "/health":  "http://localhost:8000",
      "/weather": "http://localhost:8000",
    },
  },
});
