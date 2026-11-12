"""Daily cash/position ledger with delayed orders and participation limits.

Close executions are a historical approximation. Desired shares use previous
close information. The realized daily-volume cap bounds simulated fills; it is
not presented as volume that was known before placing an order.
"""

import math

import numpy as np
import pandas as pd

TRADE_COLUMNS = [
    "date",
    "event_id",
    "ticker",
    "side",
    "shares",
    "reference_close",
    "fill_price",
    "fees",
    "cash_change",
    "realized_pnl",
    "reason",
    "lagged_adv_shares",
    "day_shares",
    "participation_cap",
]
ORDER_COLUMNS = ["date", "event_id", "ticker", "status", "shares", "reason"]


def simulate(dataset, signals, cfg):
    cal = dataset.calendar
    signals = signals.sort_values(["publication_date", "ticker"])
    starts = {}
    for _, e in signals.iterrows():
        idx = int(cal.searchsorted(e.publication_date, side="right"))
        starts.setdefault(idx, []).append(e)
    adv = {
        t: f.shares.rolling(cfg.liquidity_sessions, min_periods=cfg.liquidity_sessions)
        .mean()
        .shift(1)
        for t, f in dataset.frames.items()
    }
    cash = float(cfg.initial_capital)
    positions = {}
    pending = {}
    trims = {}
    trades = []
    orders = []
    daily = []
    disabled = False
    peak = cash
    previous_nav = cash

    def log(date, e, t, status, q, reason):
        orders.append(
            dict(date=date, event_id=e, ticker=t, status=status, shares=int(q), reason=reason)
        )

    def value(i, t):
        return positions[t]["qty"] * float(dataset.frames[t].iloc[i].close)

    def nav(i):
        return cash + sum(value(i, t) for t in positions)

    def sector(t):
        return dataset.metadata.loc[t, "sector"]

    def capacity(i, t):
        row = dataset.frames[t].iloc[i]
        a = adv[t].iloc[i]
        if not row.traded or not np.isfinite(a):
            return 0
        return max(0, int(math.floor(min(a, row.shares) * cfg.participation_rate)))

    for i, date in enumerate(cal):
        used = {}
        # Known corporate actions apply before today's trading; no hidden split loss.
        for t, p in list(positions.items()):
            row = dataset.frames[t].iloc[i]
            if row.split != 1:
                q = p["qty"] * row.split
                if abs(q - round(q)) > 1e-8:
                    raise ValueError("Fractional split requires a verified cash-in-lieu record")
                p["qty"] = int(round(q))
                if t in trims:
                    trims[t]["qty"] = int(math.ceil(trims[t]["qty"] * row.split))
            cash += p["qty"] * float(row.dividend)
        # Only a prior close can trigger today's risk exit.
        for t, p in list(positions.items()):
            due = disabled or i >= p["exit_index"]
            trim = trims.get(t)
            if not due and not trim:
                continue
            wanted = p["qty"] if due else min(p["qty"], trim["qty"])
            reason = (
                "drawdown_liquidation"
                if disabled
                else ("scheduled_exit" if due else trim["reason"])
            )
            q = min(wanted, capacity(i, t))
            if q <= 0:
                log(date, p["event_id"], t, "EXIT_PENDING", wanted, reason + "_no_capacity")
                continue
            row = dataset.frames[t].iloc[i]
            px = float(row.close) * (1 - cfg.slippage_rate)
            fees = q * px * cfg.fee_rate
            proceeds = q * px - fees
            basis = p["cost_basis"] * q / p["qty"]
            cash += proceeds
            trades.append(
                dict(
                    date=date,
                    event_id=p["event_id"],
                    ticker=t,
                    side="SELL",
                    shares=q,
                    reference_close=float(row.close),
                    fill_price=px,
                    fees=fees,
                    cash_change=proceeds,
                    realized_pnl=proceeds - basis,
                    reason=reason,
                    lagged_adv_shares=float(adv[t].iloc[i]),
                    day_shares=float(row.shares),
                    participation_cap=capacity(i, t),
                )
            )
            used[t] = q
            p["qty"] -= q
            p["cost_basis"] -= basis
            if trim:
                trim["qty"] = max(0, trim["qty"] - q)
                if trim["qty"] == 0:
                    trims.pop(t, None)
            if p["qty"] == 0:
                del positions[t]
                trims.pop(t, None)
            elif q < wanted:
                log(date, p["event_id"], t, "EXIT_PARTIAL_PENDING", wanted - q, reason)
        for e in starts.get(i, []):
            t = e.ticker
            if disabled:
                log(date, e.event_id, t, "ENTRY_REJECTED", 0, "drawdown_kill_switch")
                continue
            if t in positions or any(x["ticker"] == t for x in pending.values()):
                log(date, e.event_id, t, "ENTRY_REJECTED", 0, "existing_position_or_order")
                continue
            if i == 0 or t not in dataset.frames:
                log(date, e.event_id, t, "ENTRY_REJECTED", 0, "no_prior_price")
                continue
            prior = dataset.frames[t].iloc[i - 1].close
            if not np.isfinite(prior) or prior <= 0:
                log(date, e.event_id, t, "ENTRY_REJECTED", 0, "invalid_prior_price")
                continue
            q = int(
                cfg.stock_cap
                * previous_nav
                / (prior * (1 + cfg.slippage_rate) * (1 + cfg.fee_rate))
            )
            pending[e.event_id] = {"ticker": t, "qty": q, "expires": i + cfg.entry_ttl_sessions - 1}
            log(date, e.event_id, t, "ENTRY_INTENT", q, "quantity_from_prior_close_and_NAV")
        for eid, o in list(pending.items()):
            t = o["ticker"]
            if disabled:
                log(date, eid, t, "ENTRY_CANCELLED", o["qty"], "drawdown_kill_switch")
                del pending[eid]
                continue
            if i > o["expires"]:
                log(date, eid, t, "ENTRY_EXPIRED", o["qty"], "no_fill_within_TTL")
                del pending[eid]
                continue
            row = dataset.frames[t].iloc[i]
            qcap = max(0, capacity(i, t) - used.get(t, 0))
            if not row.traded or qcap == 0:
                continue
            close = float(row.close)
            unit_cost = close * (1 + cfg.slippage_rate) * (1 + cfg.fee_rate)
            current_nav = nav(i)
            gross = current_nav - cash
            sect = sum(value(i, k) for k in positions if sector(k) == sector(t))
            existing = value(i, t) if t in positions else 0
            # Include the immediate execution-cost reduction of NAV in each cap.
            cost_drag = unit_cost - close
            limits = [
                cash / unit_cost,
                (cfg.stock_cap * current_nav - existing) / (close + cfg.stock_cap * cost_drag),
                (cfg.sector_cap * current_nav - sect) / (close + cfg.sector_cap * cost_drag),
                (cfg.gross_cap * current_nav - gross) / (close + cfg.gross_cap * cost_drag),
            ]
            q = max(0, min(o["qty"], qcap, int(math.floor(min(limits) + 1e-10))))
            if q == 0:
                continue
            px = close * (1 + cfg.slippage_rate)
            fees = q * px * cfg.fee_rate
            cost = q * unit_cost
            cash -= cost
            positions[t] = {
                "qty": q,
                "cost_basis": cost,
                "event_id": eid,
                "exit_index": i + cfg.hold_sessions,
            }
            trades.append(
                dict(
                    date=date,
                    event_id=eid,
                    ticker=t,
                    side="BUY",
                    shares=q,
                    reference_close=close,
                    fill_price=px,
                    fees=fees,
                    cash_change=-cost,
                    realized_pnl=0.0,
                    reason="earnings_case_study"
                    if not bool(signals.loc[signals.event_id == eid, "verified_signal"].iloc[0])
                    else "verified_earnings_signal",
                    lagged_adv_shares=float(adv[t].iloc[i]),
                    day_shares=float(row.shares),
                    participation_cap=capacity(i, t),
                )
            )
            log(date, eid, t, "ENTRY_FILLED", q, "one_initial_fill_no_replenishment")
            if q < o["qty"]:
                log(
                    date,
                    eid,
                    t,
                    "REMAINDER_CANCELLED",
                    o["qty"] - q,
                    "participation_cash_or_weight_limit",
                )
            del pending[eid]
        # TTL expires after the third eligible calendar session, even if untraded.
        for eid, o in list(pending.items()):
            if i >= o["expires"]:
                log(date, eid, o["ticker"], "ENTRY_EXPIRED", o["qty"], "no_fill_within_TTL")
                del pending[eid]
        equity = nav(i)
        peak = max(peak, equity)
        drawdown = equity / peak - 1
        if not disabled and drawdown <= -cfg.drawdown_trigger:
            disabled = True
            log(date, "PORTFOLIO", "ALL", "KILL_SWITCH", 0, "liquidation_queued_for_next_session")
        vals = {t: value(i, t) for t in positions}
        # Price drift can breach caps. Queue reductions for the NEXT session.
        desired = {t: 0 for t in positions}
        for t, v in vals.items():
            desired[t] = max(
                0,
                int(
                    math.ceil(
                        (v - cfg.stock_cap * equity) / dataset.frames[t].iloc[i].close - 1e-10
                    )
                ),
            )
        projected = {t: vals[t] - desired[t] * dataset.frames[t].iloc[i].close for t in positions}
        for sec in sorted({sector(t) for t in positions}):
            excess = (
                sum(v for t, v in projected.items() if sector(t) == sec) - cfg.sector_cap * equity
            )
            for t in sorted(
                [t for t in positions if sector(t) == sec], key=lambda t: (-projected[t], t)
            ):
                if excess <= 0:
                    break
                px = dataset.frames[t].iloc[i].close
                q = min(positions[t]["qty"] - desired[t], int(math.ceil(excess / px)))
                desired[t] += q
                projected[t] -= q * px
                excess -= q * px
        excess = sum(projected.values()) - cfg.gross_cap * equity
        for t in sorted(positions, key=lambda t: (-projected[t], t)):
            if excess <= 0:
                break
            px = dataset.frames[t].iloc[i].close
            q = min(positions[t]["qty"] - desired[t], int(math.ceil(excess / px)))
            desired[t] += q
            excess -= q * px
        for t, q in desired.items():
            if q > 0:
                trims[t] = {"qty": min(q, positions[t]["qty"]), "reason": "weight_breach_trim"}
                log(
                    date,
                    positions[t]["event_id"],
                    t,
                    "TRIM_QUEUED",
                    q,
                    "price_drift_cap_breach_next_session",
                )
        sector_values = {
            s: sum(v for t, v in vals.items() if sector(t) == s)
            for s in {sector(t) for t in positions}
        }
        stale = [
            t
            for t in positions
            if dataset.frames[t].iloc[i].stale_sessions > cfg.max_stale_sessions
        ]
        daily.append(
            dict(
                date=date,
                cash=cash,
                holdings_value=sum(vals.values()),
                nav=equity,
                gross_weight=sum(vals.values()) / equity,
                max_stock_weight=max(vals.values(), default=0) / equity,
                max_sector_weight=max(sector_values.values(), default=0) / equity,
                drawdown=drawdown,
                positions=len(positions),
                entry_orders_pending=len(pending),
                exit_positions_pending=sum(
                    disabled or i >= p["exit_index"] or t in trims for t, p in positions.items()
                ),
                kill_switch=disabled,
                stale_holdings=";".join(stale),
            )
        )
        if cash < -1e-6 or not np.isfinite(equity) or equity <= 0:
            raise AssertionError("Invalid cash or NAV")
        previous_nav = equity
    inventory = [
        dict(
            ticker=t,
            shares=p["qty"],
            cost_basis=p["cost_basis"],
            event_id=p["event_id"],
            scheduled_exit_index=p["exit_index"],
            exit_pending=bool(disabled or len(cal) - 1 >= p["exit_index"] or t in trims),
        )
        for t, p in positions.items()
    ]
    return (
        pd.DataFrame(daily),
        pd.DataFrame(trades, columns=TRADE_COLUMNS),
        pd.DataFrame(orders, columns=ORDER_COLUMNS),
        pd.DataFrame(
            inventory,
            columns=[
                "ticker",
                "shares",
                "cost_basis",
                "event_id",
                "scheduled_exit_index",
                "exit_pending",
            ],
        ),
    )
