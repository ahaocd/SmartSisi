import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "node:path";

const BUILD_ID = new Date().toISOString();

export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  base: mode === "development" ? "/" : "/static/app/",
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID)
  },
  build: {
    outDir: path.resolve(__dirname, "../static/app"),
    emptyOutDir: true,
    sourcemap: true
  }
}));
