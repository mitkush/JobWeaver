# LinkedIn via Bright Data: daily 24-hour windows, paced shared budget

Bright Data's free tier gives 5,000 credits a month at 1 credit per scraped record, so the budget is a number of records, whatever the fetch frequency. Fetching daily with the "past 24 hours" filter costs no more than fetching every 3 days, avoids paying twice for records that a coarser "past week" filter would repeat, and gets Jobs to Users sooner. Queries are narrow (each User's titles and locations) so credits go to relevant Postings. The budget is shared by all Users with no per-user split, paced across the days left in the month (about 166 records a day), and the 14-day Backfill is capped (about 1,500 records). A tracker shows spend and a month-end projection; when the budget is exhausted the Source is marked Degraded until it renews.

**Considered and rejected:** fetching every 3 days (same cost, staler jobs, possible double payment), a per-user quota (the founder chose a shared pool for a small trusted group).

**Consequences:** the available time-range options of the Bright Data LinkedIn scraper must be confirmed before build; pacing and caps are configuration, not code changes; a heavy User can use more than others, which is acceptable for a private group and revisited before any paid launch.
