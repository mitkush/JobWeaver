# PostgreSQL Feed search measurements

The current decision is to keep the existing PostgreSQL queries and indexes. The proposed four search indexes and migration 0013 were removed from this PR after measuring the actual candidate-query shape. There is no new extension requirement or startup index build.

## Read-only production measurements

On 15 Oct 2026 the running application had 26,723 open Jobs, 26,423 place-matched candidate Jobs and two Preferences. A bounded diagnostic used the existing application helpers for Preferences, Core spellings, places, titles, UserJob scoping and Feed filters. It issued EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) in a read-only transaction, without creating indexes or returning description contents. Each statement had a 15-second timeout.

Three 1,000-Posting candidate chunks compared the existing OR query against the proposed UNION query, including the actual UUID ID restrictions, title-matched short-description branch and outer description fetch. Each shape was executed three times, original before UNION. The first original execution read more cold buffers, so it must not be compared directly to the subsequent warmed UNION execution.

| Chunk | Original warm execution times (ms) | UNION warm execution times (ms) | Original / UNION shared buffer hits, last run |
| --- | --- | --- | --- |
| 1 | 1,026 / 1,369 | 1,000 / 1,009 | 16,105 / 18,277 |
| 2 | 955 / 985 | 961 / 1,101 | 15,650 / 17,464 |
| 3 | 1,021 / 1,072 | 1,229 / 1,068 | 16,822 / 17,948 |

Both shapes returned the same row counts in each chunk: 173, 166 and 108 respectively. The UNION had no consistent execution-time advantage and touched more buffers. It was removed from application code.

Feed count and 20-row page queries for Rails, Go and Engineer used the actual user-scoped join, hidden/open/company filters, title-match section and email section. Across three executions per query, execution times ranged from 25 to 82 ms. These are individual database statements, not total Feed response times. They do not establish that all Feed filters or other Users' workloads are fast.

The server was not isolated from normal traffic, cache order was not randomized, and no new index was built. These observations do not prove that a trigram index could never help. They do establish that the earlier synthetic speedups are insufficient justification for adding four maintained indexes during startup on this VM. The roughly one-second description chunks remain a candidate for separate investigation.

## Reproduce

From backend, with the target database configured through the usual settings:

```sh
PYTHONPATH=. python scripts/benchmark_feed_search.py --chunks 3 --repetitions 3
```

The default is one chunk and one execution per query. The command uses a read-only transaction, a 15-second statement timeout and a 120-second overall timeout. It performs real SELECT work and can warm caches or contend with live traffic. It prints only aggregate counts, timing, buffer counts and plan node types, not job text, user identifiers or SQL literals. It samples the first chunks in the application's current row order and the User with the most Feed links; it does not exhaustively benchmark every User or filter.

Before proposing an index again, measure the complete query plans and timings with and without that index on a representative staging copy. Include index size, build time and write overhead, and keep any expensive build outside the app startup health-check deadline. Preserve the current literal matching, Core keyword rules and tenant isolation.
