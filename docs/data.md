# Data provenance and reproduction

## Included

- `data/earnings/events.csv`: 15 annual release observations and their evidence flags.
- `data/earnings/forecasts.csv`: 21 collected estimates, including stale, mismatched and revised records.
- `data/earnings/sources.json`: original public URLs, source IDs, printed dates, PDF page references and download hashes where available.
- `data/earnings/direct_collection_log.csv`: 35 actual direct retrieval attempts, including seven errors. Paths are normalized for portability.
- `data/earnings/integrity.json`: unresolved dataset-wide requirements.
- `data/universe.csv`: provisional sector labels for the supplied universe.
- `data/corporate_actions.csv`: the supplied known action record; not a complete action history.
- `docs/evidence/`: derived historical research output. These files are not synthetic demo output.

## Kept outside the public package

Raw exchange price exports and downloaded publication bodies are not redistributed here. Local files under `data/prices/` and `source_cache/` are ignored by Git. Account screenshots and the user's actual contest portfolio are not part of this research repository.

To reproduce the original historical results, use the separate v7 research bundle's `data/prices/` directory, or obtain the exact equivalent source exports and compare their hashes against the original snapshot manifest. Different historical versions or corrections can change results. The default public demo needs no market data, credentials or API keys.

## Facts that require human review

The same numeric label can mean total net income, group-share profit (RNPG), recurring profit or a different fiscal period. A board-meeting date can differ from the first publication date. A modern PDF location and a download hash do not prove what was available historically. A report may have been revised before the event.

The collector verifies basic download success and records provenance; it does not solve those semantic problems. Do not set a verification flag to true merely to increase the signal count. Preserve prior rows and document a correction when evidence changes.

## Reproduction status

The real-market v7 study used a previously inspected price period. It has not received a clean prospective validation. The portfolio edition's synthetic demonstration tests software behavior only. Neither is a substitute for an untouched, adequately powered empirical test.
