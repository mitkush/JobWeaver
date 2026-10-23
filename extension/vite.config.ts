import { resolve } from "node:path";

import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

import { buildManifest, DEFAULT_ORIGIN } from "./manifest";

// The JobWeaver server this build talks to, e.g. JOBWEAVER_ORIGIN=http://localhost:5173.
const origin = new URL(process.env.JOBWEAVER_ORIGIN ?? DEFAULT_ORIGIN).origin;

function manifest(): Plugin {
  return {
    name: "jobweaver-manifest",
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: "manifest.json",
        source: JSON.stringify(buildManifest(origin, process.env.npm_package_version ?? "0.1.0"), null, 2),
      });
    },
  };
}

export default defineConfig({
  define: { __JOBWEAVER_ORIGIN__: JSON.stringify(origin) },
  plugins: [manifest()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "chrome116",
    modulePreload: false,
    rollupOptions: {
      input: { popup: resolve(import.meta.dirname, "popup.html"), background: resolve(import.meta.dirname, "src/background.ts") },
      output: { entryFileNames: "[name].js", chunkFileNames: "chunks/[name]-[hash].js", assetFileNames: "assets/[name]-[hash][extname]" },
    },
  },
  test: { environment: "node" },
});
