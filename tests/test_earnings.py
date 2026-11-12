import unittest
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd

from casa_alpha.config import ResearchConfig
from casa_alpha.events import evaluate_gate, match_forecast, net_return, study, trade_window
from casa_alpha.portfolio import simulate


def dataset(n=100, tickers=("AAA", "BBB"), shares=100000):
    cal = pd.bdate_range("2024-01-01", periods=n)
    frames = {}
    for t in tickers:
        f = pd.DataFrame(index=cal)
        f["close"] = 100.0
        f["shares"] = float(shares)
        f["volume_mad"] = f.shares * f.close
        f["traded"] = True
        f["observed"] = True
        f["activity_known"] = True
        f["stale_sessions"] = 0.0
        f["split"] = 1.0
        f["dividend"] = 0.0
        f["return"] = 0.0
        frames[t] = f
    meta = pd.DataFrame(
        {"sector": ["sector"] * len(tickers), "active_from": pd.NaT, "active_to": pd.NaT},
        index=list(tickers),
    )
    return SimpleNamespace(calendar=cal, frames=frames, metadata=meta)


def event(d, ticker="AAA", date=None):
    return dict(
        event_id=ticker + "_FY2023",
        ticker=ticker,
        period="FY2023",
        metric="RNPG_reported",
        currency="MAD",
        unit="million",
        actual=120.0,
        publication_date=date if date is not None else d.calendar[65],
        first_publication_verified=True,
        actual_asof_verified=True,
        known_newer_revision_unresolved=False,
    )


def forecast(e, **kw):
    f = dict(
        forecast_id="F1",
        ticker=e["ticker"],
        period=e["period"],
        metric=e["metric"],
        currency=e["currency"],
        unit=e["unit"],
        forecast=100.0,
        forecast_date=pd.Timestamp(e["publication_date"]) - pd.Timedelta(days=20),
        original_dated_document=True,
        scope_verified=True,
    )
    f.update(kw)
    return f


def signal_frame(d, tickers=("AAA",)):
    return pd.DataFrame([{**event(d, t), "verified_signal": True} for t in tickers])


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.d = dataset()
        self.e = event(self.d)
        self.c = ResearchConfig()

    def test_future_and_same_day_forecasts_are_never_used(self):
        f = forecast(self.e, forecast_date=self.e["publication_date"])
        self.assertIsNone(match_forecast(self.e, pd.DataFrame([f]), self.c)[0])

    def test_latest_comparable_revision_selected_not_biggest_surprise(self):
        a = forecast(self.e)
        b = forecast(
            self.e,
            forecast_id="F2",
            forecast=119.0,
            forecast_date=self.e["publication_date"] - pd.Timedelta(days=1),
        )
        self.assertEqual(match_forecast(self.e, pd.DataFrame([a, b]), self.c)[0].forecast, 119.0)

    def test_wrong_period_and_wrong_accounting_measure_rejected(self):
        for change in (
            {"period": "FY2024"},
            {"metric": "net_income_consolidated"},
            {"currency": "EUR"},
            {"unit": "thousand"},
        ):
            with self.subTest(change=change):
                self.assertIsNone(
                    match_forecast(self.e, pd.DataFrame([forecast(self.e, **change)]), self.c)[0]
                )

    def test_forecast_age_boundary(self):
        for days, stale in [(270, False), (271, True)]:
            _, issues = match_forecast(
                self.e,
                pd.DataFrame(
                    [
                        forecast(
                            self.e,
                            forecast_date=self.e["publication_date"] - pd.Timedelta(days=days),
                        )
                    ]
                ),
                self.c,
            )
            self.assertEqual("forecast_too_old" in issues, stale)

    def test_scope_problem_and_known_revision_block_verified_signal(self):
        self.e["known_newer_revision_unresolved"] = True
        r = study(
            self.d,
            pd.DataFrame([self.e]),
            pd.DataFrame([forecast(self.e, scope_verified=False)]),
            self.c,
        ).iloc[0]
        self.assertTrue(r.numeric_strong_beat)
        self.assertFalse(r.verified_signal)
        self.assertFalse(r.case_study_signal)

    def test_tied_brokers_not_arbitrarily_selected(self):
        a = forecast(self.e)
        b = forecast(self.e, forecast_id="F2", forecast=111.0)
        self.assertIsNone(match_forecast(self.e, pd.DataFrame([a, b]), self.c)[0])


class EventTests(unittest.TestCase):
    def test_next_session_entry_and_ten_intervals(self):
        d = dataset()
        c = ResearchConfig()
        w = trade_window(d, "AAA", d.calendar[65], c)
        self.assertEqual(w["entry_index"], 66)
        self.assertEqual(w["exit_index"], 76)
        self.assertEqual(w["holding_intervals"], 10)

    def test_exit_deferred_when_no_trade(self):
        d = dataset()
        d.frames["AAA"].loc[d.calendar[76], "traded"] = False
        w = trade_window(d, "AAA", d.calendar[65], ResearchConfig())
        self.assertEqual(w["exit_index"], 77)
        self.assertEqual(w["exit_deferred_sessions"], 1)

    def test_no_future_fill_after_entry_expiry(self):
        d = dataset()
        d.frames["AAA"].loc[d.calendar[66:69], "traded"] = False
        self.assertEqual(
            trade_window(d, "AAA", d.calendar[65], ResearchConfig())["window_status"],
            "entry_expired",
        )

    def test_censored_event_retained_and_gate_fails(self):
        d = dataset(n=70)
        e = event(d)
        c = ResearchConfig()
        r = study(d, pd.DataFrame([e]), pd.DataFrame([forecast(e)]), c)
        self.assertEqual(len(r), 1)
        self.assertEqual(r.iloc[0].window_status, "censored_exit")
        gate = evaluate_gate(r, r, {}, c)
        self.assertFalse(gate["checks"]["no_missing_or_censored_verified_outcomes"])

    def test_exact_fee_arithmetic_and_break_even(self):
        c = ResearchConfig()
        be = (1 + c.fee_rate) * (1 + c.slippage_rate) / ((1 - c.fee_rate) * (1 - c.slippage_rate))
        self.assertAlmostEqual(net_return(be, c.fee_rate, c.slippage_rate), 0.0)
        self.assertLess(net_return(1.0, c.fee_rate, c.slippage_rate), -0.017)

    def test_peer_event_screening_explicit_not_signal_input(self):
        d = dataset()
        e = event(d)
        other = event(d, "BBB", d.calendar[70])
        c = ResearchConfig()
        r = study(
            d,
            pd.DataFrame([e, other]),
            pd.DataFrame([forecast(e), forecast(other, forecast_id="F2")]),
            c,
        )
        a = r[r.ticker == "AAA"].iloc[0]
        self.assertEqual(a.asof_peer_count, 1)
        self.assertEqual(a.peer_count, 0)
        self.assertTrue(a.verified_signal)
        self.assertTrue(np.isnan(a.net_sector_excess))


class PortfolioTests(unittest.TestCase):
    def test_cash_costs_and_realized_pnl_reconcile(self):
        d = dataset()
        c = ResearchConfig()
        daily, trades, _, inv = simulate(d, signal_frame(d), c)
        self.assertTrue(inv.empty)
        self.assertAlmostEqual(
            daily.nav.iloc[-1] - c.initial_capital, trades.realized_pnl.sum(), places=7
        )
        self.assertAlmostEqual(
            daily.cash.iloc[-1], c.initial_capital + trades.cash_change.sum(), places=7
        )
        self.assertTrue((daily.cash >= 0).all())

    def test_participation_caps_and_no_replenishment(self):
        d = dataset(shares=1000)
        c = ResearchConfig()
        daily, trades, orders, _ = simulate(d, signal_frame(d), c)
        buys = trades[trades.side == "BUY"]
        self.assertEqual(len(buys), 1)
        self.assertEqual(buys.shares.iloc[0], 10)
        self.assertTrue((trades.shares <= trades.lagged_adv_shares * c.participation_rate).all())
        self.assertTrue((trades.shares <= trades.day_shares * c.participation_rate).all())
        self.assertIn("REMAINDER_CANCELLED", orders.status.tolist())

    def test_realized_volume_can_only_reduce_fill(self):
        d = dataset()
        d.frames["AAA"].loc[d.calendar[66], "shares"] = 1000
        _, trades, _, _ = simulate(d, signal_frame(d), ResearchConfig())
        self.assertEqual(trades[trades.side == "BUY"].shares.iloc[0], 10)

    def test_exit_remains_queued_and_cash_tied_up(self):
        d = dataset()
        d.frames["AAA"].loc[d.calendar[76:79], "traded"] = False
        daily, trades, orders, _ = simulate(d, signal_frame(d), ResearchConfig())
        sells = trades[trades.side == "SELL"]
        self.assertEqual(sells.date.iloc[-1], d.calendar[79])
        self.assertEqual(daily.iloc[77].positions, 1)
        self.assertIn("EXIT_PENDING", orders.status.tolist())

    def test_drawdown_exits_next_session_not_same_close(self):
        d = dataset()
        d.frames["AAA"].loc[d.calendar[68] :, "close"] = 60.0
        c = replace(ResearchConfig(), drawdown_trigger=0.01)
        daily, trades, orders, _ = simulate(d, signal_frame(d), c)
        self.assertTrue(daily.iloc[68].kill_switch)
        self.assertFalse(((trades.side == "SELL") & (trades.date == d.calendar[68])).any())
        self.assertEqual(
            trades.loc[trades.reason == "drawdown_liquidation", "date"].iloc[0], d.calendar[69]
        )

    def test_price_drift_trim_is_delayed(self):
        d = dataset()
        d.frames["AAA"].loc[d.calendar[68] :, "close"] = 110.0
        _, trades, orders, _ = simulate(d, signal_frame(d), ResearchConfig())
        self.assertIn("TRIM_QUEUED", orders.status.tolist())
        self.assertEqual(
            trades.loc[trades.reason == "weight_breach_trim", "date"].iloc[0], d.calendar[69]
        )

    def test_position_sector_and_gross_caps(self):
        names = tuple("A" + str(i) for i in range(12))
        d = dataset(tickers=names)
        d.metadata["sector"] = ["X"] * 6 + ["Y"] * 6
        c = ResearchConfig()
        daily, trades, _, _ = simulate(d, signal_frame(d, names), c)
        first = daily.iloc[66]
        self.assertLessEqual(first.gross_weight, c.gross_cap + 1e-10)
        # Existing weights can drift a few basis points from costs of later fills;
        # such drift is logged and trimmed next session, never hidden.
        self.assertLess(first.max_sector_weight, c.sector_cap + 0.001)
        self.assertLess(first.max_stock_weight, c.stock_cap + 0.001)
        self.assertTrue((trades.shares.astype(int) == trades.shares).all())

    def test_empty_verified_portfolio_is_cash(self):
        d = dataset()
        empty = signal_frame(d).iloc[:0]
        daily, trades, orders, inv = simulate(d, empty, ResearchConfig())
        self.assertTrue(trades.empty)
        self.assertTrue(inv.empty)
        self.assertTrue((daily.nav == 1_000_000).all())

    def test_known_split_preserves_wealth_and_cost_basis(self):
        original = dataset()
        split = dataset()
        date = split.calendar[70]
        split.frames["AAA"].loc[date:, "close"] = 50.0
        split.frames["AAA"].loc[date, "split"] = 2.0
        c = ResearchConfig()
        a, ta, _, _ = simulate(original, signal_frame(original), c)
        b, tb, _, _ = simulate(split, signal_frame(split), c)
        self.assertAlmostEqual(a.nav.iloc[-1], b.nav.iloc[-1], places=7)
        self.assertEqual(tb[tb.side == "SELL"].shares.sum(), 2 * ta[ta.side == "SELL"].shares.sum())

    def test_future_data_does_not_change_completed_trade(self):
        a = dataset()
        b = dataset()
        b.frames["AAA"].loc[b.calendar[85] :, "close"] = 99999.0
        b.frames["AAA"].loc[b.calendar[85] :, "shares"] = 99999999.0
        c = ResearchConfig()
        _, ta, _, _ = simulate(a, signal_frame(a), c)
        _, tb, _, _ = simulate(b, signal_frame(b), c)
        pd.testing.assert_frame_equal(ta, tb)

    def test_sample_end_retains_unliquidated_inventory(self):
        d = dataset(n=70)
        daily, trades, orders, inv = simulate(d, signal_frame(d), ResearchConfig())
        self.assertEqual(len(inv), 1)
        self.assertEqual(int((trades.side == "SELL").sum()), 0)
        self.assertGreater(daily.holdings_value.iloc[-1], 0)


if __name__ == "__main__":
    unittest.main()
