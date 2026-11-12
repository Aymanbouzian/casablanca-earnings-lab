"""Integration checks for the public demonstration, independent of market files."""

import json
import tempfile
import unittest
from pathlib import Path

from casa_alpha.config import ResearchConfig
from casa_alpha.events import study
from run_demo import make_demo_data, run_demo


class DemoTests(unittest.TestCase):
    def test_fixture_exposes_decisions_and_retains_censoring(self):
        data, events, forecasts = make_demo_data()
        audit = study(data, events, forecasts, ResearchConfig()).set_index("ticker")
        self.assertTrue(audit.loc["DEMO_A", "verified_signal"])
        self.assertEqual(audit.loc["DEMO_A", "exit_deferred_sessions"], 2)
        self.assertEqual(audit.loc["DEMO_B", "forecast"], 118)
        self.assertFalse(audit.loc["DEMO_B", "verified_signal"])
        self.assertFalse(audit.loc["DEMO_C", "verified_signal"])
        self.assertFalse(audit.loc["DEMO_D", "verified_signal"])
        self.assertFalse(audit.loc["DEMO_E", "verified_signal"])
        self.assertEqual(audit.loc["DEMO_F", "window_status"], "censored_exit")

    def test_offline_run_is_reproducible_and_never_a_live_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = run_demo(root / "first")
            second = run_demo(root / "second")
            self.assertEqual(first, second)
            self.assertTrue(first["synthetic"])
            self.assertFalse(first["live_orders_enabled"])
            self.assertEqual(first["gate_status"], "REJECT_FOR_DEPLOYMENT")
            self.assertEqual(first["remaining_positions"], 1)
            for filename in ["trade_ledger.csv", "daily_ledger.csv", "event_audit.csv"]:
                self.assertEqual(
                    (root / "first" / filename).read_bytes(),
                    (root / "second" / filename).read_bytes(),
                )
            saved = json.loads((root / "first/summary.json").read_text())
            self.assertEqual(saved, first)


if __name__ == "__main__":
    unittest.main()
