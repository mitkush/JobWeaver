# JobWeaver

AI job-hunt assistant: fetches jobs daily from many sources, groups duplicates across sites, shows skill gaps, and prepares a truthful tailored resume, cover letter and email for any job, which you review and send yourself from Gmail.

**Status:** Phases 0 to 6 are built (V1 complete): Google sign-in, onboarding, Fact Bank from your documents, preferences, Gmail connection, account deletion, daily job fetching from LinkedIn (Bright Data, with Apify as a standby), Naukri, JSearch (with SerpApi as a standby), Adzuna, company boards on Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee and Workday, the remote boards Remotive, Remote OK, We Work Remotely, Himalayas, Jobicy and Working Nomads, and Hacker News "Who is hiring" (AI-extracted), with source health and budgets on the admin Sources page, duplicates grouped into one Job per opening (with Possible Duplicates to confirm), and a personal Feed with Skill Gaps, filters and the Correspondence view. Draft packages add Fact-backed tailoring, inline edits, Draft Chat, immutable versions, resume diffs, selectable PDF downloads, Gmail draft hand-off and marking applications as applied. The Applications tracker keeps each status change, suggests follow-ups and shows your history per Company (see the [release plan](jobweaver-docs/PRD.md#12-release-plan-build-order)).

## Docs
- [PRD](jobweaver-docs/PRD.md) - what V1 does, requirements, architecture, release plan
- [Glossary](jobweaver-docs/CONTEXT.md) - domain terms used everywhere
- [ADRs](jobweaver-docs/docs/adr/) - why each key decision was made
- [Costs](jobweaver-docs/COSTS.md) - every free tier and what happens at its limit
- [Discovery brief](prd-prompt.md) - the agreed decisions the PRD is built from

See [PostgreSQL Feed search measurements](jobweaver-docs/POSTGRES_SEARCH.md) for a read-only query benchmark and the current optimization decision.
Existing Postings can be cached with the bounded [description-mention backfill](jobweaver-docs/DESCRIPTION_MENTIONS.md); it runs separately from startup migrations.

## Run locally

Needs Python 3.12, Node 22 and Postgres 16 with the [pgvector](https://github.com/pgvector/pgvector) extension (or `docker compose up postgres`, which uses the pgvector image). Creating the extension needs a superuser once per database: `CREATE EXTENSION vector;` in `jobweaver` and `jobweaver_test`.

```bash
# Backend
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp ../.env.example .env        # then fill in the values (see below)
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (second terminal); proxies /api to the backend
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

Without Google credentials, set `DEV_LOGIN_ENABLED=true` and `GATEWAY_MODE=recorded` in `backend/.env`: the sign-in page then shows a local dev sign-in, and documents are "parsed" from recorded fixtures with no AI calls.

## Drafts (Phase 4)

Review your Fact Bank, then choose **Create draft** from the Feed or a Job. Generation reports progress; review each document and its Fact references before using it. Inline edits require **Save draft**. Draft Chat preserves saved manual edits unless you explicitly allow replacement; previous versions can be restored as a new version.

Resume and Cover Letter PDFs use bundled Liberation Sans fonts (licence included) with Standard and Compact single-column layouts. Resumes over two pages are rejected with guidance to shorten them or choose Compact. Unsupported font characters must be edited before export.

**Open in Gmail** checks the recipient and asks you to confirm the recipient and PDF attachment. Gmail access may require reconnection. Successful hand-off opens Gmail's Drafts mailbox; the application never sends mail. If Gmail creation fails, download the PDF and attach it yourself in compose. Apply-link Jobs support PDF download and **Mark as applied**.

Recorded AI fixtures exercise unsupported skills and fabricated metrics. Truthfulness checks conservatively compare each line against its referenced Facts; they are not a semantic proof of every possible paraphrase. Review remains necessary. Live provider quality, production latency and real Gmail OAuth hand-off need validation with your configured accounts.

## Sources (Phase 5)

- **LinkedIn discovery keywords:** set `BRIGHTDATA_DISCOVERY_KEYWORDS` (for example `Software,Developer,Backend,Full stack`) and Bright Data searches those keywords joined with OR once per country in users' Preferences, past 24 hours, instead of once per title and city. A Preference with no location gets one worldwide remote search, never a worldwide on-site one. Jobs with an unexpected title are then found and the Feed's title, place and Core-keyword rules decide who sees them. `BRIGHTDATA_LIMIT_PER_SEARCH` (default 1,000) caps each search; a run that reaches it shows as **incomplete** under **Recent runs**. A new country-wide search picks up where the title searches for that country stopped; with nothing to pick up from, it uses the normal 14-day Backfill. With discovery keywords on, the LinkedIn standbys (Apify, then Piloterr) still search titles, so their search windows are their own.
- **Standbys:** LinkedIn falls back in order from Bright Data to Apify to Piloterr to Scrapingdog to JobSpy. Each standby waits until all upstream providers are degraded, disabled or unconfigured. SerpApi runs only while JSearch is unavailable. A standby continues from its main source's search windows, so the same search is never paid for twice. An admin can still run a standby by hand.
- **Shared budget:** Naukri and LinkedIn (Apify) draw on one $5 Apify allowance, shown on both cards. Each run is capped at what is left of it.
- **LinkedIn (Piloterr):** optional third fallback after Bright Data and Apify, lower Posting priority, and capped locally at 500 credits per month. Each successful page counts as one credit; results without a description are skipped. Confirm the actual account allowance and renewal in Piloterr before enabling it. Configure `PILOTERR_API_KEY` in the server's `backend/.env`; deploys do not need a Piloterr Actions secret.
- **LinkedIn (Scrapingdog):** opt-in fourth fallback. Set `SCRAPINGDOG_API_KEY` in the server's `backend/.env`. Search results have no description, so the adapter retrieves each job's details: five credits per successful search page and another five per successful detail call. A ten-job page with full details costs 55 credits. Before purchasing a detail, the Fetcher checks only that page's IDs against active LinkedIn-family Postings with a cached usable description; known jobs are skipped, including jobs saved by an earlier partial attempt. `SCRAPINGDOG_MONTHLY_CREDITS=100` is the default local safety ceiling; raise it only after checking awarded credits. Every search also checks the provider's current account balance. Signup and social rewards are not assumed to renew. Budget or provider caps save partial postings but fail the run visibly and leave its window open for the next fallback. Search and detail shapes were verified live on 23 Oct 2026.
- **LinkedIn (JobSpy):** opt-in final fallback with no provider key. The package is optional: install `pip install -e ".[jobspy]"` in the backend, or build with `docker build --build-arg BACKEND_EXTRAS=jobspy -t jobweaver .`. For Oracle deployment, set the repository Actions variable `BACKEND_EXTRAS` to `jobspy`; leave it empty to keep pandas, numpy and curl_cffi out of the default image. A child process searches in 25-result batches and checkpoints each completed page. The default `JOBSPY_MAX_RESULTS=50` bounds the experimental search; reaching that cap leaves the window incomplete. Earlier checkpoints survive a later block, worker error or hard timeout (`JOBSPY_TIMEOUT_SECONDS=900`); rows without descriptions are skipped and also make the result incomplete. Partial Postings are saved without advancing the watermark. Optional `JOBSPY_PROXIES` is a JSON array; proxy charges are separate. Worldwide searches explicitly send `location="Worldwide"` rather than leaving location empty. JobSpy ignores LinkedIn's `is_remote`, so remote intent is added to keywords and the Feed checks returned work modes. LinkedIn may still block your server IP. Check a manual run before relying on it; direct live collection has not been verified from the production VM.
- **Off by default:** Workday, Foundit and Instahyre read the JSON behind each site's own pages. These are not published APIs, and they could not be checked from the build environment. Each card on the Sources page says why the source is off. Turn one on and use **Run now** to see whether it works from your server. Cutshort and Hirist are not built: no usable endpoint is known.
- **Hacker News:** comments from "Who is hiring" threads are stored as they are, then read by the AI (Gemini Flash-Lite first) into Postings. Links and emails are kept only if they appear in the comment itself. While AI is unavailable the comments wait in a queue.
- **Unverified field names:** the build environment could not reach any job site. Every Phase 5 adapter is tested against payloads shaped like each provider's documentation or other projects' code. Before relying on a source, check its first real run under **Recent runs**.

## Applications (Phase 6)

- **Tracker:** **Applications** lists one Application per Job, grouped Drafted, Applied, Replied, Interview, Offer, Rejected. Change a status with its menu. Every change is kept with its time under **History**. Opening a Draft in Gmail creates the Application, and **Mark as applied** moves it to Applied. Mark as applied never moves a later status back.
- **Follow-up Reminders:** an Application still Applied after 7 days shows a reminder on the Feed and Applications pages. Change the wait under **Settings**. **Draft a follow-up** opens an editable email built from the Job, the Company and the date you applied, so it contains nothing invented and uses no AI quota. It goes to your Gmail Drafts without an attachment and is never sent. **Not now** hides the reminder for another period.
- **Company history:** select a Company name on a Job or an Application to see every Application you made there.
- **Admin:** the Sources page also shows AI calls today against each provider's free quota, and the last week by task.

Set `MISTRAL_API_KEY` to add Mistral Small as an optional fallback through the AI gateway. The gateway applies the configured per-model daily cap and records usage. On Mistral Studio's Free mode, Mistral may use input and output data to train its models; review its data controls before enabling it for users' resumes.

## Application Extension (FR-E14, in progress)

A Chrome/Brave extension that fills application forms from your reviewed profile and a chosen Draft; you review and submit (ADR-0017, plan in `jobweaver-docs/APPLICATION_EXTENSION_PLAN.md`). On a form, open the extension, choose the Draft, **Scan this form**, untick anything you do not want, then **Fill ticked fields**. Your details and the Draft's PDFs go in; questions, salary, visa and referrer fields stay for you. **Undo** restores what JobWeaver changed. It never submits.

You can also start directly on a company's careers-page advert, without a Job or Draft in
JobWeaver: click **Read this job**, review the title, Company and public JD, and choose
**Save reviewed job**. Structured `JobPosting` data, advert regions (including Workday)
and selected text are supported; when extraction is incomplete, edit or paste the JD in
the review box. Nothing is uploaded until Save. **Create Draft from this JD** uses your
reviewed Fact Bank through the existing AI gateway and opens the Draft page. Return to
the advert/form tab and choose **Use this Draft** once generation finishes. On an existing
Job, your reviewed page text is personal and never replaces the shared Source description.
Creating another Draft preserves existing Drafts and their manual edits.

Reviewed JD text is stored only on your own Job link, including the first capture.
Capture-only Jobs are not added to other Users' Feeds by Preferences matching. Required
skills are extracted from your JD through the AI gateway when the Draft is generated and
kept on your link and Draft snapshot, so skill checks and Skill Gaps use that description.
An extraction failure leaves a retryable failed Draft rather than skipping skill checks.
The push-only capture Source has no scheduled fetches or Admin fetch controls.

Capture adds backend migration 0016 and new extension permissions (access list version 3).
Deploy the server before rebuilding/reloading the extension, then reconnect and approve
the new access list. This slice does not add AI custom-question answers or regenerate an
existing Draft's versions; those remain later stages. The employer page still needs a
separate Apply click before there are form fields to scan.

1. Set `EXTENSION_IDS=npdbpfgligiimfnoblngghbokehjbafm` on the server.
2. Build it for your server: `cd extension && npm ci && JOBWEAVER_ORIGIN=https://your-host npm run build` (defaults to the production host; use `http://localhost:5173` locally).
3. In Chrome or Brave open `chrome://extensions`, turn on Developer mode, choose **Load unpacked** and select `extension/dist`.
4. Click the extension, then **Connect**, and approve on the JobWeaver page that opens.

The connection lasts `EXTENSION_CREDENTIAL_HOURS` (default 12) or until the browser closes, and **Settings > Browser extension** revokes it at once.

## Checks

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
cd frontend && npm run gen:api   # regenerate API types after any backend API change
cd extension && npm run typecheck && npm test && npm run build
```

Backend tests need a Postgres database `jobweaver_test` (user/password `jobweaver`), or set `TEST_DATABASE_URL`. Tests run the AI Gateway in recorded mode: zero live AI calls.

## Deploy (free tier, ADR-0008)

1. **Database:** create a free [Neon](https://neon.tech) project. Use its connection string as `DATABASE_URL`, written as `postgresql+asyncpg://USER:PASSWORD@HOST/DB?ssl=require`. Neon includes pgvector, and the first migration run creates the extension. Do not use Render's free Postgres: it is deleted after 30 days.
2. **Google Cloud:** create an OAuth client (Web application) with the redirect URI `https://<your-app>/api/auth/google/callback`. On the OAuth consent screen choose External, keep it in Testing, add the Gmail scope `gmail.compose`, and add every user's Gmail address under Test users (up to 100). Testing-mode Gmail access lasts 7 days; the app reminds users to reconnect.
3. **Render:** create a Blueprint from this repo (`render.yaml`) and fill in the secret values. Generate `CREDENTIALS_ENCRYPTION_KEY` with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and never change it afterwards. Production refuses to start without its secrets.
4. **Keep warm:** add an [UptimeRobot](https://uptimerobot.com) HTTP monitor on `https://<your-app>/health` every 5 minutes. `/health` never touches the database, so Neon can still sleep.
5. **AI keys:** add `GEMINI_API_KEY` (Google AI Studio), `GROQ_API_KEY` and `OPENROUTER_API_KEY`. Any missing provider is skipped by the fallback chain. `MISTRAL_API_KEY` is an optional additional fallback. The AI notice is versioned; users must accept the updated notice before documents are sent to Mistral.
6. **Job source keys:** add `BRIGHTDATA_API_KEY` (LinkedIn; accepts comma-separated keys tried in order on search-start quota, rate-limit or explicit inactive-account errors), `RAPIDAPI_KEY` (JSearch), `APIFY_TOKEN` (Naukri and the LinkedIn standby), `SERPAPI_KEY` (the JSearch standby), `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`, and optionally `PILOTERR_API_KEY` (LinkedIn Piloterr). Store provider keys in the server's `backend/.env`. Do not attach a payment method to these accounts (zero budget). Any missing key just shows that source as "Not configured". The daily fetch runs at 01:17 UTC; check the admin **Sources** page after the first run.
7. **Error reporting (optional):** create a free [Sentry](https://sentry.io) project and set `SENTRY_DSN`. Only exception types, stack traces, routes and log templates are sent: error messages, request bodies, cookies, headers and local variables are stripped first, because a database error can quote a resume or a Draft. Server logs show database errors as their type and SQL only.
8. **Cron fallback (optional):** if the host ever sleeps through the daily run, add a free cron job (e.g. cron-job.org) that sends `POST https://<your-app>/api/internal/fetch` with header `X-Cron-Secret: <INTERNAL_CRON_SECRET>` once a day.
