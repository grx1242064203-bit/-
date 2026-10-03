import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Tauri 2 桌面端 Vite 配置：固定 1420 端口，暴露 TAURI_ 前缀环境变量。
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
  },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: "es2021",
    minify: "esbuild",
    sourcemap: false,
  },
});
