# Source Adapters behind a registry, with per-source fallback

Each Source is one module implementing a fixed interface (fetch a window for a query, normalise raw data into Postings, report credits used) and registering itself, the same plugin pattern as OneBrain's connectors. Adding a Source is one new module plus one import line, never an `if source == ...` branch in core code. Every Fetch Run is isolated: if a Source fails for any reason (service down, rate limit, credits or tokens exhausted, blocked, unexpected format), the run marks it Degraded, keeps the Postings already fetched from other Sources, and retries it on the next scheduled run. One failing Source never stops the rest.

**Considered and rejected:** a single pipeline that fails as a whole (one flaky free tier would blank the Feed), substituting a "backup" Source for a failed one (Sources are not interchangeable; jobs only on LinkedIn are simply missed while it is down, and the UI says so).

**Consequences:** Source Status is a first-class screen; every adapter has recorded-fixture tests for success, limit-exceeded and malformed responses; all Sources ship in V1 and free-tier limits are discovered at run time rather than verified up front.
