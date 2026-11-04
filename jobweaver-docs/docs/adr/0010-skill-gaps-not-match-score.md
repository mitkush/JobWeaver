# Show Skill Gaps, not a match score

Feed cards do not show a match percentage. They show the required skills a Job asks for that are missing from the User's Fact Bank ("Missing: Kubernetes, Go"), so the User judges fit themselves. Required skills are extracted from a Job's description by the AI Gateway once, when the Job is created, and stored on the Job; the comparison with each User's skills is plain code, so it is instant, free and testable. The Feed is ordered newest first and narrowed by Preferences.

**Considered and rejected:** an overall match score with reasons (the founder did not find a single number useful), an LLM call per User per Job (cost grows with Users times Jobs and breaks free-tier limits).

**Consequences:** skill names are normalised (aliases such as "Postgres" and "PostgreSQL") before comparison; the extraction runs once per Job, not per User.


## Preference keyword context (4 November 2026)

The shared extracted skills also confirm that literal Preference keywords refer to technology or domain expertise in the role. There are no keyword-specific business/technical phrase lists. Preference keywords remain authoritative, and the JD must literally name the term or an existing alias; extraction alone cannot add a match. Pending candidates appear under Needs review, then are promoted or removed after extraction. No AI call runs on Feed viewing or matching. Saved/Drafted/Applied Jobs retain the existing keep rules.

Primary-description edits and primary Posting changes invalidate the analysis. In-flight extraction only saves against the same primary description. This reuses the existing cache and gateway task, with no schema migration. Model omissions can still reject a genuine mention; this is contextual filtering, not a guarantee of perfect classification.
