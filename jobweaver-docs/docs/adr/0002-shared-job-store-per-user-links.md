# Jobs are stored once and linked to Users

Every Posting and Job is stored once, in shared tables with no owner. A User's Feed is a set of links (`user_jobs`) to the Jobs that match their Preferences, carrying per-user state (seen, hidden, Application, Drafts). Duplicate detection needs one shared view of all Postings anyway, and two Users who match the same job must not pay twice for it in Bright Data credits. Irrelevant Jobs never leak into another User's Feed, because the Feed only shows linked Jobs.

**Considered and rejected:** a copy of every job per User (dedup runs per user, the same record is paid for and stored several times, and "Already applied to this Company" needs cross-copy logic).

**Consequences:** job tables are the documented exception to "every table carries `user_id`" (ADR-0001); anything a User says about a Job (status, notes, hide) lives on `user_jobs` or a user-owned table, never on the shared Job; Postings contain only public job-advert data, never User data.
