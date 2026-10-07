# PRD - JobWeaver

**Owner:** Mitanshu Kushwah (solo) · **Status:** Draft for review · **Last updated:** 5 Oct 2026
**Scope:** V1, a finished product (no deadline; quality over speed)
**Companion docs:** [`CONTEXT.md`](./CONTEXT.md) (domain glossary; capitalised terms in this PRD are defined there) · [`docs/adr/`](./docs/adr/) (why decisions were made, cited inline as "ADR-NNNN: what it decides") · [`COSTS.md`](./COSTS.md) (every free tier and what happens at its limit) · [`../prd-prompt.md`](../prd-prompt.md) (the discovery brief this PRD is built from)

---

## 1. Summary

JobWeaver is an AI job-hunt assistant. It fetches jobs every day from many Sources (LinkedIn, Naukri, company ATS boards, aggregators, remote boards, Hacker News), groups the same job found on different sites into one Job, and shows each User a personal Feed filtered by their Preferences with the Skill Gaps for every Job. For any Job, it prepares a Draft: a Tailored Resume, a Cover Letter and an Application Email, built only from the User's own Fact Bank. The User refines the Draft directly or through a Draft Chat, then opens it in Gmail with the PDF attached and sends it themselves.

The product's two promises:
1. **Never miss a genuine job, and never see the same job five times.** Many Sources, one Job per real opening, every copy still reachable (ADR-0004: two-layer dedup with confidence bands).
2. **A sharper resume for every job, with nothing made up.** Every tailored line traces back to something the User actually did (ADR-0005: Fact Bank, no fabrication), and nothing is sent without the User (ADR-0006: the User sends from Gmail).

## 2. Problem

A developer looking for work, especially one with experience across many technologies, faces four recurring problems:

- **Too many places to look.** LinkedIn, Naukri, company career pages, aggregators and remote boards each show a different slice of the market. Checking them all daily is not sustainable, so good jobs are missed.
- **The same job, again and again.** One opening appears on LinkedIn, the company's Greenhouse board and two aggregators, often reworded. Time goes into re-reading jobs already seen.
- **One resume cannot fit every job.** A full-stack developer with Rails, Python, AI evaluation and DevOps experience has more than fits on one page. A generic resume reads as vague and does poorly in ATS keyword screening; rewriting it per job takes 30 to 60 minutes.
- **Applying is repetitive.** Cover letter, email, attachment, tracking where you applied and when to follow up: all manual.

Existing tools solve parts of this. Job boards and aggregators show jobs but not duplicates across sites. AI resume tools rewrite resumes but freely invent content and do not know which jobs exist. Auto-apply tools send applications without review, which harms the applicant's reputation. Nothing joins **finding**, **de-duplicating** and **truthful tailoring** with the human still in control.

## 3. Goals and Non-Goals

### Goals
1. **G1 - Coverage:** a User sees new matching Jobs from every healthy Source within a day of posting, without visiting any job site. When a Source is down or out of budget, the Feed says so (FR-B6).
2. **G2 - One Job, one card:** duplicates across Sources are grouped, and every original Posting stays one click away.
3. **G3 - Tailored in minutes:** from a Job card to a ready Draft in at most 2 clicks, and to a Gmail draft with the PDF attached in under 5 minutes of the User's time.
4. **G4 - Truthful by construction:** zero fabricated skills, projects or claims in any Draft (ADR-0005: Fact Bank, no fabrication).
5. **G5 - Human sends:** nothing is ever sent without the User's own action in Gmail (ADR-0006: the User sends from Gmail).
6. **G6 - $0 to run:** the whole product runs on free tiers and degrades gracefully when any of them runs out (ADR-0008: zero-budget free-tier hosting).
7. **G7 - Portfolio and business grade:** clean architecture, tests and docs; going paid later needs no data-model rewrite (ADR-0001: User tenancy from day one).

### Non-Goals (deliberate)
- **Not an auto-apply bot.** JobWeaver never sends emails or submits forms on its own.
- **Not a job board.** It does not host job adverts or serve employers.
- **Not a match-score ranker.** Cards show Skill Gaps, not a percentage (ADR-0010: Skill Gaps, not a match score).
- **Not a resume ghostwriter.** It never invents experience to fit a job.
- **Not public in V1.** Users are the founder and a few friends; public or paid launch needs the pre-launch review in ADR-0012.

## 4. Users

### P1 - The Job Seeker (primary)
A software professional (the founder is the reference: a senior developer with three-plus years across Ruby on Rails, Python/FastAPI, React and AI evaluation) looking in India and abroad, onsite, hybrid or remote. Has more relevant experience than fits on one resume. Wants to spend time on good applications, not on searching. Success for P1: *"I opened JobWeaver, picked three good jobs I had not seen elsewhere, and had three strong, honest applications in my Gmail drafts within 15 minutes."*

### P2 - The Friend (secondary)
Another job seeker the founder brings in, possibly in a different field or country, with their own documents and Preferences. Must never see P1's data, and should be productive without help from the founder.

### P3 - The Admin (the founder, wearing a different hat)
Keeps the system running: watches Source Status and the Credit Budget, enables or disables Sources, narrows expensive queries. Success for P3: *"I check the status page once a week and nothing surprises me."*

## 5. Product Principles

1. **AI proposes, the User disposes.** Drafts, Possible Duplicates and parsed Facts are proposals until the User accepts them. Nothing outward happens without a User action.
2. **Facts from the User, words from the AI.** The AI may phrase, select and order; it may not add facts (ADR-0005: Fact Bank, no fabrication).
3. **Facts from code, words from AI.** Anything that must be consistent and testable (Skill Gaps, duplicate bands, budget projections) is computed in code; the AI extracts and writes (ADR-0010: Skill Gaps, not a match score).
4. **Every copy is reachable.** Grouping never hides a Posting; priority picks a display default, not a winner (ADR-0004: two-layer dedup with confidence bands).
5. **Degrade, never die.** Any Source or AI provider can fail; the product keeps working and says what is missing (ADR-0003: Source Adapters with per-source fallback).
6. **No confusing screens.** One clear main action per screen, visible status for everything slow, and one name per concept everywhere (section 8).

## 6. Functional Requirements

Every requirement is tagged **[V1]** (ships in V1) or **[Later]**. Each [V1] item has acceptance criteria (AC).

### Epic A - Accounts and Profile

**FR-A1 [V1] - Sign in with Google.** Users sign up and sign in with Google only (ADR-0015: Google sign-in only in V1). Every User needs a Google account anyway for the Gmail Hand-off, and only named Google test users can use the OAuth app in testing mode.
- AC1: A new User signs in with Google and lands on onboarding; Gmail access can be granted in the same consent or later (FR-A4).
- AC2: Sessions are signed, HTTP-only cookies with CSRF protection.
- AC3: Sign-up is open: any Google account that can sign in can create an account; there is no in-app invite list. Note: while the Google OAuth app is in testing mode, Google itself only lets named test users (up to 100) sign in, so the Admin adds each new User as a test user in Google Cloud. The sign-in screen explains this when Google blocks an account.
- AC4: While the Gemini free tier is in use, Users must be outside the EEA, Switzerland and the UK (Gemini terms, ADR-0012); onboarding asks for the User's country and explains this.

**FR-A2 [V1] - Fact Bank from uploaded documents.** The User uploads their resume and, optionally, a detailed portfolio or cover letter and a short summary (PDF; DOCX optional). The AI Gateway parses them into Facts: skills, experiences, projects, bullets, metrics and links, each linked to the document it came from. The User reviews the parsed Facts once and can edit, merge, delete or add Facts.
- AC1: Uploading the founder's resume and portfolio produces Facts that include portfolio-only items (e.g. Prism AST, the agent-skills talk) marked as "not in Base Resume".
- AC2: No Draft can be generated until the User has reviewed the Fact Bank at least once.
- AC3: Re-uploading a document shows what changed and keeps the User's manual edits.
- AC4: A User can export and delete their Fact Bank and documents.

**FR-A3 [V1] - Preferences.** Multi-select target titles and keywords, locations (India cities; other countries and cities) and work modes (onsite, hybrid, remote). Editable at any time.
- Location choices are India, other country (with optional city), or Global (no country/city restriction, including India). Job locations are optional: an empty list means Global. Work mode is separate: remote means WFH, hybrid means some days in the office, and onsite means office. A posting can list India and be remote; its listed place is the office location. Location and work mode must both match. For a remote (WFH) Job only the country has to match a chosen place (a remote Job listed in Pune matches a User who chose Bengaluru); for onsite and hybrid Jobs the city must match too.
- AC1: Changing Preferences updates the Feed from Jobs already fetched within one minute, without waiting for the next Fetch Run.
- AC2: New titles or locations are included in the next Fetch Run's queries; a Backfill runs for them.

**FR-A4 [V1] - Gmail connection.** The User connects Gmail (Google OAuth, `gmail.compose`) from Settings or at the first Open in Gmail.
- AC1: Settings shows the connection status: Connected, Expires soon, Expired.
- AC2: When the refresh token has expired (7 days after consent in testing mode), the app shows a re-login reminder before the next Gmail Hand-off is attempted, not after it fails.
- AC3: Gmail tokens are encrypted at rest and never logged.

**FR-A5 [V1] - Onboarding.** A first-run flow walks the User through: AI data notice -> upload documents -> review Fact Bank -> set Preferences -> connect Gmail (skippable). It ends on the Feed.
- AC1: Every step can be resumed later; skipping a step leaves a clear empty-state prompt where it is needed.
- AC2: Before the first upload, a one-line notice the User must accept says that their documents are processed by free AI services (Gemini, Groq, OpenRouter) whose free tiers may use the content to improve their products (ADR-0012: accepted risks for private use). No document is sent to any AI provider before acceptance.

**FR-A6 [V1] - Account deletion.** A User can delete their account; all user-owned data is removed (shared job data is not user data, ADR-0002: Jobs stored once, linked to Users).

**FR-A7 [Later] - Email and password sign-in.** For a public product: email and password with verification and reset (needs a transactional email provider, see ADR-0015).

### Epic B - Sources and Fetching

**FR-B1 [V1] - Source Adapter registry with two fetch modes.** Each Source is one adapter module registered by name (ADR-0003: Source Adapters with per-source fallback). An adapter declares one of two modes:
- **Windowed** (LinkedIn, Naukri, JSearch, SerpApi, Adzuna, Indian boards, remote boards, HN, Foundit): fetch Postings for a query and a time window; only new Postings are seen.
- **Snapshot** (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, Workday): fetch the complete list of open jobs for one ATS Board; the list is compared with stored Postings, so new, changed and closed Postings are all detected.

Both modes normalise into Postings and report credits or requests used.
- AC1: Adding a Source touches one new module and one import line; no core file changes (checked in code review).
- AC2: Every adapter has recorded-fixture tests for success, limit-exceeded and malformed responses.

**FR-B2 [V1] - All Sources in V1.** Adapters for every Source in the priority list below. Priority is used only to choose a Job's Primary Posting.

| Priority | Source | Type |
|---|---|---|
| 1 | LinkedIn (Bright Data; Apify as an alternative) | Direct |
| 2 | Naukri (Apify) | Direct, largest board in India |
| 3 | Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, Workday | Company ATS boards |
| 4 | Instahyre, Cutshort, Hirist | Indian tech boards |
| 5 | JSearch | Aggregator (Google for Jobs, Indeed, Glassdoor) |
| 6 | SerpApi Google Jobs | Aggregator |
| 7 | Adzuna | Aggregator |
| 8 | Remotive, Remote OK, We Work Remotely, Himalayas, Jobicy, Working Nomads | Remote-only boards |
| 9 | Hacker News "Who is hiring" | Free text, AI extraction |
| 10 | Foundit | Board, overlaps with Naukri |

**FR-B3 [V1] - Backfill and daily fetch.** On first enable (and for new Preferences) a windowed Source fetches the last 14 days. After that, windowed Sources run daily on a window from their last successful run, minus a small overlap (e.g. 2 hours); snapshot Sources fetch their full board daily. Duplicates from overlaps are removed by Epic C.
- AC1: A missed day (host asleep, Source down) is caught up on the next run from the last successful watermark, not from "24 hours ago". Sources that only offer fixed filters (e.g. LinkedIn: past 24 hours, past week) use the smallest filter that reaches back to the watermark for that one catch-up run; Postings already stored are skipped (and on credit Sources, are still paid for).
- AC2: Fetch Runs are idempotent: re-running a window never creates duplicate Postings.

**FR-B4 [V1] - LinkedIn via Bright Data.** Runs daily with the "past 24 hours" filter (catch-up per FR-B3), one query per distinct (title, location) combination across all Users' Preferences. **Every result of every query is fetched; JobWeaver never silently truncates LinkedIn results to fit the budget** (ADR-0009: LinkedIn full scope with a visible budget).
- AC1: Two Users with the same title and location trigger one query, not two.
- AC2: The adapter uses the scraper's "Past 24 hours" time range (seen in use alongside "Past week" and "Past month"; full list confirmed in the Bright Data dashboard when building); overlap records are stored once, and the credits they cost show in the Credit Budget.

**FR-B5 [V1] - Credit Budget.** The Admin sees each credit- or quota-limited Source's monthly allowance, spend to date, spend per query, and a month-end projection.
- AC1: When the projection says the budget will run out before renewal, the Admin is warned with the date and the most expensive queries, so they can narrow Preferences themselves. JobWeaver does not cap daily spend or the Backfill on its own.
- AC2: When a Source's budget is exhausted it becomes Degraded with reason "budget exhausted until <renewal date>"; other Sources are unaffected.
- AC3: No per-user quota (decided). Rollout: in the first month only the founder uses LinkedIn, so the full 5,000 credits serve one User's queries; friends are added after the first month's spend is known.

**FR-B6 [V1] - Source fallback and Source Status.** A Fetch Run that fails for any reason marks that Source Degraded with the reason, keeps everything already fetched from other Sources, and retries on the next run.
- AC1: Simulating "service unavailable" on one Source leaves the Feed updated from all others.
- AC2: The Admin's Source Status screen lists each Source with state, last success, last error and next run; the Admin can disable or re-enable a Source.
- AC3: Users see a short, non-alarming notice when a Source their Feed depends on has been Degraded for more than a day ("LinkedIn jobs are delayed; other sources are up to date").

**FR-B7 [V1] - ATS Board discovery.** Apply URLs of all Postings are checked against known ATS URL patterns; new ATS Boards are saved and fetched directly from the next run (ADR-0013: ATS Boards discovered from apply URLs).
- AC1: A LinkedIn Posting whose apply link is `boards.greenhouse.io/stripe/jobs/123` adds the `greenhouse:stripe` board.
- AC2: Users can add a company's ATS Board by URL from Settings.
- AC3: Boards with no Postings for 30 days are fetched weekly instead of daily.

**FR-B8 [V1] - Hacker News extraction.** Comments in the monthly "Who is hiring" thread are turned into Postings by the AI Gateway (Company, title, locations, work mode, contact email, apply link, description).
- AC1: Comments that are not job adverts are skipped, not turned into empty Postings.
- AC2: If the AI quota is exhausted, extraction is queued and resumed later; no comment is lost.

**FR-B9 [V1] - Normalisation.** Every adapter emits Postings with normalised Company name, title, locations (city, country, remote flag), work mode, posted date, apply URL, contact email (extracted from the description where present) and Source-specific ID.
- AC1: "Bengaluru", "Bangalore" and "Bangalore Urban" normalise to one city; "Google LLC" and "Google" to one Company.
- AC2: Emails found in the description are extracted into the contact-email field.

**FR-B10 [V1] - Expired Jobs.** A Job becomes an Expired Job and leaves the Feed when:
- a snapshot Source no longer lists any of its snapshot Postings (closed on the company's board), or
- it has no snapshot Posting and its newest windowed Posting is older than the age limit (default 30 days after posting; a setting), or
- an apply-link check (below) finds the job closed.

Windowed Sources cannot see a job disappear, so the age limit is what keeps "ghost jobs" out of the Feed.
- AC1: An Application on an Expired Job keeps working and shows "This job is no longer listed".
- AC2: A Job still listed on a company board stays live past the age limit.
- AC3: When a Draft is created, the Job's apply link is checked if it can be checked for free (not through a credit-based Source); a closed or 404 link marks the Posting closed and warns the User before generation.

**FR-B11 [V1] - Manual refresh (Admin).** The Admin can trigger a Fetch Run for one Source. Rate-limited (default 4 per Source per day); its cost shows in the Credit Budget.

### Epic C - Correspondence (duplicates)

**FR-C1 [V1] - Match Pair scoring.** Each new Posting is compared with Postings from the same normalised Company (and the last 30 days). Signals: same ATS job ID or apply URL, title similarity, description similarity (embeddings with pgvector), and locations. The result is a band: Exact, High, Medium or Low (ADR-0004: two-layer dedup with confidence bands).
- AC1: The same advert reworded on LinkedIn and Greenhouse is placed in High or Exact on a labelled test set.
- AC2: Two different roles at one Company (e.g. "Backend Engineer" and "Data Engineer") are Low.
- AC3: Thresholds are settings and start strict.
- AC4: A Posting without an embedding (Gemini unavailable) is matched only on Exact signals and queued; semantic matching runs when its embedding arrives (ADR-0014: Gemini embeddings, queued when down).

**FR-C2 [V1] - Automatic grouping.** Exact and High pairs join the same Job automatically. The Primary Posting is the one from the highest-priority Source; all other fields are merged.
- AC1: A contact email present only on a lower-priority Posting appears on the Job.
- AC2: The Job's location list is the union of its Postings' locations.

**FR-C3 [V1] - Possible Duplicates.** Medium pairs appear on the Correspondence screen and on both cards as "Possible duplicate" with **Confirm** and **Not the same Job**.
- AC1: Confirm merges the two into one Job; Not the same Job stores a Rejected Pair.
- AC2: A Rejected Pair is never proposed again, including after re-fetches.
- AC3: Confirm and Not the same Job apply for everyone, because Jobs are shared (ADR-0002): a split is a fact about two adverts, not a personal preference. Revisit before a public launch.

**FR-C4 [V1] - Split.** Any grouped Job can be split by marking one Posting "Not the same Job", which stores a Rejected Pair and creates a separate Job.

**FR-C5 [V1] - Multi-location Jobs.** The same advert (same text or same Source job ID) posted for several cities is one Job with location chips. It matches a User's Preferences if any location matches. Different text or job IDs are separate Jobs.

**FR-C6 [V1] - Correspondence view.** For any Job, the User sees the full stack of Postings, with Source, posted date, location and a link to the original, regardless of priority. Feed cards show "Available on" badges for every Source in the stack.
- AC1: Every Posting of a Job is reachable in at most 2 clicks from its Feed card.

### Epic D - Feed

**FR-D1 [V1] - Personal Feed.** Each User's Feed contains the Jobs whose title, locations and work mode match their Preferences, as links to shared Jobs (ADR-0002: Jobs stored once, linked to Users).
- AC1: User A's Preferences never put a Job in User B's Feed; cross-user isolation tests cover every Feed endpoint.

**FR-D2 [V1] - Two sections.** **With email** (the Job has a contact email) and **Apply link only**.

**FR-D3 [V1] - Skill Gaps.** Each card shows the Job's required skills that are missing from the User's Fact Bank: "Missing: Kubernetes, Go", or "No gaps found" (ADR-0010: Skill Gaps, not a match score).
- AC1: Required skills are extracted once per Job; the per-User comparison makes no AI call.
- AC2: Skill aliases are normalised ("Postgres" = "PostgreSQL", "JS" = "JavaScript").

**FR-D4 [V1] - Card contents.** Title, Company, locations, work mode, posted date, Source badges ("Available on"), Skill Gaps, Possible duplicate marker, Application status if any.

**FR-D5 [V1] - "Already applied to this Company".** A card shows a warning when the User has an Application (Applied or later) for another Job at the same Company in the last 90 days.

**FR-D6 [V1] - Sort, filter, search, hide.** Default order newest first. Filters: location, work mode, Source, has email, posted within. Free-text search over title and Company. Hiding a Job removes it from that User's Feed only.

**FR-D7 [V1] - Freshness label.** The Feed shows when it was last updated and which Sources are Degraded.

### Epic E - Draft (the main feature)

**FR-E1 [V1] - Create a Draft.** Any Job in the Feed (with or without email) has a "Create draft" action. Generation starts immediately and shows progress.
- AC1: From a Feed card to a ready Draft in at most 2 clicks.
- AC2: Typical generation completes in under 60 seconds on free AI tiers; progress is shown step by step (reading the job, choosing your experience, writing).

**FR-E2 [V1] - Tailored Resume.** Built from the Fact Bank for this Job: chooses the most relevant Facts (including portfolio-only Facts), rewrites them to match the Job's language and ATS keywords, orders sections and bullets by relevance, and keeps to one or two pages (ADR-0005: Fact Bank, no fabrication).
- AC1: Every bullet has a Tailoring Trace to at least one Fact.
- AC2: A code check, not the AI, rejects any skill or technology named in the output that is not in the Fact Bank; rejected lines are regenerated or removed, and the User is told.
- AC3: On a labelled test set, zero fabricated skills, employers, dates or metrics.

**FR-E3 [V1] - Cover Letter.** A Job-specific cover letter, same Fact Bank rule and trace.

**FR-E4 [V1] - Application Email.** For Jobs with a contact email: subject and short body, written to the hiring contact, same Fact Bank rule. The email body refers to the attached resume.

**FR-E5 [V1] - Diff and Trace.** The Draft screen shows what changed against the Base Resume (added from portfolio, rewritten, reordered, removed) and, for any line, the Fact(s) it came from.

**FR-E6 [V1] - Direct editing.** The User edits any part of the Draft inline. Manual edits are never overwritten by later AI edits without the User's confirmation.

**FR-E7 [V1] - Draft Chat.** A chat panel on the right of the Draft screen. The User asks for changes in plain language; each change is applied as a new Draft version, highlighted, and can be undone.
- AC1: "Lead with the Rails work and shorten the summary" produces a new version with those changes and no new facts.
- AC2: A request that would need a fact not in the Fact Bank ("add Kubernetes") is refused with the reason and an offer to add the skill to the Fact Bank first.

**FR-E8 [V1] - Versions.** Every generation, chat change and manual save is a version; the User can compare and restore versions.

**FR-E9 [V1] - PDF rendering and templates.** The Tailored Resume (and Cover Letter) render to PDF in an ATS-friendly single-column template modelled on the founder's current resume. Choosing or uploading another template is optional per User.
- AC1: The PDF's text is selectable and parses back to the same content (ATS check).
- AC2: The file name follows `<Name>_<Company>_<Title>.pdf`.

**FR-E10 [V1] - Email check.** Before Gmail Hand-off, the recipient is checked: valid format, the domain can receive mail (MX record), and not a no-reply address.
- AC1: A failing check is shown inline in the Draft with what to do; the User can still continue after confirming.

**FR-E11 [V1] - Save draft.** "Save draft" saves only. It is visually and textually distinct from Open in Gmail.

**FR-E12 [V1] - Open in Gmail (Gmail Hand-off).** Creates a Gmail draft with recipient, subject, body and the Tailored Resume PDF attached, then opens it in Gmail (ADR-0006: the User sends from Gmail).
- AC1: Confirmation before creating the Gmail draft names the recipient and the attachment.
- AC2: If the Gmail token has expired, the User is asked to sign in again and the hand-off resumes after sign-in.
- AC3: If the Gmail API fails, the fallback opens a Gmail compose link with fields filled, downloads the PDF, and tells the User to attach it.
- AC4: The Application moves to Drafted on hand-off; the User marks it Applied after sending (one click, also offered when they return).

**FR-E13 [V1] - Apply-link Jobs.** For Jobs without an email: download the Tailored Resume and Cover Letter, open the apply link, and a one-click "Mark as applied".

**FR-E14 [Later] - Browser extension.** A Chrome extension that auto-fills apply-link forms from the Draft.

### Epic F - Applications and Reminders

**FR-F1 [V1] - Application tracker.** A board or list of the User's Applications by status: Drafted -> Applied -> Replied -> Interview -> Offer, or Rejected. The User changes status manually; each change is timestamped.

**FR-F2 [V1] - Follow-up Reminders.** When an Application has stayed Applied for N days (default 7, configurable), an in-app reminder appears with a one-click "Draft a follow-up" (same Draft rules; nothing is sent).

**FR-F3 [V1] - Company history.** For any Company, the User sees all their Applications to it (feeds FR-D5).

**FR-F4 [Later] - Reading replies.** Detect replies in Gmail to update status automatically (needs a further restricted Gmail scope).

**FR-F5 [Later] - Email or push notifications** for new Jobs and reminders.

### Epic G - Security, Privacy and Operations

**FR-G1 [V1] - Tenancy.** Every user-owned table carries `user_id`; every query, cache key and job is scoped by it (ADR-0001: User tenancy from day one). Shared job tables hold only public job-advert data (ADR-0002).
- AC1: Every user-owned endpoint has a cross-user isolation test.

**FR-G2 [V1] - Secrets and credentials.** Gmail tokens and any stored API keys are encrypted at rest; provider keys (Bright Data, Apify, AI providers) live only in environment configuration; secrets never appear in logs.

**FR-G3 [V1] - Document privacy.** Uploaded documents and Facts are visible only to their owner; logs never contain document text, Draft content or email bodies.

**FR-G4 [V1] - AI usage accounting.** Every AI Gateway call records User, task, provider, tokens and outcome, for debugging free-tier limits and for future pricing (ADR-0007: thin AI Gateway with free-provider fallback).
- AC1: The gateway counts requests per provider and model per day against configured free quotas and routes to the next provider before a quota is hit (Gemini Flash is reserved for Draft generation and Draft Chat; high-volume extraction uses Flash-Lite, then Groq).

**FR-G5 [V1] - Health and monitoring.** `GET /health` responds without touching the database (for the keep-warm ping); errors are reported to a free error-tracking tier.

**FR-G6 [Later] - Public launch gate.** Before any public or paid launch: review scraping terms, AI free-tier terms and Gmail verification (ADR-0012: accepted risks for private use).

## 7. Non-Functional Requirements

| Area | Requirement |
|---|---|
| Security | Google sign-in only (no stored passwords); signed HTTP-only session cookies with CSRF protection; tokens and keys encrypted at rest; HTTPS only; open sign-up, limited in practice to Google test users while the OAuth app is in testing mode. |
| Privacy | Documents, Facts and Drafts are user-owned and never shared, logged or used outside that User's requests; each User accepts the AI data notice before any document reaches an AI provider (FR-A5); account deletion removes all user-owned data. |
| Truthfulness | Zero fabricated content in Drafts, enforced by the Fact Bank rule, the code-level skill check and the Tailoring Trace (ADR-0005). |
| Reliability | Any single Source or AI provider failing leaves the product usable; Fetch Runs are idempotent and resume after restarts (ADR-0003, ADR-0008). |
| Cost | $0/month; no payment method on any service; visible budgets and projections for credit- and quota-limited Sources; AI calls minimised by per-Job (not per-User) extraction (COSTS.md). |
| Performance | Feed loads in under 2 s for 2,000 Jobs; Preferences changes reflect in under 1 minute; Draft generation typically under 60 s with visible progress. |
| Freshness | New Postings appear within 24 hours of posting for healthy Sources; Expired Jobs leave the Feed (FR-B10); the Feed always shows when it was last updated. |
| Testability | Recorded AI mode: CI makes zero live AI calls; every Source Adapter tested on recorded fixtures; labelled sets for dedup bands and fabrication checks. |
| Accessibility | WCAG 2.1 AA: keyboard navigation for every action, readable contrast in light and dark mode, screen-reader labels. |
| Portability | 12-factor config, containerised, no hard dependency on one cloud's proprietary services. |
| Maintainability | Layered backend (api -> services -> adapters / gateway / dedup / gmail -> core, no upward imports); typed contracts; frontend types generated from OpenAPI. |

## 8. UX Rules (checkable)

The UI must look professional and the UX must never be confusing. "Not confusing" is defined by these rules; each is a review checklist item.

1. **One main action per screen.** Feed: open a Job. Job: Create draft. Draft: Open in Gmail (or Mark as applied for apply-link Jobs). Secondary actions are visibly secondary.
2. **Two clicks to a Draft** from any Feed card (FR-E1 AC1).
3. **Every slow step shows its status:** fetching, generating, saving, creating Gmail draft; failures say what happened and what to do next, in plain words.
4. **Helpful empty states:** no documents, Fact Bank not reviewed, no Preferences, no Jobs yet, Gmail not connected; each says what to do with one button.
5. **No surprise outward actions:** anything that leaves JobWeaver (Gmail draft) or deletes data asks for confirmation that names the effect.
6. **One name per concept,** taken from `CONTEXT.md`, used identically in the UI, docs and code.
7. **Consistent design system:** Tailwind CSS with one component library (shadcn/ui recommended), light and dark mode, consistent spacing and type scale.
8. **Responsive:** usable on a laptop and a phone; the Draft screen collapses the chat panel into a drawer on small screens.
9. **Draft screen layout:** editor in the centre, Draft Chat on the right, diff and trace one click away without leaving the screen.

## 9. Key User Flows

**Flow A - Onboarding (first 10 minutes).** Sign in with Google -> upload resume and portfolio -> review parsed Facts -> set Preferences -> connect Gmail (or skip) -> Feed. If no Jobs are fetched yet, the Feed shows a Backfill progress state, not an empty page. *Success = the User sees real matching Jobs on first visit or within minutes.*

**Flow B - Daily review.** Open Feed -> scan new Jobs (Skill Gaps, Available on, Already applied warnings) -> hide the irrelevant -> resolve any Possible Duplicates -> pick Jobs to apply to.

**Flow C - Apply by email.** Job card -> Create draft -> review diff and trace -> ask Draft Chat for changes -> Save draft -> Open in Gmail (confirm recipient and attachment) -> edit and send in Gmail -> return -> Mark as applied.

**Flow D - Apply by link.** Job card -> Create draft -> refine -> download PDFs -> open apply link -> Mark as applied.

**Flow E - Duplicate triage.** Possible duplicate marker -> Correspondence view -> compare Postings side by side -> Confirm or Not the same Job.

**Flow F - Source trouble (Admin).** Notice "LinkedIn delayed" -> Source Status shows "budget exhausted until 1 Nov" -> no action needed, or narrow the most expensive queries, or disable the Source.

**Flow G - Follow-up.** Reminder "No update from Acme for 7 days" -> Draft a follow-up -> Open in Gmail -> send.

## 10. Architecture (high level)

```
React + TypeScript SPA (Vite, Tailwind, shadcn/ui, TanStack Query; types generated from OpenAPI)
        |
FastAPI (one web service, also serves the built frontend)
  api/            routes, auth, request validation
  services/       feed, drafts, applications, onboarding, fetch orchestration, budgets
  adapters/       one module per Source, registered by name (ADR-0003)
  dedup/          normalisation, Match Pair scoring, grouping, field merge (ADR-0004)
  gateway/        AI Gateway: task methods, provider fallback, recorded mode (ADR-0007)
  documents/      document parsing into Facts, PDF rendering
  gmail/          OAuth, Gmail draft creation, compose-link fallback (ADR-0006)
  scheduler/      APScheduler jobs: daily Fetch Runs, expiry checks, reminders (ADR-0008)
  core/           config, security, errors, database
        |
Postgres + pgvector (free tier)          External: Sources, AI providers, Gmail API
```

Dependency direction: `api -> services -> (adapters | dedup | gateway | documents | gmail) -> core`. Lower layers never import upward; siblings meet in a service.

**Daily pipeline:** scheduler -> for each enabled Source (isolated) -> windowed: build queries from all Users' Preferences and fetch the window; snapshot: fetch each ATS Board and diff against stored Postings -> normalise to Postings -> store -> embed (queued if the embedding provider is down, ADR-0014) -> score Match Pairs -> group into Jobs and merge fields -> extract required skills for new Jobs -> apply expiry rules -> link Jobs to matching Users' Feeds -> record Fetch Run and credit spend.

### Data model (main tables)

| Table | Owner | Purpose |
|---|---|---|
| `users` | - | Google account id, email, role (User/Admin), AI notice accepted at |
| `oauth_credentials` | user | Encrypted Google/Gmail tokens, expiry |
| `documents` | user | Uploaded files and extracted text |
| `facts` | user | Fact Bank entries with type, text, source document, "in Base Resume" flag |
| `preferences` | user | Titles, keywords, locations, work modes |
| `sources` | shared | Source config, priority, enabled, budget settings |
| `fetch_runs` | shared | Mode, window or board, status, error, counts, credits spent per query |
| `companies` | shared | Normalised Company names and aliases |
| `ats_boards` | shared | Discovered or added ATS Boards (type, slug, last seen) |
| `postings` | shared | Normalised Postings, Source IDs, snapshot/windowed origin, last seen, closed flag, embedding + embedding model name |
| `jobs` | shared | Canonical Jobs, Primary Posting, merged fields, required skills, locations, expired flag |
| `match_pairs` | shared | Posting pairs, band, signals |
| `rejected_pairs` | shared | Pairs marked "Not the same Job"; apply to everyone (FR-C3) |
| `user_jobs` | user | Feed membership, seen, hidden |
| `drafts`, `draft_versions` | user | Draft content per version, PDFs, trace links to `facts` |
| `applications` | user | One per User and Job: status, applied date, when a Follow-up Reminder is due |
| `application_events` | user | Timestamped status history (FR-F1) |
| `gmail_handoffs` | user | Gmail drafts created for an Application or a follow-up |
| `ai_usage` | user | Per-call AI accounting |

## 11. Technology Stack

Per ADR-0011 (Python/FastAPI + React stack).

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2 | AI, scraping, PDF and similarity ecosystem; typed contracts and OpenAPI |
| Frontend | React + TypeScript (Vite), Tailwind CSS, shadcn/ui, TanStack Query | Interactive Draft screen; professional, consistent UI; generated API types |
| Database | PostgreSQL + pgvector (Neon free plan), SQLAlchemy 2, Alembic | One store for relational data and embeddings; tenancy from the first migration |
| Scheduling | APScheduler in-process | Single free service; no separate worker (ADR-0008) |
| AI | AI Gateway over Gemini -> Groq -> OpenRouter; Ollama for local dev | Free tiers with fallback; recorded mode for tests (ADR-0007) |
| Similarity | Gemini embeddings + pgvector (model name stored per vector); rapidfuzz for titles and names | Semantic duplicate detection (ADR-0004, ADR-0014) |
| Documents | A PDF text extractor (e.g. pypdf / pdfplumber); HTML-to-PDF rendering (e.g. WeasyPrint) | Parse uploads; render ATS-friendly PDFs |
| Email checks | email-validator + DNS MX lookup | FR-E10 |
| Auth | Google OAuth only, signed session cookies | FR-A1, ADR-0015 |
| Testing | pytest, Vitest; recorded AI fixtures; recorded Source fixtures | Zero live calls in CI |
| Infra | Docker, GitHub Actions, Render free web service, Neon free Postgres (not Render's free Postgres, deleted after 30 days), UptimeRobot | 12-factor, $0 (ADR-0008) |

## 12. Release Plan (build order)

No dates; each phase ends with something usable. Foundation first, like a full product (founder's order), with Sources split so the main feature (Draft) is reached early.

**Phase 0 - Foundation.** Repo structure, CI (lint, typecheck, tests), docs (this set), Docker setup, deploy skeleton with `/health` and keep-warm ping, AI Gateway skeleton with recorded mode, Source Adapter interface.

**Phase 1 - Accounts and Profile.** FR-A1 to FR-A6: Google sign-in, documents to Fact Bank with review, Preferences, onboarding shell. *Usable: the User's Fact Bank exists and is correct.*

**Phase 2 - First Sources.** FR-B1 to FR-B11 with four Sources that cover both fetch modes and the main supply: LinkedIn (Bright Data), JSearch, Greenhouse and Lever (snapshot), Remotive. Registry, normalisation, Backfill and daily runs, Credit Budget, fallback and Source Status, ATS discovery, expiry. *Usable: Jobs are flowing in every day.*

**Phase 3 - Correspondence and Feed UI.** FR-C1 to FR-C6, FR-D1 to FR-D7: grouping, Possible Duplicates, Correspondence view, the full Feed. *Usable: the User reviews one clean Feed daily.*

**Phase 4 - Draft.** FR-E1 to FR-E13: tailoring with trace and checks, cover letter, email, diff, editing, Draft Chat, versions, PDFs, email check, Gmail Hand-off and fallback. *Usable: end-to-end applications.*

**Phase 5 - Remaining Sources.** Every other Source in FR-B2: Naukri, the other ATS types, SerpApi, Adzuna, the other remote boards, HN extraction, the Indian boards and Foundit. Site-fetch Sources (Instahyre, Cutshort, Hirist, Foundit, Workday) may be blocked from a cloud server's IP address; each is kept only if it works reliably, otherwise disabled with the reason recorded. *Usable: full coverage.*

**Phase 6 - Applications and polish.** FR-F1 to FR-F3, FR-G4 to FR-G5, accessibility and UX-rule review, performance pass. *Usable: V1 complete.*

**Later:** browser extension (FR-E14), email and password sign-in (FR-A7), reply reading (FR-F4), notifications (FR-F5), public launch gate (FR-G6), paid plans.

## 13. Success Metrics *(decided)*

| Metric | Target for V1 |
|---|---|
| Time from Job card to Gmail draft (User time) | Median under 5 minutes |
| Applications sent per active User per week | Tracked; no fixed target |
| Reply rate (Replied or later / Applied) | Tracked from the Application tracker; compare with the User's pre-JobWeaver rate |
| Fabricated content in Drafts | 0 incidents (code check plus User reports) |
| Duplicate accuracy | Fewer than 5% of automatic groups split by Users; Possible Duplicates under 10% of new Jobs |
| Source health | 90%+ of daily Fetch Runs healthy per Source per month (excluding budget exhaustion) |
| Budget visibility | Every LinkedIn budget exhaustion was predicted by the projection at least 5 days ahead |
| Cost | $0 every month |

## 14. Risks

| Risk | Mitigation |
|---|---|
| A Source changes its format or blocks access | Isolated adapters, Degraded state, fixture tests that catch format changes; other Sources keep the Feed alive (ADR-0003) |
| Free tiers change or shrink | Fallback chains for Sources and AI; budget projections; `COSTS.md` review triggers |
| AI fabricates content | Fact Bank-only generation, code-level skill check, Tailoring Trace, User review before anything leaves (ADR-0005, ADR-0006) |
| Wrong duplicate merge hides a Job | Strict thresholds, Medium band asks the User, split action, every Posting stays reachable (ADR-0004) |
| Gmail token expiry interrupts applying | Expiry detected ahead of time, re-login reminder, compose-link fallback (ADR-0006) |
| Free host sleeps and misses a daily run | Keep-warm ping, external cron fallback, watermark-based catch-up (FR-B3, ADR-0008) |
| Embedding provider down | Postings still appear (Exact matching by ATS ID or URL still runs); semantic grouping is queued until embeddings return (ADR-0014) |
| Site-fetch Sources blocked from cloud IPs | Built last (Phase 5); disabled with the reason if unreliable; the other Sources cover the market |
| Ghost jobs that are no longer open | Snapshot comparison, 30-day age limit, apply-link check before drafting (FR-B10) |
| LinkedIn credits run out before renewal | Full-scope fetching is the founder's choice; month-end projection and per-query spend let the Admin narrow queries; other Sources keep the Feed alive; founder-only use in month 1 (ADR-0009) |
| Terms-of-service action by LinkedIn or Naukri | Accepted for private use; pre-launch review required (ADR-0012) |
| Scope creep for a solo builder | [V1] / [Later] tags are the scope; new ideas go to Later unless they replace something |

## 15. Open Questions

None for the product. Facts were checked on 5 Oct 2026 (details and figures in `COSTS.md`):
- **Confirmed:** `gmail.compose` is restricted; testing-mode tokens expire 7 days after consent; testing mode allows up to 100 test users (ADR-0006). Bright Data supports "Past 24 hours", "Past week" and "Past month" (ADR-0009). Gemini's free tier may use prompts to improve Google products, and serving users in the EEA, Switzerland or the UK requires paid services (ADR-0012). Render's free Postgres expires after 30 days, so the database is Neon's free plan, which never expires (ADR-0008).
- **Changed the design:** Gemini Flash's free tier allows only about 20 requests a day, so the AI Gateway routes high-volume work to Flash-Lite and Groq (FR-G4). JSearch (200/month) and SerpApi (250/month) run out early in a month under full scope; accepted and visible.
- **Still unconfirmed (check in each dashboard while building):** the full list of Bright Data time ranges, per-ATS rate limits, access to Instahyre, Cutshort, Hirist, Foundit and Workday, remote-board terms, exact Gemini quotas for the project, UptimeRobot and error-tracking free tiers, and whether a local embedding model fits in 512 MB (not pursued, ADR-0014).

---
*Capitalised domain terms are defined in [`CONTEXT.md`](./CONTEXT.md). Design rationale lives in [`docs/adr/`](./docs/adr/): this PRD states the what; the ADRs defend the why.*
