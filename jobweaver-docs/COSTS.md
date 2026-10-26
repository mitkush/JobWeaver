# JobWeaver - Costs

**Budget:** $0 per month during a one-month trial; after the trial the founder plans to pay for services where free tiers fall short (each upgrade is a configuration change, recorded here). All Users share the founder's keys; there are no per-user keys. **Rule:** no payment method is attached to any service, so no service can bill beyond its free tier (ADR-0008).
**What happens at a limit:** the affected Source or provider fails cleanly, is marked Degraded, and the rest of the system keeps working (ADR-0003, ADR-0007).

**How these numbers were checked:** web search on 5 Oct 2026. The providers' own documentation pages could not be opened from the build environment, so most figures come from current secondary sources that agree with each other. Free tiers change often: confirm each figure in the provider's dashboard when creating the account, and update this file. Items still marked *(unconfirmed)* could not be checked.

---

## 1. Job Sources

| # | Source | Access | Free allowance (checked 5 Oct 2026) | When it runs out |
|---|---|---|---|---|
| 1 | LinkedIn | Bright Data "Discover jobs by keyword" | **5,000 credits/month, 1 credit = 1 record** (founder's account). Up to 1,000 Postings per keyword call. Time ranges seen in use: "Past 24 hours", "Past week", "Past month" | Full scope, no caps; projection warns first (ADR-0009). With discovery keywords, one OR search per Preference country, each up to `BRIGHTDATA_LIMIT_PER_SEARCH` records (default 1,000): about 30,000 credits a month per country at the cap, so about six active 5,000-credit accounts. At zero: Degraded until renewal; month 1 is founder-only |
| 1b | LinkedIn (Apify), Standby for row 1 | Apify actor `curious_coder~linkedin-jobs-scraper` *(unconfirmed: actor choice and fields)* | **$5 of platform usage per month**, permanent, no card; shared with Naukri. Runs only while row 1 is Degraded or off (ADR-0016). Uses the first configured account with a verified balance of at least $0.50; each run is capped at that account's remaining credits | Degraded until renewal |
| 1c | LinkedIn (Piloterr) | Piloterr LinkedIn Job Search API, opt-in third fallback after Bright Data and Apify; lower Posting priority | **500-credit local monthly cap**, one credit per successful page. Provider allowance and renewal are account-specific; verify in Piloterr before enabling. Pages stop at the remaining local cap. Results without descriptions are skipped | Degraded at local cap or provider quota |
| 1d | LinkedIn (Scrapingdog), opt-in fourth fallback | [Jobs search](https://www.scrapingdog.com/documentation/scrape-jobs-search-results/) plus [job details](https://www.scrapingdog.com/documentation/scrape-job-overview/) | Signup account reported 100 credits on 23 Oct 2026; social rewards depend on the account. Each successful page costs 5 credits and each full job detail another 5. A 10-job page with descriptions costs 55; existing active LinkedIn IDs with usable descriptions skip the detail purchase. Local safety ceiling defaults to 100 per calendar month (`SCRAPINGDOG_MONTHLY_CREDITS`); each search also reads account-wide `requestLimit - requestUsed` through the Account API | Stops at the tighter of provider balance and local ceiling. Capped runs save partial postings and fail visibly so the next fallback can retry the window; provider signup/bonus credits are not assumed to renew monthly |
| 1e | LinkedIn (JobSpy), opt-in final fallback | Self-hosted [python-jobspy](https://github.com/speedyapply/JobSpy), pinned 1.4.1 | No API credits; uses the VM CPU/RAM and public LinkedIn requests. Optional proxies have their own costs. Optional `[jobspy]` extra, absent from the default production image. pandas loads only in a short-lived child process; searches default to 50 results in checkpointed 25-result batches | Blocking, missing details, caps and timeouts preserve completed checkpoints as incomplete results; the Source fails visibly without advancing its watermark |
| 2 | Naukri | Apify actor `muhammetakkurtt~naukri-job-scraper` *(unconfirmed: actor choice and fields)* | Shares the same $5/month Apify credit; India searches only; uses the same first-usable-account rule as LinkedIn (Apify) | Degraded until renewal |
| 3 | Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee | Public job-board APIs, per company (snapshot mode) | Free, no key; keep request rates polite *(per-ATS limits unconfirmed)* | Per-board retry next run |
| 3b | Workday | JSON behind career pages (`/wday/cxs/...`), not a published API; 20 jobs per page, about 2,000 listed per company | Free | **Off by default** (Admin turns it on). Past the listing cap nothing is closed from a partial list |
| 4 | Instahyre, Cutshort, Hirist | Instahyre: JSON behind its search *(unconfirmed)*. Cutshort, Hirist: **not built**, no usable endpoint known | Free | Instahyre **off by default** (no dates or full descriptions). Cutshort and Hirist disabled for that reason |
| 5 | JSearch | RapidAPI (OpenWeb Ninja) | **200 requests/month**, 1,000/hour, no card | Degraded until renewal |
| 6 | SerpApi Google Jobs, Standby for row 5 | SerpApi | **250 searches/month**, 50/hour (older sources say 100; confirm in dashboard). 1 search per results page of up to 10 jobs; runs only while JSearch is Degraded or off (ADR-0016) | Degraded until renewal |
| 7 | Adzuna | Adzuna API key | **25/minute, 250/day, 1,000/week, 2,500/month** | Degraded, retry next run |
| 8 | Remotive, Remote OK, We Work Remotely, Himalayas, Jobicy, Working Nomads | Public APIs / RSS | Free *(terms and attribution rules unconfirmed per board)* | Degraded, retry next run |
| 9 | Hacker News "Who is hiring" | Public HN API + AI extraction | Free; costs AI calls (see 2) | Extraction queued until AI quota returns |
| 10 | Foundit | JSON behind its search *(unconfirmed)* | Free | **Off by default**; an Admin turns it on after a successful manual run |

**Phase 5 build note (6 Oct 2026):** the build environment could not reach any of these providers. Response formats come from documentation summaries and other projects' code, and are checked only against test payloads. Confirm each Source's first real run under Recent runs. Terms noted while building: Remote OK and Jobicy ask for a link back to their job page (used as the apply link), Jobicy asks for at most one sync an hour, and Adzuna's descriptions are snippets of about 500 characters.

**What these quotas mean in practice:** JSearch (200/month) and SerpApi (250/month) allow only about 6 to 8 calls a day. With several (title, location) searches per day they run out early in the month under the full-scope rule; that is accepted (Degraded until renewal) and visible on Source Status. Adzuna (250/day) and the free APIs carry daily volume.

## 2. AI providers (ADR-0007)

| Order | Provider | Used for | Free allowance (checked 5 Oct 2026) | When it runs out |
|---|---|---|---|---|
| Personal, opt-in first | Official Claude Code CLI | Owner-only background Draft generation; current free routes stay as fallback | Uses the owner's existing subscription and its shared limits, not API credits. Requires recorded owner consent. Isolated worker capped at 256 MiB and 0.5 CPU, one invocation at a time; binary version 2.1.308. No invented daily quota or subscription-dollar balance | Authentication, quota, busy, invalid output and deadline failures fall back. Disabled by default; no other User can consume this credential |
| 1 | Google Gemini | Flash-Lite: high-volume extraction (skills per Job, HN, document parsing). Flash: tailoring and Draft Chat. Embeddings: duplicate detection, the **only** embedding provider (ADR-0014) | Limits are per model and shown per project in Google AI Studio, not in a public table. Reported: newest Flash models about **20 requests/day**; Flash-Lite **500 to 1,000 requests/day** (about 15/minute); embedding models free. Free-tier prompts may be used to improve Google products | Text tasks fall through to Groq; embeddings queue until Gemini returns (ADR-0014) |
| 2 | Groq | All text tasks | About **1,000 requests/day** and 30/minute per model on popular open models (lower token caps per minute and day); limits are per organization, extra keys do not help. `openai/gpt-oss-120b` allows **8,000 tokens per minute**, and Groq counts the prompt plus the requested output ceiling against it before running a request (HTTP 413 if over). The gateway lowers the output ceiling to fit and skips Groq when a prompt is too large for any useful reply (`TOKENS_PER_MINUTE` in `routing.py`). No embeddings | Falls through to OpenRouter |
| 3 | OpenRouter `:free` models (currently `google/gemma-4-31b-it:free`) | All text tasks | **50 requests/day**, 20/minute (1,000/day only after a one-time $10 credit purchase, excluded by the zero budget). No embeddings used. Free models are withdrawn without notice (`openai/gpt-oss-20b:free` returned HTTP 404 on 7 Oct 2026); the logs then show `openrouter returned HTTP 404` and the model in `routing.py` must be replaced | Task queued and retried; the User sees "AI busy, retrying" |
| 4 | Mistral `mistral-small-latest` | Optional fallback for all text tasks | Free mode has account-specific included usage and rate limits; check Mistral Studio. JobWeaver applies a **50-call/day safety cap**. Mistral says Free-mode inputs and outputs may be used to train its models | Skipped after the app cap or when provider returns a limit error; task falls through or queues |
| dev | Ollama (local) | Local development only | Unlimited on the developer's machine | Not used in production |

A provider that answers HTTP 503 ("high demand", common on Gemini's free models) is retried once after 2 seconds before the next provider is tried.

**Draft request budgets (26 Oct 2026):** background generation allows Gemini 45 seconds
and each subsequent text provider 30 seconds (135 seconds for all four configured routes),
inside a 150-second generation phase. Page Description requirements extraction retains its
separate 90-second phase; these are not a 150-second end-to-end deadline. Draft Chat remains
synchronous with 20 seconds per provider and 90 seconds overall. Busy retries share their
route's deadline. Parsing and other extraction routes keep their existing 90-second limits.

Draft prompts target at most 24,000 serialized user-message characters, selecting whole
Fact groups by job relevance. Employment, education, contact/link Facts and all Facts cited
by an existing Draft (with their groups) are protected. Fact IDs/references and manual text
are unchanged, and the full Fact snapshot remains available to validation and saved versions.
For Groq, the input is reduced further to leave at least 3,072 estimated output tokens plus
256 tokens of framing within its 8,000 TPM allowance. If protected evidence cannot fit, skip
Groq. The 24,000-character target is soft for providers without this TPM cap: protected
context that exceeds it uses the original prompt rather than disabling a previously usable
route. These are conservative character estimates, not exact token counts or guarantees of
complete output; existing response validation and fallback still apply. Quota exhaustion is
not fixed by smaller prompts or longer timeouts.

**Daily AI budget (design consequence):** the strongest free model (Gemini Flash) allows only about 20 requests a day, so it is reserved for Draft generation and Draft Chat. Everything high-volume runs on Flash-Lite first, with Groq as the bulk fallback. The AI Gateway tracks requests per provider and model per day and routes before a quota is hit, not after (FR-G4).

**Keeping AI usage low by design:**
- Required skills are extracted **once per Job**, not per User (ADR-0010).
- Embeddings are computed **at most once per Posting**, and only for Postings that have a close-titled rival at the same Company (a Posting with no possible duplicate is never embedded). Batches of 20 are paced about 20 seconds apart; the gateway stops at 900 embedding requests a day *(Gemini's embedding limits are not in a public table; confirm in AI Studio)*.
- Required skills are extracted only for Jobs that are in at least one User's Feed, five adverts per request.
- Tailoring sends only the relevant Facts plus the Job description, never every document in full.
- Tests and CI use recorded responses: **0 live AI calls** during development.

A short checked Draft backed by substantial work Facts may make one additional tailoring
call to develop the relevant evidence. That call uses the same gateway routing, consent,
quotas and usage accounting, and shares the existing generation deadline. It can consume
additional provider quota and time. Sparse Fact Banks and already developed resumes skip
it; failure preserves the first usable package. Draft Chat does not run this pass.

## 3. Platform

| Item | Choice | Free allowance (checked 5 Oct 2026) | Notes |
|---|---|---|---|
| Web service (API + frontend) | **Render** free web service | **512 MB RAM, 0.1 CPU, 750 instance hours/month** per workspace (enough for one service running all month); spins down after **15 minutes** without traffic | Kept warm by UptimeRobot (ADR-0008) |
| Database | **Neon** free plan (Postgres + pgvector) | **1 GB storage per project** (raised from 0.5 GB on 1 Oct 2026), 100 compute-hours/month, scales to zero after 5 minutes idle, **never expires**, no card | **Not Render's free Postgres: it becomes inaccessible after 30 days and is deleted on day 44.** `/health` does not touch the database, so Neon can sleep between jobs and stay within compute hours |
| Uptime ping | UptimeRobot | Free monitors at 5-minute intervals *(unconfirmed)* | Also gives free uptime alerts |
| Scheduler | APScheduler in-process | Free | Fallback: free external cron calling a protected endpoint |
| Google OAuth (the only sign-in, plus Gmail) | Google Cloud project, testing mode, External user type | Free; **up to 100 test users**; Google shows an "unverified app" warning to test users | **Refresh tokens and consents expire 7 days after consent** for Gmail scopes; re-login reminder (ADR-0006) |
| Gmail API | `gmail.compose` | Free | **Restricted** scope: a public launch needs Google verification plus an annual third-party security assessment (CASA). `gmail.send` is only "sensitive" (no assessment) but cannot create drafts (ADR-0006, ADR-0012) |
| Error tracking | Sentry developer plan, set with `SENTRY_DSN` *(event allowance unconfirmed)* | Limited events/month; errors only, no performance tracing | Optional; off without a DSN. Reports are scrubbed of request bodies, cookies, headers and local variables (FR-G3) |
| Code and CI | GitHub + GitHub Actions | Free for public repos; monthly minutes for private *(unconfirmed)* | Recorded AI mode keeps CI at $0 |
| Domain | Host-provided subdomain | Free | A custom domain is a cost and is out of V1 |

**Storage estimate for Neon's 1 GB:** a Posting with description is a few KB, and a 768-dimension embedding is about 3 KB. Around 100,000 Postings fit with room for user data. Old Expired Jobs without Applications are pruned after 90 days. *(Gemini embeddings support a reduced output size such as 768 dimensions; unconfirmed, check when building.)*

**Neon network transfer is a separate limit:** the Free project has a 5 GB monthly outbound transfer allowance. Each description read by the Oracle app counts again even when the database stores only one copy. On 9 Oct 2026, the JobWeaver database used about 54 MB of storage but Neon warned that its 5 GB transfer allowance was exhausted. Feed matching now asks PostgreSQL for descriptions that may contain a User's Core keyword, plus short adverts that need review; Job metadata refresh no longer reads descriptions. This lowers one repeat-read path, but it does not prove the entire 5 GB spike came from that path. Monitor the project's data-transfer graph in Neon after deployment. The HTTP `/health` check does not access Neon, so use a database-backed request or a small SQL query when diagnosing suspension.

## 4. Development tooling

Claude Code usage for building JobWeaver comes from the founder's own plan and is outside the product budget. The optional personal Draft route also uses that owner's plan and shares its limits with other Claude use. It does not enable API billing or subscription access for other Users. See [Personal Claude](PERSONAL_CLAUDE.md) for measured resource costs, explicit consent and deployment.

## 5. Review triggers

Revisit this file when:
- the one-month trial ends: decide which services move to paid tiers. A paid Gemini tier also removes the free-tier prompt-use concern (ADR-0012), and is required before serving any User in the EEA, Switzerland or the UK,
- any Source is Degraded for limit reasons more than 3 times in a month,
- the AI Gateway falls back past Gemini on most days,
- the User count grows beyond the founder's private group, or
- before any public or paid launch (ADR-0012).

### Account balances versus tracked usage (8 Oct 2026)

JobWeaver's `FetchRun.credits_used` ledger only counts its own recorded searches. It misses outside activity and some provider charges after failed responses, so it is not an account balance.

Apify's [private user data](https://docs.apify.com/api/v2/users-me-get) supplies included plan credits; [account limits](https://docs.apify.com/api/v2/users-me-limits-get) supplies current usage, the spending limit and the actual usage cycle. The Sources page shows account-wide usage and remaining included credits separately from local query costs. Fetches read the account again before starting each paid search, cap actor charges at the remaining included credits or spending limit, and pause if the account cannot be verified. Balances may lag recent provider charges. Nothing here enables spending above included credits.

Bright Data's [balance API documentation](https://docs.brightdata.com/api-reference/account-management-api/Get_total_balance_through_API#is-there-an-api-endpoint-for-free-tier-credit-status) explicitly states that no Account Management API returns the free-tier credit balance. Its USD balance is not the 5,000-credit pool. The Sources page labels local usage as an estimate and directs the admin to the Free credits card. Bright Data credential selection relies on provider limit errors instead of a local allowance guard; recorded usage remains an estimate, not a balance.

The cache is scoped to a credential fingerprint and never stores raw tokens or exposes account identity. Updating credentials does not delete jobs, search watermarks or historical spend. Credential fallback adds migration `0009`: an optional fingerprint on FetchRun for per-credential cost accounting. Legacy unlabelled runs count against the primary account only.

### Retaining primary and backup accounts

Keep `APIFY_TOKEN` as the original primary credential. Bright Data accepts an ordered comma-separated list in `BRIGHTDATA_API_KEY`, or a primary key plus `BRIGHTDATA_API_KEYS` backups in the VM's `backend/.env`:

```dotenv
APIFY_TOKENS=backup-apify-token,another-backup-token
BRIGHTDATA_API_KEY=first-brightdata-key,second-brightdata-key,third-brightdata-key
# Alternatively: BRIGHTDATA_API_KEY=first-brightdata-key
# BRIGHTDATA_API_KEYS=second-brightdata-key,third-brightdata-key
```

These are accounts with their own allowances, not extra keys for the same account. Never commit real values. Changing an environment file takes effect when the container is recreated.

Before each search, Apify checks accounts in configured order and selects the first account with a verified balance of at least $0.50. Accounts with unavailable balances, exhausted credits, or less than $0.50 are skipped; searches pause only when no configured account can be verified with enough credit. The Sources page uses the same rule to label the account selected for a search and lists each account's balance. A renewed primary is selected again when it is the first configured account meeting the minimum. Both Apify Sources use the same credential order and shared account balances. The $0.50 floor is a conservative guard based on an observed actor run aborting at a $0.25 cap; it reduces retries caused by tiny balances but does not guarantee every search will fit within that amount.

Bright Data tries configured credentials in order, trimming whitespace and ignoring empty or duplicate keys. It switches only when a trigger request rejects the search for explicit credit/quota exhaustion or HTTP 429 before returning a snapshot id. Bright Data also switches on the exact case-insensitive `Customer is not active` message on HTTP 400 or 403 from the trigger request. This is an inactive account, not a quota diagnosis; other HTTP 400 responses keep the normal failure path. A temporary HTTP 429 is retried once on the same key after three seconds before switching. Credential selection does not query balances, consult local usage totals, or track renewal times. Rejected credentials are skipped for the remainder of that Source run and tried again on the next run. If every credential is rejected, the Source becomes Degraded and its existing Standby flow takes over. Authentication errors, timeouts, malformed downloads, server errors and failures after a search starts never trigger cross-account retries. Existing Fetch Run history and estimated spend remain available for diagnostics.

If Bright Data's Free credits card shows the primary is exhausted but a trigger error does not clearly say so, set `BRIGHTDATA_PRIMARY_PAUSED_UNTIL` to that account's next renewal in UTC, for example `2026-11-01T00:00:00Z`. Searches select the first backup until then and automatically prefer the original primary afterward. Keep both keys in their original fields. This is a manual override based on the provider's account page; JobWeaver cannot verify the backup's actual free credits. Restart the container after changing the environment. An ambiguous HTTP error never causes an automatic retry on another paid account.

Only successful fetches advance the query watermark. A safe quota retry uses the exact same window; it does not refetch earlier successful windows or reset the 14-day initial backfill. Historical spend is retained per fingerprint and old unlabelled spend is attributed to the primary credential.

Deployment applies migration `0009` through the container's normal startup. If rolling back to an image that only contains migrations through `0008`, first stop fetching and use the newer image to downgrade to `0008`; older Alembic code cannot resolve revision `0009`. Downgrading removes credential attribution, so back up the database before doing so. The deployment script does not automatically downgrade the database.
