# Earnings drift protocol — fixed before event returns were computed

Research date: 10 November 2026. This is retrospective exploratory research, not a preregistered or untouched out-of-sample trial.

Main hypothesis: a positive earnings surprise relative to an earlier, separately archived analyst forecast predicts positive sector-relative returns after publication in Casablanca.

- Actual and forecast must refer to the same fiscal period, currency, units and accounting measure (RNPG, MAD millions). Do not substitute revenue growth, year-on-year earnings growth, reported profit for recurring profit, or a full-year estimate for a half-year result.
- Forecast must predate publication, be at most 270 calendar days old, and be traceable to an original dated document. Use the latest *collected* comparable forecast; incomplete revision coverage remains a limitation. No consensus claim from one broker.
- Signal: actual > 0, forecast > 0, and (actual - forecast)/abs(forecast) >= 10%. Threshold chosen before inspecting event returns. No parameter optimization.
- Entry: first observed tradable close strictly after the verified announcement/publication date, within three inferred exchange sessions. Unknown publication time is treated as end of day. A regulator upload date is not automatically the first announcement date; unresolved dates are research-only, excluded from the verified cohort.
- Exit: close of the tenth subsequent exchange session after entry (10 close-to-close intervals), deferred only for lack of trading. Flag deferrals and censored events. Do not drop a losing or censored observation silently.
- Eligibility uses only information at or before publication: 60 sessions, traded fraction >=80%, mean daily traded MAD >=1m, last close fresh <=3 sessions; suspicious historical moves require review.
- Peer benchmark: equal weight of other liquid supplied stocks in the same sector, selected at publication. Exclude peers whose collected earnings events fall in the event window; flag incomplete peer-news coverage. Hold the peer set fixed. No future return selection. Report both stock net return minus peer gross return (conservative hurdle) and stock gross minus peer gross.
- Costs: 0.77% fee and 0.10% slippage on each side, applied multiplicatively to buys and sells. Price-only returns; no claims of total-return alpha without complete corporate actions.
- Diagnostics: all matched events, strong-beat events, chronological release-year groups, 20-session robustness, entry one additional session later, double costs. These do not select a winning variant. Report issuer-cluster bootstrap uncertainty only when sample permits.
- Simulation: 1m MAD starting virtual capital; long only, whole shares, no leverage; 5% target per stock, 20% sector, 30% gross, 1% of lagged mean daily shares and 1% of realized daily shares fill caps, no replenishment after initial entry. Orders expire after 3 sessions. Exit queues remain until tradable; capital stays tied up. Drawdown at 5% queues liquidation next session, disables entries, and logs unfilled exits. No assumption that a stop guarantees a price.
- Deployment gate: at least 30 verified independent events, >=10 issuers, >=3 release years; positive net sector-relative mean, issuer-cluster bootstrap lower 95% bound >0, positive latest chronological group and double-cost mean. Data integrity, adjustment and forecast revision coverage must also pass. Minimum counts are a research screen, not proof of economic significance.
- If gate fails or evidence is incomplete: no capital allocated to this new sleeve. Produce a research watchlist and an empty live-order proposal. No broker integration or order submission.

Known inherited limits: supplied current-universe selection, incomplete corporate actions, provisional sectors, inferred market calendar, missing suspensions/auction order book, and a previously inspected price period. These cannot be repaired by statistics.
