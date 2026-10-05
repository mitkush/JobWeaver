# User-based tenancy from day one

JobWeaver starts as a tool for the founder and a few friends, but it is built so that going paid later needs no data-model rewrite. Every user-owned record (Fact Bank, Preferences, Feed links, Drafts, Applications, reminders, Gmail credentials, AI usage) carries `user_id` from the first migration, and every query, cache key and background job is scoped by it. The tenancy unit is the **User**, not an organization: job hunting is personal, and a workspace layer would add joins and access rules that no planned feature needs. Shared job data (Sources, Companies, ATS Boards, Postings, Jobs, Match Pairs) is deliberately not user-owned (ADR-0002).

**Considered and rejected:** single-user app (retrofitting tenancy touches every table later), organization/workspace tenancy as in OneBrain (no team use case; can be added above User if a team plan ever exists).

**Consequences:** every user-owned table has `user_id` with an `ON DELETE CASCADE` foreign key and a composite index on its hottest filter; cross-user isolation tests are mandatory for every user-owned endpoint; one User has the Admin role for Source Status and the Credit Budget.
