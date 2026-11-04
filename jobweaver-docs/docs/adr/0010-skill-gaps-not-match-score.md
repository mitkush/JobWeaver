# Show Skill Gaps, not a match score

Feed cards do not show a match percentage. They show the required skills a Job asks for that are missing from the User's Fact Bank ("Missing: Kubernetes, Go"), so the User judges fit themselves. Required skills are extracted from a Job's description by the AI Gateway once, when the Job is created, and stored on the Job; the comparison with each User's skills is plain code, so it is instant, free and testable. The Feed is ordered newest first and narrowed by Preferences.

**Considered and rejected:** an overall match score with reasons (the founder did not find a single number useful), an LLM call per User per Job (cost grows with Users times Jobs and breaks free-tier limits).

**Consequences:** skill names are normalised (aliases such as "Postgres" and "PostgreSQL") before comparison; the extraction runs once per Job, not per User.


## Preference keyword context (4 November 2026)

Clear literal Preference matches do not depend on AI. For search, Ruby on Rails also accepts whole-word Ruby regardless of case, while Fact Bank skill equivalence is unchanged. Ambiguous skill names such as bare Rails can use the shared cached analysis as supporting context. Capitalisation alone is not proof: Payment Rails remains ambiguous. No technical/business phrase allowlists decide the meaning.

A title or model-generated skill alone never adds a match. A literal candidate that the model omits, rejects or has not analysed stays in Needs review rather than being silently removed. No AI call runs on Feed viewing or matching. Saved/Drafted/Applied Jobs retain the existing keep rules.

Primary-description changes mark analysis for refresh but keep old skills provisionally, so supported cards do not bounce between tabs while the new result is queued. Title-only and whitespace-only edits do not invalidate context. A change of primary Posting still clears its context because that is a different advert. In-flight extraction only saves against the same primary description. This reuses the existing cache and gateway task, with no schema migration. Model omissions cannot erase clear literal matches or unresolved candidates.
