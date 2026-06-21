import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: "keep-stdin-open",
      configureServer() {
        // Prevent Vite from exiting when stdin closes (background/CI execution)
        process.stdin.resume();
      },
    },
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: "127.0.0.1",
    open: false,
    proxy: {
      "/api/auth": {
        target: "http://127.0.0.1:3005",
        changeOrigin: true,
      },
      "/v1": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
      "/auth": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
});
