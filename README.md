# JobWeaver

AI job-hunt assistant: fetches jobs daily from many sources, groups duplicates across sites, shows skill gaps, and prepares a truthful tailored resume, cover letter and email for any job, which you review and send yourself from Gmail.

**Status:** Phase 0 (foundation) and Phase 1 (accounts and profile) are built: Google sign-in, onboarding, Fact Bank from your documents, preferences, Gmail connection and account deletion. Job sources arrive in Phase 2 (see the [release plan](jobweaver-docs/PRD.md#12-release-plan-build-order)).

## Docs
- [PRD](jobweaver-docs/PRD.md) - what V1 does, requirements, architecture, release plan
- [Glossary](jobweaver-docs/CONTEXT.md) - domain terms used everywhere
- [ADRs](jobweaver-docs/docs/adr/) - why each key decision was made
- [Costs](jobweaver-docs/COSTS.md) - every free tier and what happens at its limit
- [Discovery brief](prd-prompt.md) - the agreed decisions the PRD is built from

## Run locally

Needs Python 3.12, Node 22 and Postgres 16 (or `docker compose up postgres`).

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

## Checks

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
cd frontend && npm run gen:api   # regenerate API types after any backend API change
```

Backend tests need a Postgres database `jobweaver_test` (user/password `jobweaver`), or set `TEST_DATABASE_URL`. Tests run the AI Gateway in recorded mode: zero live AI calls.

## Deploy (free tier, ADR-0008)

1. **Database:** create a free [Neon](https://neon.tech) project. Use its connection string as `DATABASE_URL`, written as `postgresql+asyncpg://USER:PASSWORD@HOST/DB?ssl=require`. Do not use Render's free Postgres: it is deleted after 30 days.
2. **Google Cloud:** create an OAuth client (Web application) with the redirect URI `https://<your-app>/api/auth/google/callback`. On the OAuth consent screen choose External, keep it in Testing, add the Gmail scope `gmail.compose`, and add every user's Gmail address under Test users (up to 100). Testing-mode Gmail access lasts 7 days; the app reminds users to reconnect.
3. **Render:** create a Blueprint from this repo (`render.yaml`) and fill in the secret values. Generate `CREDENTIALS_ENCRYPTION_KEY` with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and never change it afterwards. Production refuses to start without its secrets.
4. **Keep warm:** add an [UptimeRobot](https://uptimerobot.com) HTTP monitor on `https://<your-app>/health` every 5 minutes. `/health` never touches the database, so Neon can still sleep.
5. **AI keys:** add `GEMINI_API_KEY` (Google AI Studio), `GROQ_API_KEY` and `OPENROUTER_API_KEY`. Any missing provider is skipped by the fallback chain.
