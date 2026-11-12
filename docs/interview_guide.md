# Explain the project without hiding behind jargon

Use this as a study guide. Be accurate about the AI assistance and about which parts you personally reviewed, changed or debugged. Do not claim to have independently written components you cannot explain.

## A 45-second explanation

I investigated whether Moroccan companies that reported profit above an earlier expectation had useful returns afterward. I used Python to connect dated forecasts, financial releases and price data, then modeled trading fees and execution limits. The most important result was that an apparently attractive signal did not survive all the data checks. I kept uncertain records visible, separated one exploratory case from valid evidence, and did not claim to have found a profitable strategy. The project includes an offline demo and tests for timing, cash accounting and unavailable exits. I developed it with AI assistance and can explain the checks I have reviewed.

## Questions to answer closed-book

| Question | What a sound explanation should contain |
| --- | --- |
| What is a surprise? | Actual profit compared with an expectation that existed beforehand; growth from last year is a different calculation. |
| Why cannot you buy on the release date? | Without a release timestamp, the result may have appeared after trading ended. |
| Why select the latest earlier forecast? | Keeping an old pessimistic estimate can manufacture a larger apparent surprise. |
| What did the fees change? | The Akdital example went from about -2.15% price return to -3.84% net under the declared cost model. |
| What is look-ahead bias? | Making an earlier decision with information that only became available later. Give an example from the code. |
| Why do exit orders stay pending? | A price on a screen does not guarantee trading capacity. Cash stays tied up until a fill. |
| Why are the peer results imperfect? | Sector labels and peer announcements are incomplete; event screening uses future dates and is descriptive only. |
| Does the negative result disprove the hypothesis? | No. The usable verified sample was empty; absence of adequate evidence is not proof the effect cannot exist. |
| Why not change the holding period to 20 days? | It looked better only after inspection, and that same case underperformed its peer. Selecting it would need a new independent test. |
| What do tests prove? | Specific implementation behaviors and accounting identities, not profitable market predictions. |

## Three exercises that create your own evidence of understanding

1. Explain and manually calculate one buy, partial sale and final sale, including both sides' costs. Compare your answer with `trade_ledger.csv`.
2. Temporarily remove the strict forecast-date comparison in a local copy. Identify which test fails, explain why, then restore the rule. Do not leave the deliberate bug committed.
3. Choose one excluded original event. Read the linked source yourself, explain the exclusion in your own words, and add an evidence-backed review note or correction with a real Git commit.

For each exercise, keep a short note describing what you observed and learned. Honest, specific explanations will make the code much more useful in an interview than memorizing the README.
