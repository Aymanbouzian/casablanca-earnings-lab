"""Point-in-time matching, explicit exclusions and fixed event windows.

The event-screened peer comparison is an ex-post descriptive control, not an
investable index: future peer releases are not known at signal formation.
An additional peer comparison uses only the publication-date liquidity set.
Neither peer return is used to select or size trades.
"""

import numpy as np
import pandas as pd

KEYS = ("ticker", "period", "metric", "currency", "unit")
BOOL_EVENT = (
    "first_publication_verified",
    "actual_asof_verified",
    "known_newer_revision_unresolved",
)


def boolean_column(s):
    out = s.astype(str).str.lower().map({"true": True, "false": False, "1": True, "0": False})
    if out.isna().any():
        raise ValueError(f"Invalid boolean in {s.name}")
    return out.astype(bool)


def load_inputs(root):
    events = pd.read_csv(root / "data/earnings/events.csv").fillna("")
    forecasts = pd.read_csv(root / "data/earnings/forecasts.csv").fillna("")
    for f, idcol in ((events, "event_id"), (forecasts, "forecast_id")):
        if f[idcol].duplicated().any():
            raise ValueError(f"Duplicate {idcol}")
        if f[list(KEYS)].eq("").any().any():
            raise ValueError("Missing match key")
    events["publication_date"] = pd.to_datetime(
        events.publication_date, format="%Y-%m-%d", errors="raise"
    )
    forecasts["forecast_date"] = pd.to_datetime(
        forecasts.forecast_date, format="%Y-%m-%d", errors="raise"
    )
    for col in BOOL_EVENT:
        events[col] = boolean_column(events[col])
    for col in ("scope_verified", "original_dated_document"):
        forecasts[col] = boolean_column(forecasts[col])
    for f, col in ((events, "actual"), (forecasts, "forecast")):
        f[col] = pd.to_numeric(f[col], errors="raise")
        if not np.isfinite(f[col]).all():
            raise ValueError(f"Invalid {col}")
    if events.duplicated(list(KEYS)).any():
        raise ValueError("Duplicate issuer/period observations require explicit revision handling")
    return events, forecasts


def match_forecast(event, forecasts, cfg):
    """Select latest collected comparable prior document, never the best surprise."""
    same = forecasts.copy()
    for k in KEYS:
        same = same[same[k] == event[k]]
    same = same[same.forecast_date < pd.Timestamp(event["publication_date"])]
    same = same[same.original_dated_document]
    if same.empty:
        return None, ["no_original_comparable_prior_forecast"]
    latest = same[same.forecast_date == same.forecast_date.max()]
    if len(latest) > 1:
        return None, ["ambiguous_latest_forecasts_no_consensus_rule"]
    f = latest.iloc[0]
    issues = []
    if (pd.Timestamp(event["publication_date"]) - f.forecast_date).days > cfg.forecast_max_age_days:
        issues.append("forecast_too_old")
    if f.forecast <= 0 or event["actual"] <= 0:
        issues.append("nonpositive_earnings")
    if not f.scope_verified:
        issues.append("forecast_scope_unverified")
    if event["known_newer_revision_unresolved"]:
        issues.append("known_newer_revision_unresolved")
    if not event["first_publication_verified"]:
        issues.append("first_publication_unverified")
    if not event["actual_asof_verified"]:
        issues.append("actual_not_verified_as_published")
    return f, issues


def liquidity_at(dataset, ticker, date, cfg):
    if ticker not in dataset.frames:
        return False, {"reason": "no_price_history"}
    f = dataset.frames[ticker].loc[: pd.Timestamp(date)].tail(cfg.liquidity_sessions)
    if len(f) < cfg.liquidity_sessions or f.close.isna().any():
        return False, {"reason": "insufficient_liquidity_history"}
    last = f.iloc[-1]
    stats = dict(
        adv_mad=float(f.volume_mad.mean()),
        traded_fraction=float(f.traded.mean()),
        stale_sessions=float(last.stale_sessions),
    )
    reasons = []
    if stats["adv_mad"] < cfg.min_average_volume_mad:
        reasons.append("low_ADV")
    if stats["traded_fraction"] < cfg.min_traded_fraction:
        reasons.append("low_traded_fraction")
    if not np.isfinite(stats["stale_sessions"]) or stats["stale_sessions"] > cfg.max_stale_sessions:
        reasons.append("stale_price")
    # Already-known outliers only; no ex-post filtering of losing event windows.
    if (f["return"].abs() > cfg.large_return_flag).any():
        reasons.append("historical_large_move_needs_review")
    meta = dataset.metadata.loc[ticker]
    if pd.notna(meta.active_from) and pd.Timestamp(date) < meta.active_from:
        reasons.append("not_active_yet")
    if pd.notna(meta.active_to) and pd.Timestamp(date) > meta.active_to:
        reasons.append("no_longer_active")
    stats["reason"] = ";".join(reasons)
    return not reasons, stats


def trade_window(dataset, ticker, publication_date, cfg, delay=0):
    cal = dataset.calendar
    first = cal.searchsorted(pd.Timestamp(publication_date), side="right")
    if ticker not in dataset.frames:
        return {"window_status": "no_prices"}
    f = dataset.frames[ticker]
    entry = next(
        (
            i
            for i in range(first + delay, min(first + cfg.entry_ttl_sessions, len(cal)))
            if bool(f.iloc[i].traded)
        ),
        None,
    )
    if entry is None:
        return {
            "window_status": "censored_entry"
            if first + cfg.entry_ttl_sessions > len(cal)
            else "entry_expired"
        }
    out = dict(
        entry_index=int(entry), entry_date=cal[entry], entry_close=float(f.iloc[entry].close)
    )
    target = entry + cfg.hold_sessions
    if target >= len(cal):
        return {**out, "window_status": "censored_exit", "target_exit_date": pd.NaT}
    out["target_exit_date"] = cal[target]
    ex = next((i for i in range(target, len(cal)) if bool(f.iloc[i].traded)), None)
    if ex is None:
        return {**out, "window_status": "censored_exit"}
    return {
        **out,
        "exit_index": int(ex),
        "exit_date": cal[ex],
        "exit_close": float(f.iloc[ex].close),
        "exit_deferred_sessions": int(ex - target),
        "holding_intervals": int(ex - entry),
        "window_status": "complete",
    }


def net_return(price_ratio, fee, slip):
    return price_ratio * (1 - slip) * (1 - fee) / ((1 + slip) * (1 + fee)) - 1


def price_ratio(frame, start, end):
    # Price-only, with known splits; distributions are explicitly not complete.
    a = frame.loc[start].close
    b = frame.loc[end].close
    if pd.isna(a) or pd.isna(b) or a <= 0:
        return np.nan
    splits = frame.loc[(frame.index > start) & (frame.index <= end), "split"].prod()
    return float(b * splits / a)


def peer_comparison(dataset, event, events, entry, exit, cfg):
    ticker = event["ticker"]
    sector = dataset.metadata.loc[ticker, "sector"]
    peers = [
        t
        for t in dataset.frames
        if t != ticker
        and dataset.metadata.loc[t, "sector"] == sector
        and liquidity_at(dataset, t, event["publication_date"], cfg)[0]
    ]
    contaminated = set(
        events.loc[
            (events.publication_date >= event["publication_date"])
            & (events.publication_date <= exit),
            "ticker",
        ]
    )
    screened = [t for t in peers if t not in contaminated]

    def calc(names):
        vals = [price_ratio(dataset.frames[t], entry, exit) - 1 for t in names]
        # Do not silently remove missing or inconvenient constituents.
        return float(np.mean(vals)) if vals and np.isfinite(vals).all() else np.nan

    stale = [t for t in peers if not dataset.frames[t].loc[[entry, exit], "traded"].all()]
    return dict(
        peer_tickers=";".join(screened),
        peer_count=len(screened),
        peer_gross_return=calc(screened),
        asof_peer_tickers=";".join(peers),
        asof_peer_count=len(peers),
        asof_peer_gross_return=calc(peers),
        peer_events_excluded_ex_post=";".join(sorted(set(peers) - set(screened))),
        peer_stale_endpoints=";".join(stale),
        peer_coverage_complete=False,
    )


def study(dataset, events, forecasts, cfg, delay=0):
    rows = []
    for _, e in events.sort_values(["publication_date", "ticker"]).iterrows():
        f, issues = match_forecast(e, forecasts, cfg)
        row = e.to_dict()
        row.update(
            forecast_id="",
            forecast=np.nan,
            forecast_date=pd.NaT,
            forecast_age_days=np.nan,
            surprise=np.nan,
            numeric_strong_beat=False,
        )
        if f is not None:
            surprise = (e.actual - f.forecast) / abs(f.forecast) if f.forecast else np.nan
            row.update(
                forecast_id=f.forecast_id,
                forecast=float(f.forecast),
                forecast_date=f.forecast_date,
                forecast_age_days=(e.publication_date - f.forecast_date).days,
                surprise=surprise,
                numeric_strong_beat=bool(
                    e.actual > 0 and f.forecast > 0 and surprise >= cfg.surprise_threshold
                ),
            )
        liquid, stats = liquidity_at(dataset, e.ticker, e.publication_date, cfg)
        row.update(
            liquid_at_publication=liquid,
            liquidity_reason=stats.get("reason", ""),
            adv_mad=stats.get("adv_mad", np.nan),
            traded_fraction=stats.get("traded_fraction", np.nan),
        )
        if not liquid:
            issues.append("liquidity_ineligible")
        row["issues"] = ";".join(issues)
        row["verified_match"] = f is not None and not issues
        row["verified_signal"] = row["verified_match"] and row["numeric_strong_beat"]
        # This permissive cohort is labelled CASE STUDY, never a deployable signal.
        fatal = {
            "no_original_comparable_prior_forecast",
            "ambiguous_latest_forecasts_no_consensus_rule",
            "forecast_too_old",
            "nonpositive_earnings",
            "known_newer_revision_unresolved",
            "actual_not_verified_as_published",
            "liquidity_ineligible",
        }
        row["case_study_signal"] = bool(row["numeric_strong_beat"] and not (fatal & set(issues)))
        w = trade_window(dataset, e.ticker, e.publication_date, cfg, delay)
        row.update(w)
        row.update(
            gross_return=np.nan,
            net_return=np.nan,
            peer_gross_return=np.nan,
            asof_peer_gross_return=np.nan,
            net_sector_excess=np.nan,
            gross_sector_excess=np.nan,
            net_asof_sector_excess=np.nan,
            peer_count=0,
            asof_peer_count=0,
            peer_tickers="",
            asof_peer_tickers="",
            peer_stale_endpoints="",
            known_action_in_window=False,
            event_large_move=False,
        )
        if w["window_status"] == "complete":
            frame = dataset.frames[e.ticker]
            ratio = price_ratio(frame, w["entry_date"], w["exit_date"])
            interval = frame.loc[(frame.index > w["entry_date"]) & (frame.index <= w["exit_date"])]
            row.update(
                gross_return=ratio - 1,
                net_return=net_return(ratio, cfg.fee_rate, cfg.slippage_rate),
                known_action_in_window=bool(
                    ((interval.split != 1) | (interval.dividend != 0)).any()
                ),
                event_large_move=bool((interval["return"].abs() > cfg.large_return_flag).any()),
            )
            peers = peer_comparison(dataset, e, events, w["entry_date"], w["exit_date"], cfg)
            row.update(peers)
            row.update(
                net_sector_excess=row["net_return"] - row["peer_gross_return"],
                gross_sector_excess=row["gross_return"] - row["peer_gross_return"],
                net_asof_sector_excess=row["net_return"] - row["asof_peer_gross_return"],
            )
        rows.append(row)
    return pd.DataFrame(rows)


def cluster_interval(frame, cfg):
    """Resample issuers, retaining each selected issuer's full event cluster."""
    frame = frame.dropna(subset=["net_sector_excess"])
    tickers = sorted(frame.ticker.unique())
    if len(tickers) < 5:
        return None
    groups = [frame.loc[frame.ticker == t, "net_sector_excess"].to_numpy() for t in tickers]
    rng = np.random.default_rng(cfg.random_seed)
    vals = [
        np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))]).mean()
        for _ in range(cfg.bootstrap_samples)
    ]
    return [float(x) for x in np.quantile(vals, [0.025, 0.975])]


def evaluate_gate(base, double_cost, integrity, cfg):
    signals = base[base.verified_signal]
    complete = signals[(signals.window_status == "complete") & signals.net_sector_excess.notna()]
    ci = cluster_interval(complete, cfg)
    mean = float(complete.net_sector_excess.mean()) if len(complete) else None
    years = sorted(signals.publication_date.dt.year.unique().tolist())
    latest = complete[complete.publication_date.dt.year == years[-1]] if years else complete
    double = double_cost[double_cost.event_id.isin(complete.event_id)]
    checks = {
        "minimum_verified_signals": len(signals) >= cfg.minimum_events,
        "minimum_issuers": signals.ticker.nunique() >= cfg.minimum_issuers,
        "minimum_release_years": len(years) >= cfg.minimum_release_years,
        "no_missing_or_censored_verified_outcomes": len(complete) == len(signals)
        and len(signals) > 0,
        "positive_net_sector_mean": mean is not None and mean > 0,
        "issuer_cluster_95pct_lower_above_zero": ci is not None and ci[0] > 0,
        "positive_latest_release_year": len(latest) > 0 and latest.net_sector_excess.mean() > 0,
        "positive_double_cost_mean": len(double) > 0 and double.net_sector_excess.mean() > 0,
    }
    for k, v in integrity.items():
        if isinstance(v, bool):
            checks[k] = v
    passed = all(bool(x) for x in checks.values())
    return dict(
        status="RESEARCH_GATE_PASSED_PAPER_ONLY" if passed else "REJECT_FOR_DEPLOYMENT",
        checks={k: bool(v) for k, v in checks.items()},
        verified_signals=len(signals),
        verified_issuers=int(signals.ticker.nunique()),
        verified_release_years=years,
        complete_verified_outcomes=len(complete),
        mean_net_sector_excess=mean,
        issuer_cluster_95pct=ci,
        new_sleeve_allocation_fraction=0.0,
        live_orders_enabled=False,
        reason="Research software never emits executable orders. Current evidence and data integrity do not support deploying this sleeve."
        if not passed
        else "Requires independent prospective validation and execution approval; this package is research-only.",
    )
