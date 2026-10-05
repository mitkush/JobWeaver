# JobWeaver - Costs

**Budget:** $0 per month, permanently for V1. **Rule:** no payment method is attached to any service, so no service can bill beyond its free tier (ADR-0008).
**What happens at a limit:** the affected Source or provider fails cleanly, is marked Degraded, and the rest of the system keeps working (ADR-0003, ADR-0007).

Limits marked *(verify)* are from general knowledge and change often. Confirm each one in the provider's dashboard when creating the account and update this file. Limits without the mark were confirmed by the founder.

---

## 1. Job Sources

| # | Source | Access | Free allowance | When it runs out |
|---|---|---|---|---|
| 1 | LinkedIn | Bright Data scraper | **5,000 credits/month, 1 credit = 1 record**; renews monthly | Full scope: every result fetched, no caps; projection warns before it runs out (ADR-0009). At zero: Degraded until renewal; month 1 is founder-only |
| 1b | LinkedIn (alternative) | Apify actor | Monthly free platform credit *(verify amount)* | Degraded until renewal |
| 2 | Naukri | Apify actor | Shares the Apify monthly credit *(verify)* | Degraded until renewal |
| 3 | Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee | Public job-board APIs, per company | Free, no key *(verify per ATS)*; be polite with request rates | Per-board retry next run |
| 3b | Workday | No public API; best-effort page fetch | Free | Best-effort; often Degraded |
| 4 | Instahyre, Cutshort, Hirist | Site fetch / available APIs *(verify per site)* | Free | Degraded, retry next run |
| 5 | JSearch | RapidAPI | Small monthly free request quota *(verify)* | Degraded until renewal |
| 6 | SerpApi Google Jobs | SerpApi | Small monthly free search quota *(verify)* | Degraded until renewal |
| 7 | Adzuna | Adzuna API key | Free developer quota *(verify)* | Degraded, retry next run |
| 8 | Remotive, Remote OK, We Work Remotely, Himalayas, Jobicy, Working Nomads | Public APIs / RSS | Free *(verify terms and attribution rules)* | Degraded, retry next run |
| 9 | Hacker News "Who is hiring" | Public HN API + AI extraction | Free; costs AI calls (see 2) | Extraction queued until AI quota returns |
| 10 | Foundit | Site fetch *(verify)* | Free | Degraded, retry next run |

Request-quota Sources (JSearch, SerpApi, Adzuna) follow the same rule as LinkedIn: no hidden caps; spend and a month-end projection are shown, and a Source that runs out is Degraded until renewal.

## 2. AI providers (ADR-0007)

| Order | Provider | Used for | Free allowance | When it runs out |
|---|---|---|---|---|
| 1 | Google Gemini (Flash / Flash-Lite, embeddings) | All tasks; the **only** embedding provider (ADR-0014) | Per-model limits per minute and per day *(verify)*; free-tier prompts may be used by Google (ADR-0012) | Text tasks fall through to Groq; embeddings are queued until Gemini returns (ADR-0014) |
| 2 | Groq (open models, e.g. Llama, Qwen) | All text tasks | Per-model limits *(verify)* | Falls through to OpenRouter |
| 3 | OpenRouter `:free` models | All text tasks | 50 requests/day without a credit purchase; models can be overloaded or removed | Task queued and retried; the User sees "AI busy, retrying" |
| dev | Ollama (local) | Local development only | Unlimited on the developer's machine | Not used in production |

**Keeping AI usage low by design:**
- Required skills are extracted **once per Job**, not per User (ADR-0010).
- Embeddings are computed **once per Posting** and stored.
- Tailoring sends only the relevant Facts plus the Job description, never every document in full.
- Tests and CI use recorded responses: **0 live AI calls** during development.

## 3. Platform

| Item | Choice | Free allowance | Notes |
|---|---|---|---|
| Web service (API + frontend) | Render or Railway free tier | Render: one always-on service fits the monthly free hours; sleeps after ~15 min idle *(verify)* | Kept warm by UptimeRobot (ADR-0008) |
| Database | Free Postgres with pgvector (e.g. Neon or Supabase) | Small storage quota *(verify)*; some free databases pause when idle or expire after a period *(verify)* | Pick one whose free tier does not expire; daily Fetch Runs keep it active |
| Uptime ping | UptimeRobot | Free monitors at 5-minute intervals | Also gives free uptime alerts |
| Scheduler | APScheduler in-process | Free | Fallback: free external cron calling a protected endpoint |
| Google OAuth (the only sign-in, plus Gmail) | Google Cloud project, testing mode | Free; up to 100 named test users | Refresh tokens expire about every 7 days *(verify)*; re-login reminder (ADR-0006) |
| Gmail API | `gmail.compose` | Free; generous per-user quota | Restricted scope; public launch needs verification (ADR-0012) |
| Error tracking | A free error-tracking tier (e.g. Sentry developer plan) *(verify)* | Limited events/month | Optional |
| Code and CI | GitHub + GitHub Actions | Free for public repos; monthly minutes for private *(verify)* | Recorded AI mode keeps CI at $0 |
| Domain | Host-provided subdomain | Free | A custom domain is a cost and is out of V1 |

## 4. Development tooling

Claude Code usage for building JobWeaver comes from the founder's own plan and is outside the product budget.

## 5. Review triggers

Revisit this file when:
- any Source is Degraded for limit reasons more than 3 times in a month,
- the AI Gateway falls back past Gemini on most days,
- the User count grows beyond the founder's private group, or
- before any public or paid launch (ADR-0012).
