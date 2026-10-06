# A standby provider may stand in for a Source that reads the same jobs

**Status: Proposed** (amends ADR-0003; needs the founder's acceptance).

ADR-0003 rejected "substituting a backup Source for a failed one", because Sources are not interchangeable: jobs only on LinkedIn are simply missed while it is down. That reason holds between different job sites. It does not hold between two providers that read the **same** site. LinkedIn through Apify returns the same LinkedIn jobs as LinkedIn through Bright Data. SerpApi and JSearch both read Google for Jobs. A Source may therefore declare a **Standby** for another Source (`standby_for`). The Standby runs only while its main Source is Degraded or turned off. It continues from the main Source's query watermarks, and the main Source continues from the Standby's, so a search is never paid for twice. Standbys run after all main Sources in a Fetch Run, so they decide from that run's state. An Admin can still run a Standby by hand. Users see no "jobs are delayed" notice for a main Source while its Standby is enabled and healthy. Every other part of ADR-0003 is unchanged: each Source is still one module, failures stay isolated, and different job sites never stand in for each other.

Providers billed from one account share one allowance (`budget_pool`). Naukri and LinkedIn through Apify draw on the same $5 a month. ADR-0009 still applies to the LinkedIn Standby: every result of a search is fetched. Only the shared budget can stop a run early, through Apify's own spending cap.

**Considered and rejected:** running both providers every day (pays twice for the same jobs), switching providers by hand (LinkedIn stays dark until someone notices), letting any Source stand in for any other (the reason ADR-0003 rejected backups still applies there).

**Consequences:** Postings from a main Source and its Standby have different Source names. The same job from both is grouped into one Job by Correspondence (ADR-0004), not by Source ID. SerpApi only partly overlaps JSearch, which also reads other boards, so its stand-in coverage is narrower.
