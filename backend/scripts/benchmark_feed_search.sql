-- Run with psql against a database where pg_trgm is installed.
-- All benchmark tables and indexes are temporary and rolled back at the end.
-- These are synthetic search-predicate timings, not end-to-end Feed timings.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL statement_timeout = '60s';
CREATE TEMP TABLE feed_search_bench (
    id integer PRIMARY KEY,
    title text NOT NULL,
    company_name text NOT NULL,
    description text NOT NULL,
    expired_at timestamptz
) ON COMMIT DROP;
INSERT INTO feed_search_bench
SELECT i,
    CASE WHEN i % 997 = 0 THEN 'Ruby on Rails Developer' ELSE 'Backend Engineer ' || i END,
    CASE WHEN i % 991 = 0 THEN 'Rails Labs' ELSE 'Company ' || i END,
    CASE WHEN i % 200 = 0 THEN 'Brief advert'
         ELSE 'Build APIs in ' || CASE WHEN i % 997 = 0 THEN 'Rails' ELSE 'Python' END ||
              '. ' || repeat(md5(i::text) || ' ', 65) END,
    CASE WHEN i % 10 = 0 THEN now() ELSE NULL END
FROM generate_series(1, 20000) AS i;
ANALYZE feed_search_bench;
\echo 'Before indexes: Feed title/company substring search'
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT count(*) FROM feed_search_bench
WHERE expired_at IS NULL AND (title ILIKE '%rails%' OR company_name ILIKE '%rails%');
\echo 'Before indexes: preference description candidates in a 1000-posting chunk'
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT id, description FROM feed_search_bench
WHERE id <= 1000 AND (description ILIKE '%rails%' OR length(description) < 1000);
CREATE INDEX bench_title_trgm ON feed_search_bench USING gin (title gin_trgm_ops)
WHERE expired_at IS NULL;
CREATE INDEX bench_company_trgm ON feed_search_bench USING gin (company_name gin_trgm_ops)
WHERE expired_at IS NULL;
CREATE INDEX bench_description_trgm ON feed_search_bench USING gin (description gin_trgm_ops);
CREATE INDEX bench_description_length ON feed_search_bench (length(description));
ANALYZE feed_search_bench;
\echo 'After indexes: Feed title/company substring search'
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT count(*) FROM feed_search_bench
WHERE expired_at IS NULL AND (title ILIKE '%rails%' OR company_name ILIKE '%rails%');
\echo 'After indexes: preference description candidates in a 1000-posting chunk'
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT id, description FROM feed_search_bench
WHERE id IN (
    SELECT id FROM feed_search_bench WHERE id <= 1000 AND description ILIKE '%rails%'
    UNION
    SELECT id FROM feed_search_bench WHERE id <= 1000 AND length(description) < 1000
);
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_all_indexes WHERE relname = 'feed_search_bench' ORDER BY indexrelname;
ROLLBACK;
