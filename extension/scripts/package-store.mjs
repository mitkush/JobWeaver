// Zips dist/ for a Chrome Web Store upload after checking it is a store build.
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const dist = join(root, "dist");
const manifest = JSON.parse(readFileSync(join(dist, "manifest.json"), "utf8"));
if (manifest.key) throw new Error("dist/ is an unpacked build. Run npm run build:store.");
if (!manifest.host_permissions.every((p) => p.startsWith("https://"))) throw new Error("A store build must use an HTTPS server");

const out = join(root, "release");
mkdirSync(out, { recursive: true });
const zip = join(out, `jobweaver-extension-${manifest.version}.zip`);
rmSync(zip, { force: true });
execFileSync("zip", ["-qrX", zip, "."], { cwd: dist, stdio: "inherit" });
console.log(`Store package: ${zip}`);
