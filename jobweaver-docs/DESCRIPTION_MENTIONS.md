# Cached description mentions

Feed matching stores deterministic vocabulary mentions on each Posting when save_postings already has the description in memory. This is separate from Job.required_skills, which is AI-extracted and may include title text. A title alone still cannot confirm a Core keyword.

The nullable fields are description_mentions (canonical TEXT[]), description_usable (the existing has_description rule) and description_mentions_version. A current empty array means no vocabulary mentions; null means not cached. There is no new index: Feed rebuilds already look up at most 1,000 primary Posting IDs per chunk, and compare the small arrays in Python.

## Matching and invalidation

- Use the existing keywords.mentioned function, including aliases, word boundaries and capitalization rules for Go, REST and other prose words.
- Only use a cache whose version matches and whose array and usability flag are both present. Stale or missing rows retain the existing description SQL prefilter and Python matcher.
- Unknown preference keywords keep a description fallback, including non-Core keywords used by keyword_min_matches. Current known vocabulary terms are not re-scanned in that fallback. This preserves custom phrases such as Sidekiq or Rails developer without restricting Preferences to the vocabulary.
- Current caches supply Needs review usability without reading text. Rebuilds read metadata; they do not update caches or call AI for this cache. Separate required-skills extraction can still read descriptions.
- Changed descriptions and stale caches are recomputed by save_postings. Other writers of description must also refresh or invalidate its cache.
- The version hashes the vocabulary, aliases, prose words and minimum usable length. Bump MATCHER_REVISION in tailoring/description_mentions.py whenever the matching or usability algorithm changes. Old rows then fall back until re-fetched or explicitly backfilled.
- Jobs use their current primary Posting's cache, so changing the primary during a merge or split cannot leave a copied Job cache pointing at old text. User-specific matching and isolation rules remain unchanged.

## Deployment and backfill

Migration 0013 adds three nullable columns only. It reads no descriptions, builds no indexes and performs no backfill. Until caches are populated, existing Postings use the fallback, so deploy is functional immediately. New or re-fetched Postings populate their caches normally.

The scheduler fills the rest by itself: each queue run (every 6 hours, and once 5 minutes after every start) caches up to 5,000 missing or stale Postings in batches of 200, inside the fetch lock, with matching done in a worker thread so requests stay responsive. About 29,000 existing Postings therefore fill within roughly six runs, and a vocabulary or version change refills on its own. A backfill error is logged and retried next run; Feeds keep the fallback meanwhile.

To fill the cache at once instead, run batches inside the application container:

```sh
sudo docker exec jobweaver python scripts/backfill_description_mentions.py --batch-size 500 --max-batches 100
```

Or from backend locally:

```sh
PYTHONPATH=. python scripts/backfill_description_mentions.py --batch-size 100 --max-batches 1
```

Increase max-batches deliberately to process more rows. The command prints counts only. Each batch commits independently; rerunning skips current rows and resumes missing/stale rows. A batch locks only its selected rows with FOR UPDATE SKIP LOCKED so concurrent ingestion cannot change their descriptions between reading and caching. Zero rows can mean other workers hold the remaining rows; rerun later. The command uses a 2-second lock timeout and 30-second statement timeout, with a short pause between batches. Timeouts limit SQL statements, not total Python processing time or the whole command. Cache construction consumes CPU; start small on the 1 GB VM. The command does not rebuild all Feeds or change Preferences.

## Validation and limits

Tests cover equivalent cached/stale/missing matches, unknown Core and non-Core keywords, description edits, cache-version refresh, resumable batches and concurrent locks. A query-capture regression asserts that a known-vocabulary Feed rebuild issues neither a Posting description SELECT nor ILIKE. Existing tests cover aliases, keyword thresholds, Needs review, merges, splits and cross-user isolation.

A local synthetic comparison used 1,000 Postings with roughly 4,522-character descriptions, one Preference (Rails Core plus PostgreSQL), 200 matches and the actual _matches function. Three legacy runs took 111/104/104 ms; cached runs took 16/30/16 ms and returned identical match dictionaries. Building 1,000 caches in batches of 100 took 5.46 seconds locally. These are developer-machine measurements on synthetic text, not production latency or a deployment-time guarantee. No production schema or cache data was changed for this PR. Unknown keywords and unbackfilled rows retain the description-check cost; matching loops and Feed link writes also remain.
