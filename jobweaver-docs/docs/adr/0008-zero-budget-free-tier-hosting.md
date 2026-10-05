# Zero budget: one free web service kept warm, in-process scheduler

JobWeaver runs entirely on free tiers with no payment method attached anywhere, so nothing can bill. One web service serves the API and the built frontend (one URL, no CORS). Free hosts sleep after about 15 minutes idle, so an external monitor (UptimeRobot) pings a lightweight `GET /health` (no database access) every 5 minutes, the setup already proven on OneBrain. Scheduled Fetch Runs and reminders run in an in-process scheduler (APScheduler) on that warm instance, as background work, never inside one long HTTP request. If the host still sleeps, an external free cron calling a secret-protected trigger endpoint is the fallback. The database is a free Postgres with pgvector, chosen for a free tier that does not expire.

**Considered and rejected:** separate worker and queue services (a second free service doubles the sleep problem), paid tiers (zero budget).

**Consequences:** jobs must be idempotent and resumable after a restart; long Fetch Runs are chunked; free-tier limits of each host are listed in `COSTS.md` and must be checked when choosing providers (some free databases expire or pause).
