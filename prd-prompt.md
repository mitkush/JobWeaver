# JobWeaver - PRD Brief

Agreed decisions from the discovery session (step 2 of the PRD workflow in `CLAUDE.md`).
The PRD (step 3) must be generated from this file. Anything under **Open questions** is unresolved and must stay flagged in the PRD, not silently decided.

Items marked *(recommendation)* were proposed during discovery and accepted, but are implementation suggestions the PRD may refine.
Items marked *(verify)* are facts about third-party services stated with moderate confidence; the PRD must list them as things to confirm before build.

---

## 1. Product in one line
An AI job-hunt assistant that fetches jobs from many sources, removes and groups duplicates, ranks them against the user's profile, and prepares a tailored resume, cover letter and application email for each job - which the user reviews, edits (directly or via an AI chat) and sends themselves.

## 2. Problem & users
- **Problem:** job hunting means checking many boards, seeing the same job reposted across sites, and rewriting the resume and cover letter for each job. Generic applications don't pass ATS screening and look vague.
- **Primary user:** the founder (a senior developer with experience across many technologies), whose full experience doesn't fit one generic resume.
- **Secondary users:** a few of the founder's friends, each with their own profile, resume and preferences.
- **Not targeted now:** recruiters/employers, the general public.

## 3. Goal & positioning
- **Now:** personal tool for the founder + a few friends.
- **Quality bar:** portfolio-grade (clean architecture, docs, tests) and **business-ready** - the data model and architecture must not need a rewrite to go multi-tenant/paid later.
- **Market / job coverage:** global - jobs in India (city-level) and outside India, onsite / hybrid / remote. "Global" refers to job coverage; the user base is the founder + friends for now.

## 4. Constraints
- **Team:** solo developer.
- **Timeline:** as soon as possible.
- **Scope:** a **finished V1 product**, not a throwaway MVP. Everything in section 5 ships in V1. Only the browser extension (apply-form auto-fill) is deferred. Build order inside V1 is still sliced into releasable phases (see open question 9).
- **Budget:** **zero**. Only free tiers of every service.
- **Stack:** **FastAPI (Python) backend + React (TypeScript) frontend.** Chosen for the Python AI/automation ecosystem and portfolio value.
- **Hosting:** free tiers only, reusing the setup already proven on OneBrain *(recommendation)*: one web service serving API + built frontend (single URL, no CORS) on Render/Railway free tier, free Postgres (+ pgvector), Redis free tier if needed.
  - Free backends sleep after ~15 min idle -> keep warm with an external monitor (UptimeRobot) pinging a lightweight `GET /health` (no DB touch) every 5 min.
  - Scheduled fetches run in an **in-process scheduler (APScheduler)** on the warm instance, as background work, never inside one long HTTP request. External cron calling a secret-protected endpoint is the fallback if the host still sleeps.
  - Some free databases pause after inactivity *(verify per provider)*; daily fetches should keep them active.

## 5. Core features (V1)

### 5.1 Accounts & settings
- Sign up / sign in with **Google** or **email + password**.
- Proper multi-user model from day one (user-owned profiles, documents, preferences, drafts, credits). **Tenancy unit is the `user`**: every table, cache key and background job carries `user_id`. No workspace/organization layer.
- Settings page (editable any time; feed updates when changed):
  - Contact email
  - **Documents:** resume, cover letter / detailed portfolio, short summary
  - **Preferences (multi-select):** locations - India (cities) / non-India (countries/cities); work mode - onsite / hybrid / remote; target job titles / keywords
- Gmail connection status + re-login reminder (see 5.4).

### 5.2 Job fetching
- **Initial backfill:** last 14 days from all sources.
- **Incremental:** per-source schedule.
  - **LinkedIn (Bright Data): daily, "past 24 hours" filter** - avoids paying for the same records twice with week-granularity filters *(verify the time-range options of the Bright Data LinkedIn scraper)*.
  - Free sources: daily (or as rate limits allow).
- Queries are **narrow and per user** (their titles + locations) so paid credits go only to relevant jobs.
- **Bright Data credit budget:** 5,000 free credits/month (1 credit = 1 scraped record), shared across all users:
  - credit usage tracker with month-end projection
  - backfill capped *(recommendation: ~1,500 records)* so it cannot exhaust the month
  - per-user credit quota so one user cannot drain the pool
  - automatic slow-down / pause before the budget runs out
- Detect and hide **expired / closed** jobs.

**Sources, in priority order** (priority decides the primary record in a duplicate group, nothing else):

| # | Source | Type |
|---|---|---|
| 1 | Bright Data / Apify (LinkedIn) | Direct from LinkedIn |
| 2 | Naukri (via Apify) | Direct, largest board in India |
| 3 | Greenhouse / Lever / Ashby / SmartRecruiters / Workable / Recruitee / Workday | Direct from the company's ATS |
| 4 | Instahyre / Cutshort / Hirist | Direct, Indian tech boards |
| 5 | JSearch | Aggregator (Google for Jobs, Indeed, Glassdoor) |
| 6 | SerpApi Google Jobs | Aggregator, overlaps with JSearch |
| 7 | Adzuna | Aggregator |
| 8 | Remotive / Remote OK / We Work Remotely / Himalayas / Jobicy / Working Nomads | Remote-only boards |
| 9 | Hacker News "Who is hiring" | Free text; needs AI extraction |
| 10 | Foundit | Low priority, overlaps with Naukri |

### 5.3 Feed
- Two sections:
  1. Jobs **with** a contact email
  2. Jobs **without** an email (apply link only)
- Every job is ranked by a **match score with reasons** (e.g. "7/9 required skills; missing Kubernetes").
- Each card shows **"Available on"** badges for every source where the job also appears.
- **"Already applied to this company"** warning.

### 5.4 Draft (the main feature)
- A draft can be created for **any** job in the feed (with or without email).
- Draft contents: tailored **resume (PDF)**, tailored **cover letter**, and an **application email** (for jobs with an email).
- **Tailoring rule (hard requirement):** the AI optimises and focuses the resume for the specific JD (ATS keywords, relevance, ordering) by selecting and rewriting from the user's **own uploaded documents** - the detailed portfolio/cover letter is the fact bank; the resume is a condensed selection. The AI may pull portfolio-only items into the resume when the JD calls for them, but **must not add skills, projects or experience that do not exist in the user's documents**.
- Show a **diff** of what changed versus the base resume.
- User can edit the draft directly, or ask for changes through an **AI chat panel on the right side** of the same tab; changes apply to the draft live.
- **Email check** in the draft: validate the recipient address (format, domain can receive mail, not a no-reply address).
- **Separate "Save draft" and "Send / Open in Gmail" actions.** Nothing is ever sent automatically.
- **Gmail hand-off (decided: Option A):** JobWeaver creates a real **Gmail draft with the PDF attached** via the Gmail API; the user opens it in Gmail, can change formatting there, and sends it from Gmail.
  - Requires the `gmail.compose` scope *(verify: classified as restricted)*. Run the Google OAuth app in **testing mode** (up to 100 named test users, no Google verification needed).
  - In testing mode refresh tokens expire about **every 7 days** *(verify)* → the app detects expiry and shows a **re-login reminder**.
  - **Fallback (Option B):** Gmail compose link with to/subject/body pre-filled; user attaches the downloaded PDF manually (compose links cannot attach files).
- For jobs without an email: download the PDFs, open the apply link, mark as applied.

### 5.5 Correspondence (duplicates)
- Groups the same job found on multiple sources into one **stack**; the user can open **every** copy on every platform, regardless of priority.
- Matching is **semantic, not word-for-word** - an organisation may post the same opening with different wording. Based on company/organisation (normalised, e.g. "Google LLC" = "Google") + JD content/requirements + title *(recommendation: text embeddings + pgvector similarity)*.
- The primary record follows the source priority list, but **fields are merged** - e.g. an email found only in a lower-priority copy must not be lost.

### 5.6 Application tracker
- Status per job: Drafted → Applied/Sent → Replied → Interview → Offer / Rejected (manual updates; reading replies from Gmail is out of scope).

### 5.7 Follow-up reminder
- Reminder after N days with no update (reminder only, never auto-sent).

## 6. AI
- **Provider fallback chain** behind one abstraction layer: **Google Gemini (Flash / Flash-Lite) → Groq → OpenRouter `:free`**. **Ollama** for local development only (cannot run on free hosting).
- Uses the founder's own AI accounts. Per-user own API keys are an optional later addition.
- AI tasks: HN free-text extraction, JD parsing, match scoring, semantic dedup, resume/cover-letter/email tailoring, draft chat edits.

## 7. Patterns to reuse from OneBrain (`mitkush/OneBrain`)
Same founder, same stack, already built and working. The PRD should reuse these rather than reinvent them *(recommendation)*:
- **Source adapter registry** (OneBrain's connector plugin pattern): each job source is one module implementing a fixed interface (e.g. `fetch(query, since)`, `normalize(raw) -> Job`) and registering itself. Adding a source = one new module + one import line, never an `if source == ...` branch.
- **Thin AI Gateway** (ADR-0009 there): the only module that imports a provider SDK; typed task methods (`extract_job`, `score_match`, `tailor_resume`, `draft_email`, `edit_draft`); per-task model routing; per-user token/credit accounting; the existing `FallbackAIGateway` pattern extended to Gemini -> Groq -> OpenRouter; **recorded-response mode so CI and tests make zero live AI calls**.
- **Tenancy from day one** (ADR-0001 there): every table, cache key and background job carries the owner id (`user_id`), with cross-user isolation tests.
- **"AI proposes, human disposes"**: nothing AI-generated is sent or merged without the user's review. Applies to drafts, and *(recommendation)* to low-confidence duplicate groups.
- **"Numbers from code, words from AI"**: match score computed deterministically (skill/keyword overlap, location, work mode, seniority); the LLM only writes the reasons. Keeps scoring cheap, testable and consistent within free AI limits.
- **Trace**: every tailored resume bullet links back to the fact in the user's documents it came from. This makes the no-fabrication rule (5.4) checkable, the same way OneBrain answers expose how they were computed.
- **Match Pair / Rejected Pair loop** for duplicates: each pair carries a confidence score; high confidence groups automatically, low confidence is shown as "possible duplicate"; "not the same job" is stored and never re-proposed.
- **Credentials at rest** encrypted (Fernet, as in OneBrain) - here: Gmail OAuth tokens, Bright Data / Apify / AI keys.
- **Docs and repo setup**: `CONTEXT.md` glossary, ADRs, `COSTS.md`, `.claude/skills/` coding standards, CI with lint + typecheck + tests, OpenAPI-generated frontend types.

## 8. Out of scope for V1 (later)
- Browser (Chrome) extension: auto-filling apply-link forms
- Reading Gmail replies automatically (needs another restricted scope)
- Public launch / paid plans
- Recruiter / employer side

## 9. Accepted risks (decided by the founder; PRD must record them, not re-open them)
- **Scraping LinkedIn / Naukri** via Bright Data and Apify breaches those sites' terms of service. This is a civil (contract) risk, not a criminal one. Accepted because use is private (founder + friends). **Must be revisited before any public or paid launch** - that is the point where it becomes the business's risk.
- **Free-tier AI and data privacy:** free tiers may use prompts to improve the provider's products, and some providers restrict free tiers for users in certain regions *(verify Gemini's terms)*. Accepted for private use; revisit before going public.
- **Free-tier volatility:** free limits of every source and AI provider can change without notice; the fallback chain and per-source scheduling mitigate it.

## 10. Open questions (unresolved - keep flagged in the PRD)
1. **Shared job store vs per-user fetch.** Recommendation: store every fetched job once in a shared table (needed anyway for Correspondence/dedup) while keeping fetching and feeds per user. When two users' queries overlap, a LinkedIn record is paid for once instead of twice. The founder's position: don't share, because jobs fetched for one user may be irrelevant to others. Not yet agreed. Note that a shared store does not mean a shared feed.
2. **Credit split between users:** how the 5,000 Bright Data credits are divided (equal quota, or founder-priority?).
3. **Free-tier limits to confirm:** Apify monthly free credit (Naukri), JSearch, SerpApi, Adzuna; whether each fits a daily schedule.
4. **ATS company discovery:** the Greenhouse/Lever/Ashby/etc. public APIs need a list of companies (board tokens). How is that list built and maintained? Workday has no public job API.
5. **Duplicates across locations:** is the same job posted for three cities one job or three?
6. **Match-score method:** embeddings only, LLM only, or both - and how reasons are generated within free AI limits.
7. **Resume PDF template:** default to the founder's current single-column ATS-friendly layout; can users upload or choose others?
8. **Success metrics** for a personal tool (e.g. jobs reviewed per week, drafts sent, reply rate, time per application) - to be defined in the PRD.
9. **V1 build phasing for a solo, ASAP build:** which sources and features land in which release slice.
10. **Duplicate confirmation:** recommended: three confidence bands (exact/high = auto-group; medium = "possible duplicate" with one-click confirm; low = separate), plus a "not the same job" split on any group, stored and never re-proposed. Awaiting founder confirmation.

## 11. Repo conventions (decided: follow OneBrain's)
- Use "-" in prose, never the em dash character (docs, code comments, PR descriptions, commit messages).
- Single-line commit messages, no body, no AI co-author trailer.
- PR titles `<type>: <imperative summary>` under 70 chars, with a `## Walkthrough` section.

## 12. PRD must include
Match the structure and quality bar of OneBrain's `onebrain-docs/PRD.md`:
- **Deliverables:** `jobweaver-docs/PRD.md` + `CONTEXT.md` (glossary: Source, Job, Posting, Correspondence, Fact Bank, Draft, Application, ...) + `docs/adr/` (one short ADR per locked decision above) + `COSTS.md` (every free tier, its limit, and what happens when it runs out).
- **PRD sections:** summary, problem, goals and non-goals, personas, product principles, functional requirements grouped by epic with IDs (FR-A1 ...), each tagged **[V1] / [Later]** with acceptance criteria, non-functional requirements table (security of stored OAuth tokens and resumes, reliability under free-tier limits, cost guardrails, testability with zero live AI calls in CI), key user flows, technology stack table with reasons, release plan with phases, success metrics, risks with mitigations, open questions.
- Cite ADRs inline ("ADR-NNNN: what it decides"); capitalised terms defined in `CONTEXT.md`.
- High-level architecture: FastAPI + React, scheduler, source adapters, dedup pipeline, AI Gateway, Gmail integration, data model.
