# PostgreSQL Feed search

JobWeaver keeps search in PostgreSQL. Migration 0013 adds `pg_trgm` indexes for the existing literal, case-insensitive title, company and description searches, plus a description-length index for Needs review candidates. No additional service, AI calls, relevance score or fuzzy keyword matching is introduced.

The Preferences candidate query now unions two ID-only lookups: descriptions that may mention a Core keyword, and title-matched descriptions short enough to need review. PostgreSQL can choose a different index for each branch. The outer query retrieves each candidate description once, and the existing Python whole-word, capitalization, canonical skill, Core keyword, location and work-mode rules still decide the match. Literal percent/underscore escaping remains unchanged. Feed searches remain scoped by UserJob.user_id.

Indexes:

- `idx_jobs_open_title_trgm`: GIN trigrams on open Job titles.
- `idx_jobs_open_company_trgm`: GIN trigrams on open Job company names.
- `idx_postings_description_trgm`: GIN trigrams on Posting descriptions.
- `idx_postings_description_length`: B-tree on untrimmed description length.

The Job indexes exclude expired Jobs. PostgreSQL maintains all four indexes as data changes. They require additional disk and write work, but no separate search process or synchronization queue. Very short searches such as `Go` or punctuation-heavy searches such as `C++` may not have useful trigrams; PostgreSQL can still choose another scan and the literal matching rules remain in force. See [PostgreSQL pg_trgm index support](https://www.postgresql.org/docs/16/pgtrgm.html#PGTRGM-INDEX).

## Migration

The database role needs CREATE privilege to install `pg_trgm`. Indexes are built concurrently outside the migration transaction so builds do not block ordinary writes. If a build fails, retrying revision 0013 removes and rebuilds only its own named indexes, including any invalid partial build. Existing application data is retained. Downgrade drops these indexes concurrently and leaves the extension installed because other database objects may use it. Initial index construction adds deployment time and disk usage; keep the PR in draft until its behavior on the production-sized dataset has been assessed.

## Reproduce the benchmark

After applying migrations, run against a PostgreSQL database with pg_trgm installed:

```sh
psql -X -d jobweaver_test -f backend/scripts/benchmark_feed_search.sql
```

The script uses temporary tables, creates 20,000 synthetic rows and rolls everything back. It reports EXPLAIN ANALYZE/BUFFERS plans before and after the changes plus index sizes. It does not modify JobWeaver tables. It models the search predicates, not the complete Feed query with user joins, filters, counts and network latency.

One local run with a selective `Rails` term showed:

| Predicate | Before | After |
| --- | ---: | ---: |
| Title/company substring | 9.56 ms | 0.16 ms |
| Description candidates in a 1,000-row chunk | 12.20 ms | 0.18 ms |

The plans used both Job trigram indexes for title/company search, and the description trigram plus length indexes for the split candidate query. The four synthetic indexes occupied about 4.8 MiB together. These are illustrative local timings on synthetic data, not production measurements or guaranteed speedups; keyword frequency, description sizes, cache state and job count affect results.
