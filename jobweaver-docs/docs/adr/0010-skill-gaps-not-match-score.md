# Show Skill Gaps, not a match score

Feed cards do not show a match percentage. They show the required skills a Job asks for that are missing from the User's Fact Bank ("Missing: Kubernetes, Go"), so the User judges fit themselves. Required skills are extracted from a Job's description by the AI Gateway once, when the Job is created, and stored on the Job; the comparison with each User's skills is plain code, so it is instant, free and testable. The Feed is ordered newest first and narrowed by Preferences.

**Considered and rejected:** an overall match score with reasons (the founder did not find a single number useful), an LLM call per User per Job (cost grows with Users times Jobs and breaks free-tier limits).

**Consequences:** skill names are normalised (aliases such as "Postgres" and "PostgreSQL") before comparison; the extraction runs once per Job, not per User.
