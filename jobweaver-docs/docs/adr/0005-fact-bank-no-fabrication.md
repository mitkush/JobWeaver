# Tailoring may only use the User's Fact Bank

The Tailored Resume, Cover Letter and Application Email are built only from Facts in the User's own uploaded documents. The AI may select, rewrite, reorder and emphasise Facts, including portfolio Facts that are not in the Base Resume, to match a Job's description and ATS keywords, but it may never add a skill, project, employer, metric or claim that is not in the Fact Bank. Every generated line carries a Tailoring Trace to its source Fact(s), and code (not the AI) checks before saving that every skill and technology named in the output exists in the Fact Bank. Lines that fail the check are removed or flagged, never silently kept.

**Considered and rejected:** free-form AI rewriting (fabricated skills surface in interviews and damage the User), copying the Base Resume unchanged (vague, poor ATS fit; the reason the product exists).

**Consequences:** uploaded documents are parsed into reviewable Facts that the User can correct before first use; the Draft screen shows the diff against the Base Resume and the trace for any line; adding a skill to a Draft means adding it to the Fact Bank first.
