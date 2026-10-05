# Duplicates: Postings grouped into Jobs by confidence band, never silently mis-merged

A Job is one real opening; a Posting is one advert for it on one Source. Pairs of Postings are scored on normalised Company, title similarity, description meaning (embeddings) and locations, and placed in a band. **Exact** (same ATS job ID or apply URL) and **High** group automatically. **Medium** becomes a Possible Duplicate that the User confirms or rejects in one click. **Low** stays separate. Any group can be split with "Not the same Job", which stores a Rejected Pair that is never proposed again. The Primary Posting follows Source priority, but fields are merged across the group so nothing is lost (an email found only on a lower-priority Posting stays on the Job). The same advert posted for several cities is one Job with several locations.

**Considered and rejected:** always auto-merge (a wrong merge hides a real job, and the founder's top concern is not missing genuine posts), always ask (too many clicks), word-for-word matching (the same opening is often reworded per site), keeping only the top-priority Posting (loses data and the cross-source view).

**Consequences:** thresholds start strict so the Medium band is small, and are tuned on real data; the Correspondence screen shows every Posting regardless of priority; Rejected Pairs are checked before any grouping.
