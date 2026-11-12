# Implementation and evidence notes

The numerical protocol was fixed before event returns were computed. Its SHA-256 is `f6cc4b68d34380c3ecd200c3a03eaa150d8fb345988f6a79705b3f63eab112b7`. The following notes explain implementation choices, not tuned parameters.

## Data collection and publication dates

Source pages were retrieved from AMMC, issuers and Attijari Global Research. Tables and several image-only PDFs were checked visually. Direct HTTP downloads were also attempted for every URL in the 35-record source register; both successful hashes and errors are preserved. The original PDFs are not redistributed. The 64 price histories came from the user's current v6 archive.

Report-printed dates are not cryptographic evidence that a historical version was public on that day. The collector's download timestamp proves retrieval now, not availability then. Forecast revision coverage is incomplete. July 2025's bank report is hosted in a November 2025 directory; both precede the 2026 releases, but first-publication timing remains unarchived. Each CSV has separate original-document, scope, first-publication and revision flags.

For ATW FY2024 the issuer document is dated 24 February 2025 whereas AMMC's listing is 25 February; the dated document is the diagnostic anchor and the first-publication flag is false. Other unresolved records use labeled regulator-date proxies. A board date is never automatically substituted for publication. Only well-supported release dates are marked verified. Exact time is unknown and conservatively assumed end of day.

The BOA FY2024 figure was initially seeded from a later report. Its original image-only release was subsequently downloaded and visually checked: 3,427 million MAD on page 1. The source was corrected to the original release; the value, threshold and measured return did not change. The first-publication flag remains false. This data correction was made after the first diagnostic run and is disclosed rather than represented as preregistration.

## Match and uncertainty rules

Matching requires the same issuer, fiscal period, accounting metric, currency and unit. A forecast must precede the publication date; a same-day forecast is excluded when time is unavailable. Select the latest collected comparable document. Equal-date competing estimates are ambiguous, not averaged opportunistically. No forecast is fabricated from realized growth.

The age limit is inclusive at 270 calendar days. Numerical surprises retain rounded source precision; BCP headlines have a half-rounding-width of 50 million MAD. The engine does not treat source rounding as extra predictive precision. Neither BCP case is near the positive 10% threshold.

`verified_match` requires a usable original comparable forecast, verified scope, no unresolved known update, a supported publication date, an as-published actual and publication-date liquidity. `verified_signal` adds the 10% threshold. Neither implies that the full research gate passes: revision coverage, corporate actions and other dataset-wide requirements still apply.

`case_study_signal` is deliberately permissive about scope/date uncertainty, but rejects stale forecasts, known unresolved revisions, unmatched measures and liquidity failures. It is descriptive only and cannot produce live orders. This build has one such case, Akdital FY2024, and zero verified signals.

## Event return and peers

Entry is the first tradable close strictly after publication, within three exchange sessions. A 10-session holding period means exit index = entry index + 10. The one-session-delay diagnostic retains the same three-session entry deadline. Untradable exits defer without expiring; sample-end windows are censored rather than silently removed.

Raw close ratios are adjusted for supplied splits. Dividend information is incomplete, so this is a price-return study. The exact modeled net return is:

`(exit_price * split_factor / entry_price) * (1-slip)*(1-fee) / ((1+slip)*(1+fee)) - 1`

At fee=0.0077 and slip=0.001, the simple sum is about 1.74% round-trip friction. The exact break-even price gain is approximately 1.755%. This is before any unmodeled taxes or settlement restrictions.

Peer eligibility uses only information through publication. The frozen protocol also requested excluding peers with announcements inside the holding window. Those future event dates are not generally known when trading. Therefore the study labels this as an **ex-post descriptive event-screened benchmark**, not an investable sector portfolio. It separately reports an as-of liquidity peer set without future event exclusions. Neither peer series affects entry, sizing or exits. Missing constituents are not silently discarded; stale endpoints and absent peers are visible. Peer announcements are incompletely collected and inherited sector assignments are provisional. In the Akdital case both benchmarks contain only SOT.

All collected rows receive descriptive outcomes, including small beats, misses and excluded records. Their average is not the performance of the strong-surprise strategy. Event-window outliers are flagged without removing losses after observing them.

## Portfolio execution and risk

Desired share quantities use the previous close and previous NAV. The model can only reduce this quantity for current cash, weight and fill-cap constraints. It applies the tighter of 1% of lagged 60-session average shares and 1% of realized daily shares. The latter is an ex-post cap on a simulated fill, not foresight about daily volume. A close-price execution with fixed slippage is approximate; it does not establish auction availability.

The first partial entry cancels all remaining desired shares. There is no later top-up. Entry expires after three sessions. Exit orders and risk reductions can fill partially over multiple days and stay queued until filled. Inventory and cash remain on the ledger while orders are pending.

Whole shares, nonnegative cash and no leverage are enforced. Entry caps include cost-induced NAV reduction. Market movement and subsequent trade costs may still push an existing holding above a cap; the breach is logged and reductions are queued for the next session, never retrospectively filled. The illustrative Akdital maximum exposure was slightly over 5% before its next-session trim.

The portfolio drawdown trigger is observed after the close. It disables new entries and starts liquidation no earlier than the next session, subject to the same liquidity limits. It does not guarantee a maximum loss. Portfolio NAV marks shares at the last available close; stale valuations are flagged. Known split quantities and supplied dividends are handled, but completeness is not asserted.

The price sample was already inspected in earlier momentum/volume research. No untouched holdout, live execution, significance or total-return alpha is claimed. Statistical gates cannot fix these missing facts. The v7 runner never issues executable orders even if a future research gate passes.
