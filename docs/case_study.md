# Case study: testing an earnings-surprise hypothesis in Casablanca

## Question

After a company reports profit above an expectation available beforehand, does its share price continue to outperform comparable liquid stocks over the following ten exchange sessions, after trading costs?

The market setting made the question practical: a short educational trading contest, meaningful per-trade fees and limited historical analyst coverage. The aim was to turn an idea into a test that could reject it.

## Data and method

The research used 64 supplied stock histories and collected 15 annual-result events across eight issuers, with 21 forecast records. Sources include AMMC, company releases and Attijari Global Research. Twenty-eight of 35 registered URLs downloaded successfully; errors were retained. The dataset is a feasibility sample, not exhaustive market coverage.

The main rule was fixed before inspecting these event returns: a positive reported RNPG surprise of at least 10%, using a comparable forecast no more than 270 calendar days old. Publication date, fiscal period, units and accounting definition had to match. Entry began at the first tradable close after publication; exit was ten subsequent exchange sessions later. Fees were 0.77% and slippage 0.10% per side.

The simulator used virtual capital of 1 million MAD, whole shares, no leverage, per-name/sector/gross limits, participation caps, expiring entries and persistent exit queues. Risk decisions observed at a close could execute only from the next session.

## Three decisions that mattered

1. **Do not call growth a surprise.** A company's profit can grow substantially yet still fall below an earlier forecast. Forecast matching uses comparable levels, not year-on-year growth.
2. **Do not keep an obsolete estimate because it produces a bigger signal.** Marsa Maroc's November estimate appeared to imply a strong beat, but a newer February document existed with a different earnings basis. That comparison remained unresolved and was blocked.
3. **Do not force an attractive performance story.** Akdital's apparent 14.13% gap was against a management-plan-derived pre-money estimate. It remained an exploratory observation because scope equivalence and intervening revisions were unresolved.

## Results

No fully verified qualifying signal remained. The exploratory Akdital trade entered on 21 March 2025 at 1,256 MAD and exited on 8 April at 1,229 MAD, producing a 2.15% price loss and a **3.84% loss after modeled costs**. Entering one session later increased the net loss to 8.28%.

The pre-specified 20-session diagnostic made 7.90% net, but underperformed its one eligible peer by 7.54 percentage points. It was not promoted into the main strategy after the result was observed.

The risk-constrained exploratory ledger finished at **998,149.43 MAD**, a loss of **1,850.57 MAD**. Its small total-account loss reflected a small position and mostly idle virtual cash; it is not evidence of a strong risk-adjusted strategy.

## Limits and conclusion

This investigation did not establish an earnings alpha. It also did not prove that earnings drift is absent from Morocco: the verified sample was empty and the collected panel was small. Corporate actions, revisions, historical constituents, publication timing and peer announcements remain incomplete.

The peer comparison also needs careful interpretation. Excluding peers with later announcements is an ex-post descriptive control; it is not a benchmark an investor could necessarily select at publication. A second comparison preserves the publication-date liquid peer set. Neither affects trade decisions.

The defensible result is an auditable research system and a decision to allocate zero to the unvalidated sleeve. A broader prospective dataset is the next research step.

## Inspect the evidence

- [Original report](research_report.pdf)
- [Every collected event and its exclusion reason](evidence/events_base_10.csv)
- [Diagnostics](evidence/scenario_summary.csv)
- [Portfolio fills](evidence/case_study_trades.csv)
- [Source register](../data/earnings/sources.json)
- [Frozen protocol](../research/PROTOCOL.md)

Research snapshot: 10 November 2026. Portfolio presentation: 12 November 2026. AI assistance was used in collection, coding and documentation; this presentation does not claim a profitable live trading record.
