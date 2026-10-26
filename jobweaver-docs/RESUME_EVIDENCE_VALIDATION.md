# Resume evidence coverage

## Report and diagnosis

The reported PlanetScale Draft contained 254 resume words. Its Standard PDF ended at
169.7 mm on A4, with a usable bottom of 285 mm. The provider received all 84 Facts:
input selection did not remove the missing material. The saved warnings showed that
the Summary had been removed for mixed Fact groups and unsupported claims.

Prompt-only corrections were insufficient in two live comparisons: the checked results
had 327 and 318 words. One Summary was still rejected. Do not describe these tests as
proof that a word-count instruction reliably fills a page.

## Implementation

Keep the original font sizes, margins, line spacing and PDF renderer. Give the model
section-planning guidance for substantial Fact Banks, with a shorter result permitted
when evidence is sparse. A shared technology does not make distinct project work
redundant. Limit project selection to two relevant projects.

After the first result passes the existing checks, consider one development pass only
when it has fewer than 380 resume words and the Fact Bank contains at least eight
distinct work Facts totaling 450 words. These are internal heuristics, not a quality
score, minimum output requirement or a reason to fabricate content.

Send the checked content, Facts and feedback through the same typed gateway route.
Preserve cited groups under prompt budgeting. Both attempts share the original generation
deadline; Draft Chat is unchanged. Record each call normally. A second call can increase
latency and quota use; it is limited to one and never runs for a sparse Fact Bank.

Adopt the development only if it has more checked resume words, still contains required
package parts, and renders on one Standard page. Failed, unsafe, shorter or overflowing
results leave the first usable package intact. Recheck consent before saving. No manual
edits or existing Draft versions are revised by this generation-only process.

The name checker also treated sentence-opening verbs "Brings" and "Offers" as unknown
proper names. Add those two ordinary openings without changing skill, employer,
leadership, metric, expertise or cross-group checks.

## Live comparison

An isolated development call using the same reviewed Facts and Job produced 394 checked
resume words, eight Experience bullets and two projects, on one Standard page. It still
lost a Summary to the "Brings" false positive before the checker correction. The correction
has separate truthfulness regression tests; the live result does not claim to validate it.

The private comparison files are not committed and no saved Draft was modified. These
are observations from one user's Job, not a guarantee for every provider or Fact Bank.

Measured content end: 169.7 mm before, 241.3 mm after development, against a 285 mm
usable bottom. Font size, spacing and margins were identical. Some whitespace remains;
no guarantee of edge-to-edge filling is intended.

Validation: all 877 backend tests pass locally. Five development integration cases cover
adoption, unavailable provider, timeout, unsupported output and Standard-page overflow;
they also verify one extra attempt, the shared deadline, a single saved version, and
removal of AI-supplied manual flags. Prompt-budget tests protect cited project groups.
