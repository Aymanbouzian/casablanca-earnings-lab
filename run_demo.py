"""Run the research engine on explicitly synthetic, deterministic examples.

This demonstrates software behavior, not historical returns or investment skill.
The real Casablanca snapshot is documented separately in docs/case_study.md.
"""

import argparse
import base64
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from casa_alpha.config import ResearchConfig
from casa_alpha.events import evaluate_gate, study
from casa_alpha.portfolio import simulate
from casa_momentum.data import Dataset


def make_demo_data(seed=7051):
    """Six fictional issuers cover valid, revised, invalid and censored cases."""
    rng = np.random.default_rng(seed)
    calendar = pd.bdate_range("2024-01-02", periods=180)
    names = [f"DEMO_{letter}" for letter in "ABCDEF"]
    metadata = pd.DataFrame(
        {
            "sector": ["Software", "Software", "Industry", "Industry", "Software", "Industry"],
            "active_from": pd.NaT,
            "active_to": pd.NaT,
        },
        index=names,
    )
    frames = {}
    for i, ticker in enumerate(names):
        frame = pd.DataFrame(index=calendar)
        frame["close"] = (100 + i * 15) * np.exp(rng.normal(0, 0.006, len(calendar)).cumsum())
        frame["shares"] = rng.integers(40_000, 70_000, len(calendar)).astype(float)
        frame["traded"] = True
        frame["observed"] = True
        frame["activity_known"] = True
        frame["split"] = 1.0
        frame["dividend"] = 0.0
        if ticker == "DEMO_A":
            # Its scheduled exit has no trading; liquidation must remain queued.
            frame.loc[calendar[76:78], "shares"] = 0.0
            frame.loc[calendar[76:78], "traded"] = False
            frame.loc[calendar[76:78], "close"] = frame.loc[calendar[75], "close"]
        frame["volume_mad"] = frame.close * frame.shares
        frame["return"] = frame.close.pct_change().fillna(0.0)
        last_trade = pd.Series(
            np.where(frame.traded, np.arange(len(frame)), np.nan), index=calendar
        ).ffill()
        frame["stale_sessions"] = np.arange(len(frame)) - last_trade
        frames[ticker] = frame

    events, forecasts = [], []
    for ticker, index in zip(names, [65, 85, 105, 125, 145, 178]):
        publication = calendar[index]
        event = {
            "event_id": f"{ticker}_FY2023",
            "ticker": ticker,
            "period": "FY2023",
            "metric": "RNPG_reported",
            "currency": "MAD",
            "unit": "million",
            "actual": 120.0,
            "publication_date": publication,
            "first_publication_verified": True,
            "actual_asof_verified": True,
            "known_newer_revision_unresolved": False,
            "provenance": "FICTIONAL DEMONSTRATION; not an actual issuer",
        }
        forecast = {
            "forecast_id": f"{ticker}_forecast_1",
            **{k: event[k] for k in ["ticker", "period", "metric", "currency", "unit"]},
            "forecast": 100.0,
            "forecast_date": publication - pd.Timedelta(days=30),
            "original_dated_document": True,
            "scope_verified": True,
            "provenance": "FICTIONAL DEMONSTRATION; no real analyst report",
        }
        if ticker == "DEMO_B":
            forecasts.append(
                {
                    **forecast,
                    "forecast_id": f"{ticker}_forecast_2",
                    "forecast": 118.0,
                    "forecast_date": publication - pd.Timedelta(days=5),
                }
            )
        if ticker == "DEMO_C":
            forecast["metric"] = "net_income_consolidated"
        if ticker == "DEMO_D":
            forecast["forecast_date"] = publication + pd.Timedelta(days=1)
        if ticker == "DEMO_E":
            forecast["scope_verified"] = False
        events.append(event)
        forecasts.append(forecast)

    dataset = Dataset(
        frames=frames,
        calendar=calendar,
        metadata=metadata,
        benchmark=pd.Series(1.0, index=calendar),
        audit=pd.DataFrame(),
        sources=[{"generator": "make_demo_data", "seed": seed, "synthetic": True}],
        warnings=["All demo prices, companies, results and forecasts are synthetic."],
    )
    return dataset, pd.DataFrame(events), pd.DataFrame(forecasts)


def run_demo(output_dir, seed=7051):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = ResearchConfig()
    dataset, events, forecasts = make_demo_data(seed)
    observations = study(dataset, events, forecasts, cfg)
    gate = evaluate_gate(observations, observations, {"real_market_data": False}, cfg)
    signals = observations[observations.verified_signal]
    daily, trades, orders, inventory = simulate(dataset, signals, cfg)

    series = pd.concat(
        [
            frame.assign(ticker=ticker).rename_axis("date").reset_index()
            for ticker, frame in dataset.frames.items()
        ],
        ignore_index=True,
    )
    outputs = {
        "synthetic_prices": series,
        "synthetic_events": events,
        "synthetic_forecasts": forecasts,
        "event_audit": observations,
        "daily_ledger": daily,
        "trade_ledger": trades,
        "order_log": orders,
        "remaining_inventory": inventory,
    }
    for name, frame in outputs.items():
        frame.to_csv(
            output_dir / f"{name}.csv", index=False, date_format="%Y-%m-%d", float_format="%.10f"
        )
    summary = {
        "synthetic": True,
        "purpose": "Software demonstration only; no historical performance claim",
        "seed": seed,
        "fictional_issuers": len(dataset.frames),
        "events": len(events),
        "fixture_verified_signals": int(observations.verified_signal.sum()),
        "censored_exit_events": int(observations.window_status.eq("censored_exit").sum()),
        "exit_pending_log_entries": int(orders.status.eq("EXIT_PENDING").sum()),
        "remaining_positions": len(inventory),
        "gate_status": gate["status"],
        "live_orders_enabled": False,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    fig, ax = plt.subplots(figsize=(9, 3.8), layout="constrained")
    ax.plot(daily.date, daily.nav, color="#157f78", linewidth=2)
    ax.set_title(
        "Synthetic demo: daily cash-and-position accounting", loc="left", fontweight="bold"
    )
    ax.set_ylabel("Fictional portfolio value (MAD)")
    ax.grid(alpha=0.2)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.text(
        0.02,
        0.05,
        "SYNTHETIC DATA - NO INVESTMENT EVIDENCE",
        transform=ax.transAxes,
        fontsize=9,
        color="#a34431",
    )
    fig.savefig(output_dir / "demo_nav.png", dpi=130)
    plt.close(fig)
    encoded = base64.b64encode((output_dir / "demo_nav.png").read_bytes()).decode()
    audit = observations[
        ["ticker", "surprise", "verified_signal", "issues", "window_status"]
    ].copy()
    audit["surprise"] = audit.surprise.map(lambda x: "n/a" if pd.isna(x) else f"{x:.1%}")
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Casablanca Earnings Lab - Synthetic Demo</title><style>"
        "body{font:16px/1.6 system-ui;max-width:1050px;margin:35px auto;padding:20px;color:#17384b}"
        "table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}"
        "th{background:#17384b;color:white}img{max-width:100%}.status{padding:15px;background:#fff0e8;color:#9b402b;font-weight:bold}"
        '</style><h1>Casablanca Earnings Lab</h1><p class="status">SYNTHETIC DEMO - NO REAL-MARKET RETURNS</p>'
        "<p>This offline run exercises forecast revisions, accounting mismatches, future information, liquidity queues and an unfinished holding period. "
        "The real Casablanca research case is documented separately in docs/case_study.md.</p>"
        f'<img src="data:image/png;base64,{encoded}" alt="Synthetic accounting demonstration">'
        "<h2>Explainable event decisions</h2>"
        + audit.to_html(index=False, escape=True, border=0)
        + "<p>Open the accompanying CSV files to inspect every input, fill, pending exit and remaining position. No live orders are produced.</p></html>"
    )
    (output_dir / "report.html").write_text(page, encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).resolve().parent / "outputs/demo"
    )
    parser.add_argument("--seed", type=int, default=7051)
    args = parser.parse_args()
    summary = run_demo(args.output, args.seed)
    print(json.dumps(summary, indent=2))
    print(f"Open {args.output / 'report.html'}")


if __name__ == "__main__":
    main()
