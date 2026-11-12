# Validation record

Checked locally on **12 November 2026** using Linux and Python **3.12.14**.
Direct dependencies were NumPy **2.3.5**, pandas **2.2.3**, Matplotlib **3.10.8**
and Ruff **0.14.4**. The requirements files pin these direct dependencies;
this is not a complete lock of every transitive dependency.

| Check | Observed outcome |
| --- | --- |
| `python -m unittest discover -s tests -v` | **72 tests passed** |
| `ruff check .` | Passed |
| `ruff format --check .` | All 23 Python files formatted |
| `python run_demo.py` without market files | Completed; HTML, CSV, PNG and JSON outputs written |
| Demo repeated with the same seed | Summary and selected CSV outputs identical; checked by integration test |
| Synthetic unavailable exit | Two pending-exit records retained before the fill |
| Synthetic sample end | One position retained as unliquidated inventory |
| Historical study rerun with the original local price archive | Seven event/diagnostic/trade/order CSVs exactly matched the original v7 output; summary counts, portfolio metrics and deployment gate unchanged |

Read the full [test log](validation/test_results.txt). The 72 tests comprise
23 earnings tests, 2 demo integration tests and 47 inherited infrastructure
regression tests. Test counts are not statistical evidence of investment skill.

The original market files were made available only for the historical regression
check and removed from this public package afterward. The archived research
evidence remains under `docs/evidence/`; the runnable demonstration generates
fictional data and labels it explicitly.

GitHub Actions is configured for Linux and Windows with Python 3.12. **Hosted
CI and the Windows launcher have not been executed here.** Inspect the actual
Actions result after publication before claiming those platforms pass.

The research protocol remained unchanged, with SHA-256:

```text
f6cc4b68d34380c3ecd200c3a03eaa150d8fb345988f6a79705b3f63eab112b7
```
