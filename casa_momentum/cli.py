import argparse
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

from .backtest import metrics, simulate
from .config import load_config
from .data import load_dataset
from .planning import target_worksheet
from .reporting import save_report
from .signals import allocate, make_schedule, snapshot
from .volatility import build_overlay
from .volume import core_weights, make_volume_plan, screen_volume


def _liquidation_return(result, record, cfg):
    """Close remaining shares at a hypothetical final-session sale after costs."""
    if record.get("status") == "insufficient_period":
        return float("nan")
    end = pd.Timestamp(record["end"])
    marked = result.positions[result.positions.date.eq(end)].value.sum()
    nav = result.equity.loc[end, "nav"]
    sale_cost = marked * (1 - (1 - cfg.slippage_rate) * (1 - cfg.fee_rate))
    return (1 + record["total_return"]) * (1 - sale_cost / nav) - 1


def run(config_path: Path, account_file=None, as_of=None, output=None):
    config_path = config_path.resolve()
    root = config_path.parent
    cfg = load_config(config_path)
    if as_of:
        cfg = replace(cfg, as_of=as_of)
    data = load_dataset(root, cfg)
    schedule = make_schedule(data, cfg)
    if not schedule:
        raise ValueError("No complete month-end signal window; provide longer price histories")
    base = simulate(data, cfg, schedule, "tsmom")
    passive = simulate(data, cfg, schedule, "passive")
    ref_cfg = replace(cfg, fee_rate=0.0, slippage_rate=0.0)
    # The optional overlay observes a cost-free version of this strategy.
    reference = simulate(data, ref_cfg, schedule, "tsmom_reference")
    overlay = build_overlay(reference, data.benchmark, schedule, cfg)
    results = {"tsmom": base, "passive": passive}
    if cfg.vm_mode != "off":
        results["tsmom_vm"] = simulate(data, cfg, schedule, "tsmom_vm", overlay.multipliers)
    stats = pd.DataFrame([metrics(r, data, cfg) for r in results.values()])
    # Report every configuration over the SAME sessions. These are exploratory
    # comparisons unless a future data period was set aside in advance.
    variants = {
        "original_12m": replace(
            cfg,
            signal_mode="single",
            lookback_months=12,
            exposure_mode="paper",
            min_trade_nav_fraction=0.0,
            min_trade_position_fraction=0.0,
            vm_mode="off",
        ),
        "selected_no_band": replace(
            cfg, min_trade_nav_fraction=0.0, min_trade_position_fraction=0.0
        ),
        "contest_12m": replace(cfg, signal_mode="single", lookback_months=12),
        "contest_12m_breadth": replace(
            cfg, signal_mode="single", lookback_months=12, breadth_scaling="linear"
        ),
        "contest_6m": replace(cfg, signal_mode="single", lookback_months=6),
        "contest_blend_3_6_12": replace(cfg, signal_mode="blend_3_6_12"),
        "contest_blend_breadth": replace(cfg, signal_mode="blend_3_6_12", breadth_scaling="linear"),
        "contest_12_minus_1": replace(cfg, signal_mode="12-1"),
        "selected": cfg,
    }
    schedules = {label: make_schedule(data, variant) for label, variant in variants.items()}
    complete = {label: d for label, d in schedules.items() if d}
    first_common_signal = max(min(d) for d in complete.values())
    later = data.calendar[data.calendar > first_common_signal]
    training_start = later[0] if len(later) else first_common_signal
    common_start = training_start
    training_end = None
    if cfg.holdout_start:
        requested_start = max(common_start, pd.Timestamp(cfg.holdout_start))
        observed_after = data.calendar[data.calendar >= requested_start]
        common_start = observed_after[0] if len(observed_after) else requested_start
        earlier = data.calendar[(data.calendar >= training_start) & (data.calendar < common_start)]
        training_end = earlier[-1] if len(earlier) else None
    comparison_rows = []
    training_rows = []
    for label, variant in variants.items():
        if not schedules[label]:
            comparison_rows.append({"variant": label, "status": "insufficient_signal_history"})
            continue
        result = base if label == "selected" else simulate(data, variant, schedules[label], label)
        record = metrics(result, data, variant, common_start)
        record.update(
            {
                "variant": label,
                "signal_mode": variant.signal_mode,
                "lookback_months": variant.lookback_months,
                "exposure_mode": variant.exposure_mode,
                "breadth_scaling": variant.breadth_scaling,
                "target_invested_weight": variant.target_invested_weight,
                "no_trade_nav_fraction": variant.min_trade_nav_fraction,
                "no_trade_position_fraction": variant.min_trade_position_fraction,
            }
        )
        comparison_rows.append(record)
        if training_end is not None:
            train_record = metrics(result, data, variant, training_start, training_end)
            train_record["variant"] = label
            training_rows.append(train_record)
    comparison = pd.DataFrame(comparison_rows)
    training = pd.DataFrame(training_rows)
    common = pd.DataFrame([metrics(r, data, cfg, common_start) for r in results.values()])
    sensitivity_rows = []
    if cfg.run_cost_sensitivity:
        for label, stress_cfg in (
            ("zero_cost", ref_cfg),
            ("configured_cost", cfg),
            (
                "double_cost",
                replace(cfg, fee_rate=cfg.fee_rate * 2, slippage_rate=cfg.slippage_rate * 2),
            ),
        ):
            r = (
                reference
                if label == "zero_cost"
                else base
                if label == "configured_cost"
                else simulate(data, stress_cfg, schedule, "tsmom")
            )
            record = metrics(r, data, stress_cfg)
            record.update(
                {
                    "case": label,
                    "fee_rate": stress_cfg.fee_rate,
                    "slippage_rate": stress_cfg.slippage_rate,
                }
            )
            sensitivity_rows.append(record)
    sensitivity = pd.DataFrame(sensitivity_rows)
    # Two fixed tactical horizons; the later period is a chronological check,
    # not an untouched holdout because prior project iterations inspected it.
    volume_screen = screen_volume(data, cfg)
    capped_core = simulate(data, cfg, core_weights(schedule, data, cfg), "core_half_budget")
    volume_runs, volume_rows, volume_plans = {}, [], {}
    phases = [("earlier", training_start, training_end), ("later", common_start, data.calendar[-1])]
    for phase, start, end in phases:
        if end is None or end < start:
            continue
        reference = {}
        for label, result in (("core_full", base), ("core_half_budget", capped_core)):
            record = metrics(result, data, cfg, start, end)
            record.update(
                {
                    "phase": phase,
                    "variant": label,
                    "hold_sessions": None,
                    "planned_entries": 0,
                    "buy_fills": 0,
                    "sell_fills": 0,
                    "exit_adjusted_return": _liquidation_return(result, record, cfg),
                }
            )
            volume_rows.append(record)
            reference[label] = record
        for hold in (5, 10):
            plan = make_volume_plan(
                data, cfg, schedule, volume_screen, hold, entry_start=start, entry_end=end
            )
            label = f"core_plus_volume_{hold}d"
            result = simulate(data, cfg, plan.schedule, f"{label}_{phase}")
            volume_runs[f"{label}_{phase}"] = result
            volume_plans[f"{label}_{phase}"] = plan.entries
            record = metrics(result, data, cfg, start, end)
            record.update(
                {
                    "phase": phase,
                    "variant": label,
                    "hold_sessions": hold,
                    "planned_entries": len(plan.entries),
                    "buy_fills": int(
                        (
                            (result.trades.date.ge(start))
                            & (result.trades.date.le(end))
                            & result.trades.side.eq("BUY")
                        ).sum()
                    ),
                    "sell_fills": int(
                        (
                            (result.trades.date.ge(start))
                            & (result.trades.date.le(end))
                            & result.trades.side.eq("SELL")
                        ).sum()
                    ),
                    "exit_adjusted_return": _liquidation_return(result, record, cfg),
                }
            )
            for baseline in ("core_full", "core_half_budget"):
                record[f"vs_{baseline}_after_exit_cost"] = (
                    record["exit_adjusted_return"] - reference[baseline]["exit_adjusted_return"]
                )
            volume_rows.append(record)
    volume_comparison = pd.DataFrame(volume_rows)
    earlier = volume_comparison[
        (volume_comparison.phase == "earlier") & volume_comparison.hold_sessions.notna()
    ]
    passing = earlier[
        (earlier.vs_core_full_after_exit_cost > 0)
        & (earlier.vs_core_half_budget_after_exit_cost > 0)
    ]
    selected_hold = (
        int(
            passing.sort_values(
                ["vs_core_full_after_exit_cost", "hold_sessions"], ascending=[False, True]
            )
            .iloc[0]
            .hold_sessions
        )
        if not passing.empty
        else None
    )
    checked = (
        volume_comparison[
            (volume_comparison.phase == "later") & volume_comparison.hold_sessions.eq(selected_hold)
        ]
        if selected_hold
        else pd.DataFrame()
    )
    later_pass = (
        not checked.empty
        and checked.iloc[0].vs_core_full_after_exit_cost > 0
        and checked.iloc[0].vs_core_half_budget_after_exit_cost > 0
    )
    volume_decision = {
        "selection_rule": "Select 5 or 10 sessions using earlier exit-adjusted excess over BOTH the full core and the half-budget core; use the later period only as a chronological diagnostic.",
        "selected_on_earlier_period": selected_hold,
        "later_check_passed": bool(later_pass),
        "status": "research_candidate_manual_review_required"
        if later_pass
        else "drop_automatic_volume_sleeve",
        "later_period_is_untouched": False,
        "news_and_cross_trade_filter_backtested": False,
    }
    latest = schedule[max(schedule)].copy()
    latest["target_weight"] = allocate(latest, cfg)
    diagnostic = snapshot(data, cfg, data.calendar[-1], monthly=False)
    worksheet, plan_info = target_worksheet(
        data,
        cfg,
        latest,
        overlay.multipliers[max(schedule)],
        Path(account_file).resolve() if account_file else None,
    )
    output_path = Path(output).resolve() if output else root / cfg.output_dir
    manifest = save_report(
        output_path,
        cfg,
        data,
        schedule,
        latest,
        diagnostic,
        results,
        stats,
        common,
        overlay,
        worksheet,
        plan_info,
        sensitivity,
        comparison,
        common_start,
        training,
        training_start,
        training_end,
        volume_screen,
        volume_comparison,
        volume_runs,
        volume_plans,
        volume_decision,
    )
    print(f"Loaded {len(data.frames)} equities: {', '.join(sorted(data.frames))}")
    print(f"Actual data cutoff: {data.calendar[-1].date()} | mode: {cfg.return_mode}")
    print(f"Latest completed-month signal: {max(schedule).date()}")
    print(
        f"Eligible at latest month-end: {int(latest.eligible.sum())}; positive: "
        f"{int((latest.eligible & (latest.signal_score > 0)).sum())}"
    )
    print(
        latest[latest.target_weight > 0][["ticker", "signal_score", "target_weight"]].to_string(
            index=False
        )
    )
    print(f"Report: {output_path / 'report.html'}")
    print(
        f"Volume sleeve: {volume_decision['status']} | selected on earlier sample: {selected_hold}"
    )
    print("No orders submitted. Read data limitations before using target estimates.")
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Multi-equity Casablanca time-series momentum research"
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="JSON settings; relative paths resolve beside this file",
    )
    parser.add_argument("--as-of", help="ISO date; ignore later observations")
    parser.add_argument("--output", help="Override output directory")
    parser.add_argument(
        "--account", help="Actual cash, settled holdings and pending orders JSON (optional)"
    )
    args = parser.parse_args()
    try:
        run(Path(args.config), args.account, args.as_of, args.output)
    except (ValueError, FileNotFoundError, KeyError) as error:
        print(f"Input error: {error}", file=sys.stderr)
        sys.exit(2)
