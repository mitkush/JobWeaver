import { resolve } from "node:path";

import { defineConfig } from "vite";

// The content script is injected with chrome.scripting, which runs a classic script:
// one self-contained file, no imports. Built after the main build into the same dist.
export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: false,
    target: "chrome116",
    lib: { entry: resolve(import.meta.dirname, "src/content.ts"), formats: ["iife"], name: "jobweaverContent", fileName: () => "content.js" },
  },
});
