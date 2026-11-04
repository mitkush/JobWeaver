// Records a short, real-interface Feed clip with fictional API responses, as JPEG
// frames plus their timings, for an animated WebP in the README.
import { chromium } from "playwright";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { extname, join } from "node:path";

const DIST = process.env.DIST ?? new URL("../../../frontend/dist", import.meta.url).pathname;
const OUT = process.env.OUT ?? "feed-demo-frames";
rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

// Static server for the production build; the SPA falls back to index.html.
const types = { ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".woff": "font/woff", ".png": "image/png", ".webmanifest": "application/manifest+json" };
const server = createServer((req, res) => {
  const path = join(DIST, decodeURIComponent(new URL(req.url, "http://x").pathname));
  const file = existsSync(path) && extname(path) ? path : join(DIST, "index.html");
  res.setHeader("Content-Type", types[extname(file)] ?? "text/html");
  res.end(readFileSync(file));
});
await new Promise((r) => server.listen(5299, r));

const hours = (h) => new Date(Date.now() - h * 3_600_000).toISOString();
const src = (name, label) => ({ name, label, site: null });
const card = (o) => ({
  locations: [{ city: "Bengaluru", country: "IN", remote: false }], work_mode: "hybrid", experience_requirement: null,
  contact_email: null, apply_url: "https://example.com/apply", possible_duplicate: false, hidden: false, saved: false,
  viewed: false, expired: false, draft_id: null, application_status: null, company_applied: false, match: "title",
  matched_keywords: [{ keyword: "Ruby on Rails", where: "requirements", core: true }], ...o,
});
const titles = [
  card({ job_id: "j1", title: "Senior Backend Engineer", company: "Northstar Labs", posted_at: hours(3), work_mode: "remote", experience_requirement: "4+ years", sources: [src("greenhouse", "Greenhouse"), src("linkedin", "LinkedIn (Bright Data)")], skill_matches: ["Ruby on Rails", "PostgreSQL", "Redis", "Docker"], skill_gaps: ["Kubernetes", "Kafka"], saved: true, draft_id: "d1" }),
  card({ job_id: "j2", title: "Software Engineer, Platform", company: "Harbor Systems", locations: [{ city: "Pune", country: "IN", remote: false }], posted_at: hours(7), experience_requirement: "3+ years", sources: [src("lever", "Lever")], skill_matches: ["Ruby", "PostgreSQL", "AWS", "RSpec"], skill_gaps: ["Terraform"], matched_keywords: [{ keyword: "Ruby on Rails", where: "requirements", core: true }], viewed: true }),
  card({ job_id: "j3", title: "Backend Developer (Rails)", company: "Lumen Pay", posted_at: hours(11), experience_requirement: "2+ years", sources: [src("linkedin", "LinkedIn (Bright Data)"), src("jsearch", "JSearch")], skill_matches: ["Ruby on Rails", "Sidekiq", "PostgreSQL"], skill_gaps: ["GraphQL"] }),
  card({ job_id: "j4", title: "Full Stack Engineer", company: "Copperleaf", locations: [{ city: "Hyderabad", country: "IN", remote: false }], posted_at: hours(20), sources: [src("ashby", "Ashby")], skill_matches: ["Ruby on Rails", "React", "TypeScript"], skill_gaps: ["Elixir"] }),
];
const keywords = [
  card({ job_id: "k1", title: "Payments Engineer", company: "Tidewater", posted_at: hours(5), match: "keywords", sources: [src("greenhouse", "Greenhouse")], skill_matches: ["Ruby on Rails", "PostgreSQL", "Sidekiq"], skill_gaps: ["Go"], matched_keywords: [{ keyword: "Ruby on Rails", where: "requirements", core: true }, { keyword: "PostgreSQL", where: "requirements", core: false }] }),
  card({ job_id: "k2", title: "API Engineer", company: "Orbitline", work_mode: "remote", posted_at: hours(9), match: "keywords", sources: [src("lever", "Lever")], skill_matches: ["Ruby", "REST APIs", "Redis"], skill_gaps: ["Kafka"], matched_keywords: [{ keyword: "Ruby on Rails", where: "description", core: true }, { keyword: "Redis", where: "requirements", core: false }] }),
];
const saved = new Set(["j1"]);
const all = [...titles, ...keywords];
const sources = [src("linkedin", "LinkedIn (Bright Data)"), src("greenhouse", "Greenhouse"), src("lever", "Lever"), src("ashby", "Ashby")];
function feed(url) {
  const q = new URL(url).searchParams;
  const view = q.get("view"), match = q.get("match") ?? "title";
  const mark = (c) => ({ ...c, saved: saved.has(c.job_id) });
  const items = view === "saved" ? all.filter((c) => saved.has(c.job_id)) : match === "keywords" ? keywords : titles;
  return {
    items: items.map(mark), total: items.length, section: "link",
    counts: { with_email: 0, apply_link_only: items.length, title_matches: titles.length, keyword_matches: keywords.length, review_matches: 1, saved: saved.size },
    last_updated_at: hours(0.05), sources,
  };
}

const browser = await chromium.launch({ executablePath: process.env.BROWSER || undefined, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, colorScheme: "dark", deviceScaleFactor: 1 });
const page = await ctx.newPage();
const unmatched = new Set();
await page.route("**/api/**", async (route) => {
  const req = route.request(), path = new URL(req.url()).pathname;
  const json = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (path === "/api/me") return json({ id: "u1", email: "asha@example.com", name: "Asha Rao", picture_url: null, role: "user", follow_up_days: 7, country: "IN", gmail: { state: "not_connected", expires_at: null }, onboarding: { ai_notice_accepted: true, country_set: true, ai_region_blocked: false, documents_uploaded: true, fact_bank_reviewed: true, preferences_set: true, gmail_connected: false, next_step: "done" } });
  if (path === "/api/auth/csrf") return json({ csrf_token: "demo" });
  if (path === "/api/feed") {
    // A visible but short wait, so the refresh indicator appears on view changes.
    if (new URL(req.url()).searchParams.get("match") === "keywords" || new URL(req.url()).searchParams.get("view") === "saved") await new Promise((r) => setTimeout(r, 650));
    return json(feed(req.url()));
  }
  const m = path.match(/^\/api\/feed\/(\w+)\/save$/);
  if (m) { req.method() === "POST" ? saved.add(m[1]) : saved.delete(m[1]); return route.fulfill({ status: 204 }); }
  if (path === "/api/reminders") return json([]);
  unmatched.add(req.method() + " " + path);
  return json({ error: { code: "not_found", message: "Not in demo" } }, 404);
});
// A visible cursor: headless screenshots never include the real one.
await page.addInitScript(() => {
  addEventListener("DOMContentLoaded", () => {
    const c = document.createElement("div");
    c.style.cssText = "position:fixed;left:0;top:0;width:22px;height:22px;z-index:99999;pointer-events:none;transition:transform 40ms linear";
    c.innerHTML = '<svg width="22" height="22" viewBox="0 0 22 22"><path d="M3 2l14 8-6 1.5L8 18z" fill="#fff" stroke="#000" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    document.body.appendChild(c);
    addEventListener("mousemove", (e) => { c.style.transform = `translate(${e.clientX - 3}px, ${e.clientY - 2}px)`; }, true);
    addEventListener("mousedown", () => { c.firstChild.style.transform = "scale(.85)"; }, true);
    addEventListener("mouseup", () => { c.firstChild.style.transform = ""; }, true);
  });
});

await page.goto("http://localhost:5299/feed");
await page.locator("[data-card] h2").first().waitFor();
await page.mouse.move(640, 300);
await page.waitForTimeout(400);

// Capture frames continuously while the story plays.
const frames = [];
let recording = true;
const capture = (async () => {
  let last = Date.now();
  while (recording) {
    const buf = await page.screenshot({ type: "jpeg", quality: 88 });
    const now = Date.now();
    frames.push({ buf, at: now });
    last = now;
    await new Promise((r) => setTimeout(r, 60));
  }
})();
const glide = async (locator, steps = 22) => {
  const box = await locator.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps });
};
await page.waitForTimeout(900);
const bookmark = page.getByRole("button", { name: "Save Software Engineer, Platform" });
await glide(bookmark);
await page.waitForTimeout(300);
await bookmark.click();
await page.waitForTimeout(1500);
const keywordsTab = page.getByRole("button", { name: /Other titles matching your keywords/ });
await glide(keywordsTab);
await page.waitForTimeout(250);
await keywordsTab.click();
await page.getByText("Payments Engineer").waitFor();
await page.waitForTimeout(1500);
const savedView = page.getByRole("button", { name: /^Saved \(/ });
await glide(savedView);
await page.waitForTimeout(250);
await savedView.click();
await page.getByRole("heading", { name: "Saved jobs" }).waitFor();
await page.waitForTimeout(2200);
recording = false;
await capture;

// Durations from real timings, so the clip plays at the speed it was recorded.
const lines = [];
frames.forEach((f, i) => {
  const name = `f${String(i).padStart(3, "0")}.jpg`;
  writeFileSync(join(OUT, name), f.buf);
  const next = frames[i + 1]?.at ?? f.at + 1800;
  lines.push(`${Math.max(40, next - f.at)} ${name}`);
});
writeFileSync(join(OUT, "timings.txt"), lines.join("\n"));
console.log("frames:", frames.length, "unmatched API:", [...unmatched].join(", ") || "none");
await browser.close();
server.close();
