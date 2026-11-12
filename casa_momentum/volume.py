"""Predeclared volume-spike research sleeve; no news or block-trade inference."""

from dataclasses import dataclass

import pandas as pd

from .config import Config
from .data import Dataset
from .signals import allocate


@dataclass
class VolumePlan:
    schedule: dict[pd.Timestamp, pd.Series]
    entries: pd.DataFrame


def screen_volume(data: Dataset, cfg: Config) -> pd.DataFrame:
    """At close t compare traded shares with the maximum on t-20...t-1.

    Positive close is a declared contest filter, not part of the volume paper.
    Issuer news, blocks, crossings and index changes are unavailable here.
    """
    windows = []
    k = cfg.volume_lookback_sessions
    for ticker, f in data.frames.items():
        prior_max = f.shares.shift(1).rolling(k, min_periods=k).max()
        prior_traded = f.traded.shift(1).rolling(k, min_periods=k).sum().eq(k)
        action = (f.dividend.gt(0) | f.split.ne(1)).rolling(k + 1, min_periods=1).max().astype(bool)
        recent_jump = f.large_move.rolling(k + 1, min_periods=1).max().astype(bool)
        previous_close = f.close.shift(1)
        volume_ratio = f.shares.div(prior_max.where(prior_max.gt(0)))
        meta = data.metadata.loc[ticker]
        active = pd.Series(True, index=f.index)
        if pd.notna(meta.active_from):
            active &= f.index >= meta.active_from
        if pd.notna(meta.active_to):
            active &= f.index <= meta.active_to
        eligible = (
            active
            & f.traded
            & f.observed
            & f.coverage.ge(cfg.min_history_coverage)
            & f.liquidity_fraction.ge(cfg.min_traded_fraction)
            & f.average_volume_mad.ge(cfg.min_average_volume_mad)
            & prior_traded
            & f.observed.shift(1, fill_value=False).astype(bool)
            & ~action
            & ~(recent_jump & (cfg.return_mode == "price_proxy"))
        )
        rows = pd.DataFrame(
            {
                "date": f.index,
                "ticker": ticker,
                "sector": meta.sector,
                "close": f.close,
                "previous_close": previous_close,
                "traded_shares": f.shares,
                "prior_20_max_shares": prior_max,
                "volume_ratio": volume_ratio,
                "daily_price_return": f.close.div(previous_close).sub(1),
                "average_volume_mad": f.average_volume_mad,
                "traded_fraction_60": f.liquidity_fraction,
                "prior_20_sessions_traded": prior_traded,
                "known_action_in_window": action,
                "unreviewed_large_move": recent_jump & (cfg.return_mode == "price_proxy"),
                "liquid_eligible": eligible,
            },
            index=f.index,
        )
        windows.append(rows)
    out = pd.concat(windows, ignore_index=True)
    out = out.sort_values(["date", "ticker"], kind="stable")
    # Top-40 ranking is applied BEFORE observing the direction or spike size.
    liquid = out[out.liquid_eligible].copy()
    liquid["liquidity_rank"] = liquid.groupby("date")["average_volume_mad"].rank(
        ascending=False, method="first"
    )
    out["liquidity_rank"] = liquid.liquidity_rank.reindex(out.index)
    out["eligible"] = out.liquid_eligible & out.liquidity_rank.le(cfg.max_liquid_universe_size)
    out["volume_record"] = out.traded_shares.gt(out.prior_20_max_shares)
    out["positive_close"] = out.close.gt(out.previous_close)
    out["signal"] = out.eligible & out.volume_record
    if cfg.volume_require_positive_close:
        out["signal"] &= out.positive_close
    out["manual_news_verified"] = ""  # No issuer-event archive exists in the price CSVs.
    return out.reset_index(drop=True)


def core_weights(core_schedule: dict, data: Dataset, cfg: Config) -> dict:
    """Reserve at most half NAV for the existing monthly strategy."""
    result = {}
    for date, table in core_schedule.items():
        w = allocate(table, cfg).reindex(data.frames).fillna(0.0)
        if w.sum() > cfg.volume_sleeve_budget:
            w = w * (cfg.volume_sleeve_budget / w.sum())
        result[date] = w
    return result


def make_volume_plan(
    data: Dataset,
    cfg: Config,
    core_schedule: dict,
    volume_signals: pd.DataFrame,
    hold_sessions: int,
    entry_start=None,
    entry_end=None,
) -> VolumePlan:
    """Schedule one entry per spike and an exit after 5/10 trading intervals.

    A decision at t enters no sooner than t+1 close. The exit decision is
    t+hold_sessions and its fill is no sooner than the following close. Late
    sliced fills therefore have a shorter effective hold, which the logs show.
    Only entries whose planned exits fit inside entry_end are evaluated.
    """
    if hold_sessions <= 0:
        raise ValueError("hold_sessions must be positive")
    core = core_weights(core_schedule, data, cfg)
    first = min(core)
    cal = data.calendar
    symbols = sorted(data.frames)
    sectors = data.metadata.sector.to_dict()
    start = pd.Timestamp(entry_start) if entry_start is not None else first
    end = pd.Timestamp(entry_end) if entry_end is not None else cal[-1]
    end_i = cal.searchsorted(end, side="right") - 1
    events = volume_signals[
        volume_signals.signal
        & volume_signals.date.ge(start)
        & volume_signals.date.le(end)
        & volume_signals.date.ge(first)
    ]
    events = events.sort_values(
        ["date", "volume_ratio", "ticker"], ascending=[True, False, True], kind="stable"
    )
    by_date = {d: group for d, group in events.groupby("date")}
    active = {}  # ticker: (signal date index, fixed NAV weight)
    schedule, entries = {}, []
    monthly = pd.Series(0.0, index=symbols)
    for i, date in enumerate(cal):
        if date < first:
            continue
        changed = date in core
        if date in core:
            monthly = core[date].copy()
        expired = {s for s, (created, _) in active.items() if i >= created + hold_sessions}
        for s in expired:
            del active[s]
        changed |= bool(expired)
        # New core allocations take precedence over existing tactical exposure.
        for s, (created, weight) in list(active.items()):
            sector = sectors[s]
            other_sector = sum(w for t, (_, w) in active.items() if t != s and sectors[t] == sector)
            room = min(
                cfg.target_max_stock_weight - monthly[s],
                cfg.max_sector_weight
                - monthly[[t for t in symbols if sectors[t] == sector]].sum()
                - other_sector,
                cfg.volume_sleeve_budget - sum(w for t, (_, w) in active.items() if t != s),
                cfg.max_gross_weight
                - monthly.sum()
                - sum(w for t, (_, w) in active.items() if t != s),
            )
            if room < weight - 1e-10:
                changed = True
                if room <= 0:
                    del active[s]
                else:
                    active[s] = (created, max(0.0, room))
        if i + hold_sessions + 1 <= end_i and date in by_date:
            for row in by_date[date].itertuples():
                s = row.ticker
                if s in active or s in expired or monthly[s] > 0:
                    continue  # No stacking with the core and no fee-heavy restart.
                sector_room = cfg.max_sector_weight - sum(
                    monthly[t] for t in symbols if sectors[t] == sectors[s]
                )
                sector_room -= sum(
                    weight for t, (_, weight) in active.items() if sectors[t] == sectors[s]
                )
                remaining = min(
                    cfg.volume_sleeve_budget, cfg.max_gross_weight - monthly.sum()
                ) - sum(w for _, w in active.values())
                weight = min(cfg.target_max_stock_weight, sector_room, remaining)
                if weight < cfg.min_trade_nav_fraction - 1e-10:
                    continue
                active[s] = (i, float(weight))
                changed = True
                entries.append(
                    {
                        "date": date,
                        "ticker": s,
                        "sector": row.sector,
                        "volume_ratio": row.volume_ratio,
                        "planned_weight": weight,
                        "planned_entry": cal[i + 1],
                        "exit_decision": cal[i + hold_sessions],
                        "planned_exit_fill": cal[i + hold_sessions + 1],
                        "hold_sessions": hold_sessions,
                        "manual_news_verified": "",
                    }
                )
        if changed:
            target = monthly.copy()
            for s, (_, weight) in active.items():
                target[s] += weight
            if target.sum() > cfg.max_gross_weight + 1e-9:
                raise AssertionError("Volume sleeve exceeded gross cap")
            schedule[date] = target
    cols = [
        "date",
        "ticker",
        "sector",
        "volume_ratio",
        "planned_weight",
        "planned_entry",
        "exit_decision",
        "planned_exit_fill",
        "hold_sessions",
        "manual_news_verified",
    ]
    return VolumePlan(schedule, pd.DataFrame(entries, columns=cols))
