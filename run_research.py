"""Reproduce the fixed earnings study using separately supplied market files."""

import argparse
import hashlib
import json
import platform
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from casa_alpha.config import ResearchConfig, load_config
from casa_alpha.events import evaluate_gate, load_inputs, study
from casa_alpha.portfolio import simulate
from casa_alpha.reporting import build_reports
from casa_momentum.config import Config
from casa_momentum.data import load_dataset

PROTOCOL_SHA256 = "f6cc4b68d34380c3ecd200c3a03eaa150d8fb345988f6a79705b3f63eab112b7"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-11-10")
    parser.add_argument("--config", default="earnings_config.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if not any((root / "data/prices").glob("*.csv")):
        raise SystemExit(
            "Market price files are not bundled with this portfolio edition. "
            "Run python run_demo.py for the synthetic demo, or supply the original "
            "exchange CSV files in data/prices/ to reproduce the historical study."
        )
    cfg = load_config(root / args.config)
    out = root / "outputs/earnings"
    out.mkdir(parents=True, exist_ok=True)
    protocol_hash = hashlib.sha256((root / "research/PROTOCOL.md").read_bytes()).hexdigest()
    if protocol_hash != PROTOCOL_SHA256:
        raise ValueError(
            "Protocol changed. Archive and identify a new experiment before proceeding."
        )
    integrity = json.loads((root / "data/earnings/integrity.json").read_text(encoding="utf-8"))
    integrity["frozen_parameter_set"] = asdict(cfg) == asdict(ResearchConfig())
    d = load_dataset(
        root,
        Config(
            corporate_actions_file="data/corporate_actions.csv",
            as_of=args.as_of,
            liquidity_sessions=cfg.liquidity_sessions,
        ),
    )
    events, forecasts = load_inputs(root)
    events = events[events.publication_date <= pd.Timestamp(args.as_of)].copy()
    if events.empty:
        raise ValueError("No collected events available by the selected as-of date")
    variants = {
        "base_10": (cfg, 0),
        "hold_20": (replace(cfg, hold_sessions=20), 0),
        "entry_plus_1": (cfg, 1),
        "double_cost": (
            replace(cfg, fee_rate=cfg.fee_rate * 2, slippage_rate=cfg.slippage_rate * 2),
            0,
        ),
    }
    results = {}
    for name, (c, delay) in variants.items():
        results[name] = study(d, events, forecasts, c, delay)
        results[name].to_csv(
            out / f"events_{name}.csv", index=False, float_format="%.10f", date_format="%Y-%m-%d"
        )
    base = results["base_10"]
    gate = evaluate_gate(base, results["double_cost"], integrity, cfg)
    portfolios = {}
    for name, mask in [("verified", base.verified_signal), ("case_study", base.case_study_signal)]:
        daily, trades, orders, inventory = simulate(d, base[mask], cfg)
        for label, df in [
            ("daily", daily),
            ("trades", trades),
            ("orders", orders),
            ("inventory", inventory),
        ]:
            df.to_csv(
                out / f"{name}_{label}.csv",
                index=False,
                float_format="%.10f",
                date_format="%Y-%m-%d",
            )
        portfolios[name] = dict(
            start_nav=cfg.initial_capital,
            end_nav=float(daily.nav.iloc[-1]),
            net_pnl=float(daily.nav.iloc[-1] - cfg.initial_capital),
            total_return=float(daily.nav.iloc[-1] / cfg.initial_capital - 1),
            max_drawdown=float(daily.drawdown.min()),
            buy_fills=int((trades.side == "BUY").sum()),
            sell_fills=int((trades.side == "SELL").sum()),
            fees_paid=float(trades.fees.sum()),
            max_gross_weight=float(daily.gross_weight.max()),
            open_positions_at_end=len(inventory),
            pending_exit_positions=int(daily.exit_positions_pending.iloc[-1]),
            stale_holding_days=int(daily.stale_holdings.ne("").sum()),
        )
    scenario = []
    for name, r in results.items():
        for cohort, col in [
            ("verified_signal", "verified_signal"),
            ("case_study_signal", "case_study_signal"),
            ("all_collected_events", None),
        ]:
            f = r if col is None else r[r[col]]
            for year in ["all"] + sorted(f.publication_date.dt.year.unique().tolist()):
                g = f if year == "all" else f[f.publication_date.dt.year == year]
                scenario.append(
                    dict(
                        scenario=name,
                        cohort=cohort,
                        release_year=year,
                        n_events=len(g),
                        n_issuers=g.ticker.nunique(),
                        n_complete=int(g.window_status.eq("complete").sum()),
                        n_with_sector_peer=int(g.net_sector_excess.notna().sum()),
                        mean_gross=g.gross_return.mean(),
                        mean_net=g.net_return.mean(),
                        mean_net_sector_excess=g.net_sector_excess.mean(),
                        mean_net_asof_sector_excess=g.net_asof_sector_excess.mean(),
                    )
                )
    pd.DataFrame(scenario).to_csv(out / "scenario_summary.csv", index=False, float_format="%.10f")
    d.audit.to_csv(out / "price_audit.csv", index=False)
    coverage = []
    for t in sorted(d.frames):
        f = base[base.ticker == t]
        coverage.append(
            dict(
                ticker=t,
                sector=d.metadata.loc[t, "sector"],
                collected_events=len(f),
                collected_forecasts=int(forecasts.ticker.eq(t).sum()),
                last_collected_result_date=f.publication_date.max() if len(f) else pd.NaT,
                verified_signals=int(f.verified_signal.sum()),
                action="RESEARCH_ONLY_NO_ORDER",
                missing="complete prior forecast revisions; historical publication timestamps; corporate actions"
                if len(f)
                else "dated results and comparable forecasts not yet collected",
            )
        )
    pd.DataFrame(coverage).to_csv(
        out / "research_watchlist.csv", index=False, date_format="%Y-%m-%d"
    )
    # Explicitly empty: neither the exploratory case study nor a failed research
    # gate can be mistaken for a live broker order.
    pd.DataFrame(columns=["date", "ticker", "side", "quantity", "limit_price", "reason"]).to_csv(
        out / "live_order_proposals.csv", index=False
    )
    manifest = {}
    tracked = (
        list((root / "data").rglob("*"))
        + list((root / "casa_alpha").glob("*.py"))
        + list((root / "casa_momentum").glob("*.py"))
        + list((root / "tests").glob("*.py"))
        + list((root / "scripts").glob("*.py"))
    )
    tracked += [
        root / args.config,
        root / "research/PROTOCOL.md",
        root / "research/IMPLEMENTATION_NOTES.md",
        root / "run_research.py",
        root / "collect_sources.py",
        root / "requirements.txt",
    ]
    for p in sorted(tracked):
        if p.is_file():
            manifest[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    summary = dict(
        research_as_of=args.as_of,
        last_price_session=str(d.calendar[-1].date()),
        first_price_session=str(d.calendar[0].date()),
        price_histories=len(d.frames),
        collected_events=len(base),
        collected_event_issuers=int(base.ticker.nunique()),
        forecast_records=len(forecasts),
        release_years=sorted(base.publication_date.dt.year.unique().tolist()),
        nominal_strong_beats=int(base.numeric_strong_beat.sum()),
        case_study_signals=int(base.case_study_signal.sum()),
        verified_signals=int(base.verified_signal.sum()),
        gate=gate,
        portfolio=portfolios,
        integrity=integrity,
        price_warnings=d.warnings,
        protocol_sha256=protocol_hash,
        configuration=asdict(cfg),
        runtime=dict(python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__),
    )
    (out / "run_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8"
    )
    (out / "input_manifest_sha256.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    build_reports(root, d, results, summary, cfg)
    print(
        f"{len(d.frames)} histories; {len(base)} result events; {len(forecasts)} forecast records."
    )
    print(
        f"Verified signals: {summary['verified_signals']}; exploratory case studies: {summary['case_study_signals']}."
    )
    print(f"Gate: {gate['status']}. New sleeve allocation: 0%. Live orders: 0.")
    print("Read RESEARCH_REPORT.html or RESEARCH_REPORT.md. Detailed ledgers: outputs/earnings/.")


if __name__ == "__main__":
    main()
