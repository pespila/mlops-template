import path from "node:path";
import react from "@vitejs/plugin-react";
// Import defineConfig from vitest/config so the `test` block below is
// type-checked (plain vite's UserConfig does not know about the `test` key).
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 80,
    host: true,
    proxy: {
      "/api": "http://api:8000",
      "/sse": "http://api:8000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
  },
});
