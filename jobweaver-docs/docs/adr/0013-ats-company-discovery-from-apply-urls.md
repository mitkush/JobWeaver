# ATS Boards are discovered from apply URLs

Greenhouse, Lever, Ashby, SmartRecruiters, Workable and Recruitee offer free public job APIs, but only per company: there is no global search. JobWeaver learns which companies to query from the Postings it already fetches. When any Posting's apply URL points at a known ATS (e.g. `boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>`, `jobs.ashbyhq.com/<slug>`), the ATS Board is saved and fetched directly from then on. This is URL parsing, not AI. Users can also add a company's board by hand. Workday has no public job API and is best-effort.

**Considered and rejected:** a manual list only (too much effort, easy to miss companies), skipping ATS Sources (they are the cleanest free data and include ATS job IDs that make Exact duplicate matching possible).

**Consequences:** coverage starts small and grows with use; boards that return nothing for a long period are checked less often; ATS job IDs feed the Exact band in ADR-0004.
