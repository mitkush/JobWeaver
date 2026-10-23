# A standby provider may stand in for a Source that reads the same jobs

**Status: Accepted** (6 Oct 2026; amends ADR-0003).

ADR-0003 rejected "substituting a backup Source for a failed one", because Sources are not interchangeable: jobs only on LinkedIn are simply missed while it is down. That reason holds between different job sites. It does not hold between two providers that read the **same** site. LinkedIn through Apify returns the same LinkedIn jobs as LinkedIn through Bright Data. SerpApi and JSearch both read Google for Jobs. A Source may therefore declare a **Standby** for another Source (`standby_for`). The Standby runs only while its main Source is Degraded or turned off. It continues from the main Source's query watermarks, and the main Source continues from the Standby's, so a search is never paid for twice. Standbys run after all main Sources in a Fetch Run, so they decide from that run's state. An Admin can still run a Standby by hand. Users see no "jobs are delayed" notice for a main Source while its Standby is enabled and healthy. Every other part of ADR-0003 is unchanged: each Source is still one module, failures stay isolated, and different job sites never stand in for each other.

Providers billed from one account share one allowance (`budget_pool`). Naukri and LinkedIn through Apify draw on the same $5 a month. ADR-0009 still applies to the LinkedIn Standby: every result of a search is fetched. Only the shared budget can stop a run early, through Apify's own spending cap.

**Considered and rejected:** running both providers every day (pays twice for the same jobs), switching providers by hand (LinkedIn stays dark until someone notices), letting any Source stand in for any other (the reason ADR-0003 rejected backups still applies there).

**Consequences:** Postings from a main Source and its Standby have different Source names. The same job from both is grouped into one Job by Correspondence (ADR-0004), not by Source ID. SerpApi only partly overlaps JSearch, which also reads other boards, so its stand-in coverage is narrower.


## Amendment: ordered fallback chains (15 Oct 2026)

A Standby can itself have a Standby. The LinkedIn chain is Bright Data -> Apify -> Piloterr, with each Source declaring its immediate upstream provider through `standby_for`. Scheduled runs execute ancestors first, and a Standby waits while any enabled, configured ancestor is healthy. Manual runs remain available. Every member of the complete chain shares successful query watermarks, so recovery never resets Backfill or repeats a window already fetched by a later fallback. Posting priority still selects the Primary Posting and is independent of the fallback order. Piloterr remains opt-in with its existing description checks and 500-credit monthly cap.


## Additional opt-in LinkedIn fallbacks (23 Oct 2026)

Scrapingdog follows Piloterr, and self-hosted JobSpy follows Scrapingdog. Both declare `site = "LinkedIn"` and join the existing watermark family and Source filter group automatically. They remain off until the Admin enables them. Scrapingdog counts five credits per successful listing page and per successful full-detail request; budget-limited searches save partial Postings and their spend, but fail visibly without advancing the watermark so the next Standby can cover the same window. Both new adapters opt into this behavior through `retry_incomplete_window`; existing Sources retain their current cap behavior. Its configurable local safety ceiling is an upper bound, while its Account API is checked for current provider credits before a search. Signup and promotional credit awards are not treated as a recurring allowance. JobSpy has no API credit budget; its isolated worker is stopped on timeout or cancellation. Failed/blocked searches and missing JobSpy descriptions do not advance watermarks. The provider result ceiling remains about 1,000 per query.


## JobSpy partial-result handling and optional installation (23 Oct 2026)

JobSpy is an optional backend extra, excluded from default images. A worker checkpoints each completed 25-result page. Errors keep rows already returned by the library, missing descriptions only discard those rows, and a timeout preserves checkpoints already received by the parent. Any such case returns `complete=False`, so the existing opt-in retry path saves Postings and spend without advancing the watermark. The experimental JobSpy ceiling defaults to 50 results (`JOBSPY_MAX_RESULTS`, configurable through the provider's approximate 1,000-result maximum). Hitting it is explicitly incomplete rather than a claim to full coverage. This bounded experimental scope is an exception to the full-result policy for the primary LinkedIn providers; those providers retain their current scope. The worker also stops starting pages at its internal deadline, ahead of the parent's hard timeout. Worldwide queries send an explicit Worldwide location.

Scrapingdog receives an injected lookup for each search page's IDs. It avoids paying for details already stored as active LinkedIn-family Postings with usable cached descriptions. This reads only IDs and cached usability in a short-lived database session, never descriptions. Stored descriptions can be older than a changed external posting; this optimization prioritizes discovery of new jobs over re-fetching existing descriptions.
