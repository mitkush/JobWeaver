# JobWeaver - PRD Brief

Agreed decisions from the discovery session (step 2 of the PRD workflow in `CLAUDE.md`).
The PRD (step 3) must be generated from this file. Anything under **Open questions** is unresolved and must stay flagged in the PRD, not silently decided.

Items marked *(recommendation)* were proposed during discovery and accepted, but are implementation suggestions the PRD may refine.
Third-party facts were checked on 5 Oct 2026; results are in `jobweaver-docs/COSTS.md` and PRD section 15.

---

## 1. Product in one line
An AI job-hunt assistant that fetches jobs from many sources, removes and groups duplicates, shows each job's skill gaps against the user's profile, and prepares a tailored resume, cover letter and application email for each job - which the user reviews, edits (directly or via an AI chat) and sends themselves.

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
- **Timeline:** no deadlines. Quality over speed.
- **Scope:** a **finished V1 product**, not a throwaway MVP. Everything in section 5 ships in V1. Only the browser extension (apply-form auto-fill) is deferred. Build order inside V1 is still sliced into usable phases (decided in section 10).
- **Budget:** **zero**. Only free tiers of every service.
- **Stack:** **FastAPI (Python) backend + React (TypeScript) frontend.** Chosen for the Python AI/automation ecosystem and portfolio value.
- **Hosting:** free tiers only *(recommendation)*: one web service serving API + built frontend (single URL, no CORS) on Render's free tier, with Neon's free Postgres (+ pgvector), which never expires (Render's free Postgres is deleted after 30 days).
  - Free backends sleep after ~15 min idle -> keep warm with an external monitor (UptimeRobot) pinging a lightweight `GET /health` (no DB touch) every 5 min.
  - Scheduled fetches run in an **in-process scheduler (APScheduler)** on the warm instance, as background work, never inside one long HTTP request. External cron calling a secret-protected endpoint is the fallback if the host still sleeps.

## 5. Core features (V1)

### 5.1 Accounts & settings
- Sign up / sign in with **Google only** (decided after PRD review: every user needs Google for Gmail anyway; email + password moves to Later).
- **AI data notice (decided after PRD review):** each user accepts a one-line notice in onboarding that their documents are processed by free AI tiers, before any document is sent.
- Proper multi-user model from day one (user-owned profiles, documents, preferences, drafts, credits). **Tenancy unit is the `user`**: every table, cache key and background job carries `user_id`. No workspace/organization layer.
- Settings page (editable any time; feed updates when changed):
  - Contact email
  - **Documents:** resume, cover letter / detailed portfolio, short summary
  - **Preferences (multi-select):** locations - India (cities) / non-India (countries/cities); work mode - onsite / hybrid / remote; target job titles / keywords
    - Clarification: location choices are India, other country with optional city, or Global (no country selection, including India). Location is optional. Remote means WFH, hybrid means some days in office, and onsite means office; work mode and the posting's listed location are separate filters.
- Gmail connection status + re-login reminder (see 5.4).

### 5.2 Job fetching
- **Initial backfill:** last 14 days from all sources.
- **Incremental:** per-source schedule.
  - **LinkedIn (Bright Data): daily, "past 24 hours" filter** - avoids paying for the same records twice with week-granularity filters (confirmed: "Past 24 hours", "Past week" and "Past month" are available).
  - Free sources: daily (or as rate limits allow).
- Queries are **narrow and per user** (their titles + locations) so paid credits go only to relevant jobs.
- **Bright Data credit budget:** 5,000 free credits/month (1 credit = 1 scraped record), shared across all users:
  - credit usage tracker with month-end projection
  - **full scope (decided after PRD review):** every result of every query is fetched; no daily pacing and no backfill cap, because LinkedIn postings are the most genuine. Spend per query and a month-end projection warn the admin before the budget runs out; if it runs out, LinkedIn is degraded until renewal
  - **no per-user split** (decided): all users share the pool
  - **rollout:** the first month is founder-only; friends join once the real monthly spend is known
  - **catch-up:** a missed day uses the smallest LinkedIn filter that reaches back to the last successful run (e.g. past week) for that one run
- **Source fallback (decided):** if any source fails for any reason (service unavailable, rate limit, credits/tokens exhausted, blocked), the fetch run skips it, continues with the remaining sources, marks it as degraded in a source-status view, and retries it on the next run. One failing source never stops the run. Note: sources are not interchangeable - jobs only on LinkedIn are missed while it is down; aggregators (e.g. JSearch) only partly cover them.
- **Zero-budget guard (decided):** no payment method is attached to any service, so nothing can bill beyond its free tier.
- **Job storage (decided):** every job is stored **once** in a shared `jobs` table and linked to each user it matches through a `user_jobs` table (per-user status, feed membership, drafts). A user's feed shows only jobs linked to them. Duplicate grouping runs once on the shared table; a job matched by two users costs one credit.
- **ATS company discovery (decided):** when a job from any source has an apply URL on a known ATS (e.g. `boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>`, `jobs.ashbyhq.com/<slug>`), the company slug is saved and that company's ATS board is fetched directly from then on. Pure URL parsing, no AI. Users can also add companies by hand. The list starts small and grows over time. Workday has no public job API; treat it as best-effort.
- **Two fetch modes (decided after PRD review):** windowed sources (query + time window; only see new jobs) and snapshot sources (company ATS boards; full list compared with stored jobs, so closed jobs are detected).
- **Expired jobs (decided after PRD review):** closed on a company board -> expired; windowed-only jobs expire 30 days after posting unless a company board still lists them; the apply link is checked before drafting when that is free.

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
- **No match score (decided).** Each card shows only **skill gaps**: "Missing: Kubernetes, Go" - required skills from the JD that are not in the user's documents. Required skills are extracted from the JD once at ingestion; the comparison against the user's skills is done in code.
- Feed order: newest first *(recommendation)*.
- **Multi-location jobs (decided):** the same job (same text / job ID) posted for several cities is **one job with location chips**; it matches the user's filter if any of its locations fits. Different text or job ID = separate jobs.
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
  - Requires the `gmail.compose` scope (confirmed restricted). Run the Google OAuth app in **testing mode** (up to 100 named test users, no Google verification needed).
  - In testing mode refresh tokens expire **7 days after consent** (confirmed) -> the app detects expiry and shows a **re-login reminder**.
  - **Fallback (Option B):** Gmail compose link with to/subject/body pre-filled; user attaches the downloaded PDF manually (compose links cannot attach files).
- For jobs without an email: download the PDFs, open the apply link, mark as applied.

### 5.5 Correspondence (duplicates)
- Groups the same job found on multiple sources into one **stack**; the user can open **every** copy on every platform, regardless of priority.
- Matching is **semantic, not word-for-word** - an organisation may post the same opening with different wording. Based on company/organisation (normalised, e.g. "Google LLC" = "Google") + JD content/requirements + title *(recommendation: text embeddings + pgvector similarity)*.
- **Confidence bands (decided):**
  - **Exact** (same ATS job ID or same apply URL): grouped automatically.
  - **High** (same normalised company + very similar title + very close JD meaning): grouped automatically.
  - **Medium** (same company and similar title, but JD or location differs noticeably): shown as **"Possible duplicate"** with one-click Confirm / "Not the same job".
  - **Low:** kept as separate jobs.
  - Any group can be **split** with "Not the same job"; the decision is stored and never re-proposed.
  - Thresholds start strict (small medium band) and are tuned on real data.
- The primary record follows the source priority list, but **fields are merged** - e.g. an email found only in a lower-priority copy must not be lost.

### 5.6 Application tracker
- Status per job: Drafted -> Applied/Sent -> Replied -> Interview -> Offer / Rejected (manual updates; reading replies from Gmail is out of scope).

### 5.7 Follow-up reminder
- Reminder after N days with no update (reminder only, never auto-sent).

## 5.8 UI / UX
- **UI:** attractive and professional, consistent design system *(recommendation: Tailwind CSS + a component library such as shadcn/ui, light and dark mode)*.
- **UX must never be confusing.** The PRD must turn this into checkable rules, for example:
  - one clear primary action per screen (Feed: open job; Draft: Open in Gmail)
  - from a job card to a ready draft in at most 2 clicks
  - every async step shows its state (fetching, generating, saved, sent to Gmail, failed with a clear next step)
  - helpful empty states (no jobs yet, no documents uploaded, Gmail not connected) that say what to do next
  - no destructive or outward action without confirmation; nothing is sent automatically
  - consistent names: the same term from `CONTEXT.md` everywhere in the UI
  - responsive layout, keyboard accessible, readable contrast
- Draft screen layout: draft editor in the centre, AI chat panel on the right, diff / trace viewable without leaving the screen.

## 6. AI
- **Provider fallback chain** behind one abstraction layer: **Google Gemini (Flash / Flash-Lite) -> Groq -> OpenRouter `:free`**. **Ollama** for local development only (cannot run on free hosting).
- **Shared keys (decided):** all users run on the founder's API keys (AI providers, Bright Data, Apify and the other sources). No per-user keys.
- **Budget after the trial (decided):** zero budget during a one-month trial; after that the founder plans to move to paid tiers where needed. Paid tiers are a configuration change, not a redesign.
- AI tasks: HN free-text extraction, JD parsing (required skills), semantic dedup, resume/cover-letter/email tailoring, draft chat edits.
- **Embeddings (decided after PRD review):** Gemini only (Groq and OpenRouter have no free embeddings, and vectors from different models cannot be compared). Each vector stores its model name; when Gemini is down, postings are queued for embedding instead of being compared without it; a model change means re-computing all vectors.

## 7. Architecture patterns (decided)
- **Source adapter registry:** each job source is one module implementing a fixed interface (windowed or snapshot mode) and registering itself. Adding a source = one new module + one import line, never an `if source == ...` branch.
- **Thin AI Gateway:** the only module that imports a provider SDK; typed task methods (`extract_job`, `extract_requirements`, `embed`, `tailor_resume`, `draft_email`, `edit_draft`); per-task model routing; per-user usage accounting; text-task fallback Gemini -> Groq -> OpenRouter; **recorded-response mode so CI and tests make zero live AI calls**.
- **Tenancy from day one:** every user-owned table, cache key and background job carries `user_id`, with cross-user isolation tests.
- **"AI proposes, human disposes":** nothing AI-generated is sent or merged without the user's review. Applies to drafts, parsed facts and medium-confidence duplicate groups.
- **"Facts from code, words from AI":** AI extracts required skills from a JD once; the skill-gap comparison is deterministic code. Keeps it cheap, testable and consistent within free AI limits.
- **Trace:** every tailored resume line links back to the fact in the user's documents it came from, which makes the no-fabrication rule (5.4) checkable.
- **Match Pair / Rejected Pair loop** for duplicates: each pair carries a confidence band; high confidence groups automatically, medium is shown as "possible duplicate"; "not the same job" is stored and never re-proposed.
- **Credentials at rest** encrypted - Gmail OAuth tokens and any stored API keys.
- **Docs and repo setup:** `CONTEXT.md` glossary, ADRs, `COSTS.md`, CI with lint + typecheck + tests, OpenAPI-generated frontend types.

## 8. Out of scope for V1 (later)
- Browser (Chrome) extension: auto-filling apply-link forms
- Reading Gmail replies automatically (needs another restricted scope)
- Public launch / paid plans
- Recruiter / employer side
- Email + password sign-in

## 9. Accepted risks (decided by the founder; PRD must record them, not re-open them)
- **Scraping LinkedIn / Naukri** via Bright Data and Apify breaches those sites' terms of service. This is a civil (contract) risk, not a criminal one. Accepted because use is private (founder + friends). **Must be revisited before any public or paid launch** - that is the point where it becomes the business's risk.
- **Free-tier AI and data privacy:** free tiers may use prompts to improve the provider's products, (confirmed for Gemini). Accepted for private use; revisit before going public. Gemini also requires paid services for users in the EEA, Switzerland or the UK, so V1 users on the free tier must be outside those regions.
- **Free-tier volatility:** free limits of every source and AI provider can change without notice; the fallback chain and per-source scheduling mitigate it.

## 10. Open questions (unresolved - keep flagged in the PRD)
None. Last decisions after the PRD review: **success metrics** as recommended in PRD section 13; **"Not the same job" applies to everyone**; **open sign-up**, no invite list (Google testing mode still limits sign-in to named test users).

**Resolved in the last round:**
- **All sources ship in V1 (decided).** Free-tier limits are not verified up front; any limit hit is handled at run time by the source fallback (5.2). `COSTS.md` still documents each known limit.
- **Resume template (decided):** default is the founder's single-column ATS-friendly layout; choosing or uploading another template is optional per user.
- **Build order (decided; refined after PRD review):** like a full product, foundation first: auth and accounts -> first 4 sources (LinkedIn via Bright Data, JSearch, Greenhouse/Lever, Remotive) -> UI (settings, feed, Correspondence) -> Draft (tailoring, chat, Gmail) -> remaining sources -> tracker, reminders and polish. Site-fetch sources (Instahyre, Cutshort, Hirist, Foundit, Workday) may be blocked from cloud IPs and are built last.

## 11. Repo conventions (decided)
- Use "-" in prose, never the em dash character (docs, code comments, PR descriptions, commit messages).
- Single-line commit messages, no body, no AI co-author trailer.
- PR titles `<type>: <imperative summary>` under 70 chars, with a `## Walkthrough` section.

## 12. PRD must include
Structure and quality bar:
- **Deliverables:** `jobweaver-docs/PRD.md` + `CONTEXT.md` (glossary: Source, Job, Posting, Correspondence, Fact Bank, Draft, Application, ...) + `docs/adr/` (one short ADR per locked decision above) + `COSTS.md` (every free tier, its limit, and what happens when it runs out).
- **PRD sections:** summary, problem, goals and non-goals, personas, product principles, functional requirements grouped by epic with IDs (FR-A1 ...), each tagged **[V1] / [Later]** with acceptance criteria, non-functional requirements table (security of stored OAuth tokens and resumes, reliability under free-tier limits, cost guardrails, testability with zero live AI calls in CI), key user flows, technology stack table with reasons, release plan with phases, success metrics, risks with mitigations, open questions.
- Cite ADRs inline ("ADR-NNNN: what it decides"); capitalised terms defined in `CONTEXT.md`.
- High-level architecture: FastAPI + React, scheduler, source adapters, dedup pipeline, AI Gateway, Gmail integration, data model.
