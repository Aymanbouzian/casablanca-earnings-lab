"""Synthetic tests for the short-horizon sleeve and its shared execution path."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from casa_momentum.backtest import simulate
from casa_momentum.config import Config
from casa_momentum.data import load_dataset
from casa_momentum.volume import core_weights, make_volume_plan, screen_volume


class VolumeSleeveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        folder = self.root / "data/prices"
        folder.mkdir(parents=True)
        self.dates = pd.bdate_range("2025-01-02", periods=270)
        self.spike_i = 240
        self.cfg = Config(
            metadata_file=None,
            min_vol_observations=30,
            min_average_volume_mad=1_000_000,
            participation_rate=1.0,
            run_cost_sensitivity=False,
        )
        self.path = folder / "TEST.csv"
        self.prices = np.full(len(self.dates), 100.0)
        self.prices[self.spike_i :] = 101.0
        self.volumes = np.full(len(self.dates), 20_000)
        self.volumes[self.spike_i] = 60_000
        self._write()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self):
        pd.DataFrame(
            {
                "date": self.dates.strftime("%Y-%m-%d"),
                "ticker": "TEST",
                "close": self.prices,
                "shares": self.volumes,
                "volume_mad": self.prices * self.volumes,
            }
        ).to_csv(self.path, index=False)

    def _inputs(self):
        data = load_dataset(self.root, self.cfg)
        table = pd.DataFrame({"eligible": [False], "sector": ["UNCLASSIFIED"]}, index=["TEST"])
        core = {self.dates[230]: table}
        return data, core, screen_volume(data, self.cfg)

    def test_signal_uses_prior_20_and_ignores_future_changes(self):
        data, _, screen = self._inputs()
        day = screen[(screen.date == self.dates[self.spike_i]) & screen.ticker.eq("TEST")].iloc[0]
        self.assertEqual(day.prior_20_max_shares, 20_000)
        self.assertEqual(day.traded_shares, 60_000)
        self.assertTrue(day.signal)
        self.assertEqual(day.manual_news_verified, "")
        self.volumes[self.spike_i + 1 :] *= 5
        self.prices[self.spike_i + 1 :] *= 2
        self._write()
        new = screen_volume(load_dataset(self.root, self.cfg), self.cfg)
        changed = new[(new.date == self.dates[self.spike_i]) & new.ticker.eq("TEST")].iloc[0]
        self.assertEqual(day.volume_ratio, changed.volume_ratio)
        self.assertEqual(day.daily_price_return, changed.daily_price_return)

    def test_five_and_ten_session_exit_and_both_fees(self):
        data, core, screen = self._inputs()
        for horizon in (5, 10):
            plan = make_volume_plan(data, self.cfg, core, screen, horizon)
            self.assertEqual(len(plan.entries), 1)
            r = simulate(data, self.cfg, plan.schedule, f"volume_{horizon}d")
            self.assertEqual(r.trades.side.tolist(), ["BUY", "SELL"])
            self.assertEqual(
                r.trades.date.tolist(),
                [self.dates[self.spike_i + 1], self.dates[self.spike_i + horizon + 1]],
            )
            self.assertGreater(r.trades.fee.sum(), 0)
            self.assertGreater(r.trades.slippage_cost.sum(), 0)
            self.assertLess(r.equity.nav.iloc[-1], self.cfg.initial_capital)
            self.assertTrue((r.trades.date > r.trades.decision_date).all())
            self.assertLessEqual(r.equity.max_stock_weight.max(), self.cfg.hard_max_stock_weight)

    def test_negative_price_or_known_action_blocks_signal(self):
        self.prices[self.spike_i :] = 99.0
        self._write()
        data, _, screen = self._inputs()
        self.assertFalse(screen.loc[screen.date.eq(self.dates[self.spike_i]), "signal"].iloc[0])
        self.prices[self.spike_i :] = 101.0
        self._write()
        f = pd.read_csv(self.path)
        f["dividend"] = 0.0
        f.loc[self.spike_i, "dividend"] = 1.0
        f.to_csv(self.path, index=False)
        data = load_dataset(self.root, self.cfg)
        screen = screen_volume(data, self.cfg)
        self.assertFalse(screen.loc[screen.date.eq(self.dates[self.spike_i]), "signal"].iloc[0])

    def test_later_signal_period_does_not_change_earlier_core_book(self):
        data, core, screen = self._inputs()
        start = self.dates[self.spike_i]
        plan = make_volume_plan(data, self.cfg, core, screen, 5, entry_start=start)
        capped = simulate(data, self.cfg, core_weights(core, data, self.cfg), "core_only")
        combined = simulate(data, self.cfg, plan.schedule, "combined")
        assert_frame_equal(
            capped.equity.loc[: self.dates[self.spike_i - 1]],
            combined.equity.loc[: self.dates[self.spike_i - 1]],
        )
        self.assertTrue((plan.entries.date >= start).all())

    def test_core_and_tactical_names_share_stock_and_sector_caps(self):
        data, _, _ = self._inputs()
        names = ["CORE", "VOL1", "VOL2", "VOL3", "VOL4"]
        for name in names:
            data.frames[name] = data.frames["TEST"].copy()
        data.metadata = pd.concat(
            [
                data.metadata,
                pd.DataFrame(
                    {
                        "sector": ["Mining"] * len(names),
                        "active_from": [pd.NaT] * len(names),
                        "active_to": [pd.NaT] * len(names),
                    },
                    index=names,
                ),
            ]
        )
        core_table = pd.DataFrame(
            {
                "eligible": [True],
                "signal_score": [1.0],
                "annual_volatility": [0.2],
                "sector": ["Mining"],
            },
            index=["CORE"],
        )
        date = self.dates[self.spike_i]
        signals = pd.DataFrame(
            {
                "signal": [True] * 4,
                "date": [date] * 4,
                "ticker": names[1:],
                "sector": ["Mining"] * 4,
                "volume_ratio": [4.0, 3.0, 2.0, 1.0],
            }
        )
        plan = make_volume_plan(data, self.cfg, {self.dates[230]: core_table}, signals, 5)
        targets = plan.schedule[date]
        self.assertAlmostEqual(targets["CORE"], 0.08)
        self.assertLessEqual(targets.sum(), self.cfg.max_sector_weight + 1e-9)
        self.assertLessEqual(targets.max(), self.cfg.target_max_stock_weight + 1e-9)
        self.assertEqual(len(plan.entries), 3)
        self.assertAlmostEqual(targets["VOL3"], 0.06)


if __name__ == "__main__":
    unittest.main()
