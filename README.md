# JobWeaver

AI job-hunt assistant: fetches jobs daily from many sources, groups duplicates across sites, shows skill gaps, and prepares a truthful tailored resume, cover letter and email for any job, which you review and send yourself from Gmail.

**Status:** Phases 0 to 4 are built: Google sign-in, onboarding, Fact Bank from your documents, preferences, Gmail connection, account deletion, daily job fetching from LinkedIn (Bright Data), JSearch, Greenhouse, Lever and Remotive with source health and budgets on the admin Sources page, duplicates grouped into one Job per opening (with Possible Duplicates to confirm), and a personal Feed with Skill Gaps, filters and the Correspondence view. Draft packages add Fact-backed tailoring, inline edits, Draft Chat, immutable versions, resume diffs, selectable PDF downloads, Gmail draft hand-off and marking applications as applied (see the [release plan](jobweaver-docs/PRD.md#12-release-plan-build-order)).

## Docs
- [PRD](jobweaver-docs/PRD.md) - what V1 does, requirements, architecture, release plan
- [Glossary](jobweaver-docs/CONTEXT.md) - domain terms used everywhere
- [ADRs](jobweaver-docs/docs/adr/) - why each key decision was made
- [Costs](jobweaver-docs/COSTS.md) - every free tier and what happens at its limit
- [Discovery brief](prd-prompt.md) - the agreed decisions the PRD is built from

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

## Checks

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
cd frontend && npm run gen:api   # regenerate API types after any backend API change
```

Backend tests need a Postgres database `jobweaver_test` (user/password `jobweaver`), or set `TEST_DATABASE_URL`. Tests run the AI Gateway in recorded mode: zero live AI calls.

## Deploy (free tier, ADR-0008)

1. **Database:** create a free [Neon](https://neon.tech) project. Use its connection string as `DATABASE_URL`, written as `postgresql+asyncpg://USER:PASSWORD@HOST/DB?ssl=require`. Neon includes pgvector, and the first migration run creates the extension. Do not use Render's free Postgres: it is deleted after 30 days.
2. **Google Cloud:** create an OAuth client (Web application) with the redirect URI `https://<your-app>/api/auth/google/callback`. On the OAuth consent screen choose External, keep it in Testing, add the Gmail scope `gmail.compose`, and add every user's Gmail address under Test users (up to 100). Testing-mode Gmail access lasts 7 days; the app reminds users to reconnect.
3. **Render:** create a Blueprint from this repo (`render.yaml`) and fill in the secret values. Generate `CREDENTIALS_ENCRYPTION_KEY` with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and never change it afterwards. Production refuses to start without its secrets.
4. **Keep warm:** add an [UptimeRobot](https://uptimerobot.com) HTTP monitor on `https://<your-app>/health` every 5 minutes. `/health` never touches the database, so Neon can still sleep.
5. **AI keys:** add `GEMINI_API_KEY` (Google AI Studio), `GROQ_API_KEY` and `OPENROUTER_API_KEY`. Any missing provider is skipped by the fallback chain.
6. **Job source keys:** add `BRIGHTDATA_API_KEY` (LinkedIn) and `RAPIDAPI_KEY` (JSearch). Do not attach a payment method to either account (zero budget). The daily fetch runs at 01:17 UTC; check the admin **Sources** page after the first run.
7. **Cron fallback (optional):** if the host ever sleeps through the daily run, add a free cron job (e.g. cron-job.org) that sends `POST https://<your-app>/api/internal/fetch` with header `X-Cron-Secret: <INTERNAL_CRON_SECRET>` once a day.
