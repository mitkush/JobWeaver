# JobWeaver - Costs

**Budget:** $0 per month during a one-month trial; after the trial the founder plans to pay for services where free tiers fall short (each upgrade is a configuration change, recorded here). All Users share the founder's keys; there are no per-user keys. **Rule:** no payment method is attached to any service, so no service can bill beyond its free tier (ADR-0008).
**What happens at a limit:** the affected Source or provider fails cleanly, is marked Degraded, and the rest of the system keeps working (ADR-0003, ADR-0007).

**How these numbers were checked:** web search on 5 Oct 2026. The providers' own documentation pages could not be opened from the build environment, so most figures come from current secondary sources that agree with each other. Free tiers change often: confirm each figure in the provider's dashboard when creating the account, and update this file. Items still marked *(unconfirmed)* could not be checked.

---

## 1. Job Sources

| # | Source | Access | Free allowance (checked 5 Oct 2026) | When it runs out |
|---|---|---|---|---|
| 1 | LinkedIn | Bright Data "Discover jobs by keyword" | **5,000 credits/month, 1 credit = 1 record** (founder's account). Up to 1,000 Postings per keyword call. Time ranges seen in use: "Past 24 hours", "Past week", "Past month" | Full scope, no caps; projection warns first (ADR-0009). At zero: Degraded until renewal; month 1 is founder-only |
| 1b | LinkedIn (alternative) | Apify actor | **$5 of platform usage per month**, permanent, no card; runs pause when it is used up | Degraded until renewal |
| 2 | Naukri | Apify actor | Shares the same $5/month Apify credit | Degraded until renewal |
| 3 | Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee | Public job-board APIs, per company (snapshot mode) | Free, no key; keep request rates polite *(per-ATS limits unconfirmed)* | Per-board retry next run |
| 3b | Workday | No public API; best-effort page fetch | Free | Often Degraded; kept only if reliable |
| 4 | Instahyre, Cutshort, Hirist | Site fetch *(access method unconfirmed)* | Free | May be blocked from cloud IPs; built last |
| 5 | JSearch | RapidAPI (OpenWeb Ninja) | **200 requests/month**, 1,000/hour, no card | Degraded until renewal |
| 6 | SerpApi Google Jobs | SerpApi | **250 searches/month**, 50/hour (older sources say 100; confirm in dashboard) | Degraded until renewal |
| 7 | Adzuna | Adzuna API key | **25/minute, 250/day, 1,000/week, 2,500/month** | Degraded, retry next run |
| 8 | Remotive, Remote OK, We Work Remotely, Himalayas, Jobicy, Working Nomads | Public APIs / RSS | Free *(terms and attribution rules unconfirmed per board)* | Degraded, retry next run |
| 9 | Hacker News "Who is hiring" | Public HN API + AI extraction | Free; costs AI calls (see 2) | Extraction queued until AI quota returns |
| 10 | Foundit | Site fetch *(access method unconfirmed)* | Free | May be blocked from cloud IPs; built last |

**What these quotas mean in practice:** JSearch (200/month) and SerpApi (250/month) allow only about 6 to 8 calls a day. With several (title, location) searches per day they run out early in the month under the full-scope rule; that is accepted (Degraded until renewal) and visible on Source Status. Adzuna (250/day) and the free APIs carry daily volume.

## 2. AI providers (ADR-0007)

| Order | Provider | Used for | Free allowance (checked 5 Oct 2026) | When it runs out |
|---|---|---|---|---|
| 1 | Google Gemini | Flash-Lite: high-volume extraction (skills per Job, HN, document parsing). Flash: tailoring and Draft Chat. Embeddings: duplicate detection, the **only** embedding provider (ADR-0014) | Limits are per model and shown per project in Google AI Studio, not in a public table. Reported: newest Flash models about **20 requests/day**; Flash-Lite **500 to 1,000 requests/day** (about 15/minute); embedding models free. Free-tier prompts may be used to improve Google products | Text tasks fall through to Groq; embeddings queue until Gemini returns (ADR-0014) |
| 2 | Groq | All text tasks | About **1,000 requests/day** and 30/minute per model on popular open models (lower token caps per minute and day); limits are per organization, extra keys do not help. No embeddings | Falls through to OpenRouter |
| 3 | OpenRouter `:free` models | All text tasks | **50 requests/day**, 20/minute (1,000/day only after a one-time $10 credit purchase, excluded by the zero budget). No embeddings used | Task queued and retried; the User sees "AI busy, retrying" |
| dev | Ollama (local) | Local development only | Unlimited on the developer's machine | Not used in production |

**Daily AI budget (design consequence):** the strongest free model (Gemini Flash) allows only about 20 requests a day, so it is reserved for Draft generation and Draft Chat. Everything high-volume runs on Flash-Lite first, with Groq as the bulk fallback. The AI Gateway tracks requests per provider and model per day and routes before a quota is hit, not after (FR-G4).

**Keeping AI usage low by design:**
- Required skills are extracted **once per Job**, not per User (ADR-0010).
- Embeddings are computed **once per Posting** and stored.
- Tailoring sends only the relevant Facts plus the Job description, never every document in full.
- Tests and CI use recorded responses: **0 live AI calls** during development.

## 3. Platform

| Item | Choice | Free allowance (checked 5 Oct 2026) | Notes |
|---|---|---|---|
| Web service (API + frontend) | **Render** free web service | **512 MB RAM, 0.1 CPU, 750 instance hours/month** per workspace (enough for one service running all month); spins down after **15 minutes** without traffic | Kept warm by UptimeRobot (ADR-0008) |
| Database | **Neon** free plan (Postgres + pgvector) | **1 GB storage per project** (raised from 0.5 GB on 1 Oct 2026), 100 compute-hours/month, scales to zero after 5 minutes idle, **never expires**, no card | **Not Render's free Postgres: it becomes inaccessible after 30 days and is deleted on day 44.** `/health` does not touch the database, so Neon can sleep between jobs and stay within compute hours |
| Uptime ping | UptimeRobot | Free monitors at 5-minute intervals *(unconfirmed)* | Also gives free uptime alerts |
| Scheduler | APScheduler in-process | Free | Fallback: free external cron calling a protected endpoint |
| Google OAuth (the only sign-in, plus Gmail) | Google Cloud project, testing mode, External user type | Free; **up to 100 test users**; Google shows an "unverified app" warning to test users | **Refresh tokens and consents expire 7 days after consent** for Gmail scopes; re-login reminder (ADR-0006) |
| Gmail API | `gmail.compose` | Free | **Restricted** scope: a public launch needs Google verification plus an annual third-party security assessment (CASA). `gmail.send` is only "sensitive" (no assessment) but cannot create drafts (ADR-0006, ADR-0012) |
| Error tracking | A free error-tracking tier (e.g. Sentry developer plan) *(unconfirmed)* | Limited events/month | Optional |
| Code and CI | GitHub + GitHub Actions | Free for public repos; monthly minutes for private *(unconfirmed)* | Recorded AI mode keeps CI at $0 |
| Domain | Host-provided subdomain | Free | A custom domain is a cost and is out of V1 |

**Storage estimate for Neon's 1 GB:** a Posting with description is a few KB, and a 768-dimension embedding is about 3 KB. Around 100,000 Postings fit with room for user data. Old Expired Jobs without Applications are pruned after 90 days. *(Gemini embeddings support a reduced output size such as 768 dimensions; unconfirmed, check when building.)*

## 4. Development tooling

Claude Code usage for building JobWeaver comes from the founder's own plan and is outside the product budget.

## 5. Review triggers

Revisit this file when:
- the one-month trial ends: decide which services move to paid tiers. A paid Gemini tier also removes the free-tier prompt-use concern (ADR-0012), and is required before serving any User in the EEA, Switzerland or the UK,
- any Source is Degraded for limit reasons more than 3 times in a month,
- the AI Gateway falls back past Gemini on most days,
- the User count grows beyond the founder's private group, or
- before any public or paid launch (ADR-0012).
