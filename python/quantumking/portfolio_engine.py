"""True concurrent multi-strategy portfolio engine.

Mirrors CStrategyManager logic:
- Global position cap (6 positions max across all strategies)
- 23:00-00:00 UTC danger zone (all strategies pause)
- ATR regime gate (trend strategies trade only in trending regime,
  reversion strategies only in low-vol)
- Per-strategy magic-number lock (one trade per strategy at a time)

This shows what happens when strategies interfere with each other
(e.g., MA wants to enter but global cap is full because MACD already has 3 open).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .risk import POINT, POINT_VALUE_PER_LOT, TrailParams, adaptive_lot


@dataclass
class StratSpec:
    name: str
    signals: pd.DataFrame
    trail: TrailParams
    kind: str = "trend"
    weight: float = 1.0


@dataclass
class PortfolioConfig:
    initial_equity: float = 10_000.0
    max_positions: int = 6
    spread_cap_pts: int = 400
    danger_hours: tuple[int, ...] = (23, 0)
    drawdown_kill_pct: float = 0.20
    catastrophic_sl_pts: int = 5000
    # Realistic execution costs (XAUUSD typical broker):
    spread_pts: int = 17      # 17 pts = $0.17 per 0.01 lot per trade
    slippage_pts: int = 5     # 5 pts at entry and at exit
    commission_per_lot: float = 0.0  # most retail brokers bundle commission into spread


@dataclass
class _OT:
    strat: str
    side: int
    entry: float
    sl: float
    lot: float
    bar_in: int
    stop: float = 0.0


def run_portfolio(df: pd.DataFrame, strats: list[StratSpec],
                  cfg: PortfolioConfig = PortfolioConfig(),
                  *, regime: pd.Series | None = None) -> dict:
    n = len(df)
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    spread = df.get("spread", pd.Series(0, index=df.index)).to_numpy()
    times = df.index

    reg_arr = regime.reindex(df.index).to_numpy() if regime is not None else None

    sig_map = {}
    sl_map = {}
    for s in strats:
        sig_map[s.name] = s.signals["signal"].fillna(0).astype(int).to_numpy()
        sl_map[s.name] = s.signals["sl_pts"].astype(float).to_numpy()
    strat_map = {s.name: s for s in strats}

    open_trades: list[_OT] = []
    closed: list[dict] = []
    equity = cfg.initial_equity
    eq_hist = np.full(n, np.nan, dtype="float64")

    for i in range(n - 1):
        bid = closes[i]
        ask = closes[i] + spread[i] * POINT

        # Manage existing positions
        to_remove = []
        for t in open_trades:
            spec = strat_map[t.strat]
            trail = spec.trail
            # trailing update
            if t.side > 0 and (bid - t.entry) >= trail.activation_pts * POINT:
                new_sl = bid - trail.distance_pts * POINT
                if t.stop == 0 or (new_sl - t.stop) >= trail.step_pts * POINT:
                    t.stop = new_sl
            elif t.side < 0 and (t.entry - ask) >= trail.activation_pts * POINT:
                new_sl = ask + trail.distance_pts * POINT
                if t.stop == 0 or (t.stop - new_sl) >= trail.step_pts * POINT:
                    t.stop = new_sl

            # catastrophic SL (always active)
            cat_sl = t.entry - t.side * cfg.catastrophic_sl_pts * POINT

            effective_sl = t.sl
            if t.side > 0:
                if t.stop > 0 and t.stop > effective_sl:
                    effective_sl = t.stop
                if lows[i] <= effective_sl or lows[i] <= cat_sl:
                    exit_px = max(effective_sl, cat_sl) if cat_sl < effective_sl else effective_sl
                    # Slippage at exit
                    exit_px -= cfg.slippage_pts * POINT
                    pnl = (exit_px - t.entry) / POINT * t.lot * POINT_VALUE_PER_LOT
                    equity += pnl
                    closed.append({"strat": t.strat, "side": 1, "entry": t.entry,
                                   "exit": exit_px, "lot": t.lot, "bar_in": t.bar_in,
                                   "bar_out": i, "pnl_usd": pnl})
                    to_remove.append(t)
            else:
                if t.stop > 0 and (effective_sl == 0 or t.stop < effective_sl):
                    effective_sl = t.stop
                if highs[i] >= effective_sl or highs[i] >= cat_sl:
                    exit_px = min(effective_sl, cat_sl) if cat_sl > effective_sl else effective_sl
                    # Slippage at exit (short, slippage works against us = higher exit)
                    exit_px += cfg.slippage_pts * POINT
                    pnl = (exit_px - t.entry) / POINT * t.side * t.lot * POINT_VALUE_PER_LOT
                    equity += pnl
                    closed.append({"strat": t.strat, "side": -1, "entry": t.entry,
                                   "exit": exit_px, "lot": t.lot, "bar_in": t.bar_in,
                                   "bar_out": i, "pnl_usd": pnl})
                    to_remove.append(t)
        for t in to_remove:
            open_trades.remove(t)

        eq_hist[i] = equity
        if equity <= cfg.initial_equity * (1 - cfg.drawdown_kill_pct):
            break

        # New entries (in strategy declaration order — first to fire wins the slot)
        ts = times[i + 1]
        if ts.hour in cfg.danger_hours:
            continue
        if spread[i] > cfg.spread_cap_pts:
            continue
        if len(open_trades) >= cfg.max_positions:
            continue

        active_strats = {t.strat for t in open_trades}
        for s in strats:
            if len(open_trades) >= cfg.max_positions:
                break
            if s.name in active_strats:
                continue  # one trade per strategy at a time
            if reg_arr is not None:
                r = reg_arr[i]
                if s.kind == "trend" and not bool(r):
                    continue
                if s.kind == "reversion" and bool(r):
                    continue
            sig = sig_map[s.name][i]
            if sig == 0:
                continue
            entry = opens[i + 1]
            if not np.isfinite(entry):
                continue
            # Apply spread + slippage to entry: pay spread on buy, get less on sell;
            # entry slippage works against us.
            entry_cost_pts = cfg.spread_pts + cfg.slippage_pts
            entry = entry + sig * entry_cost_pts * POINT
            sl_pts = sl_map[s.name][i]
            if not np.isfinite(sl_pts) or sl_pts <= 0:
                sl_pts = 800
            sl_price = entry - sig * sl_pts * POINT
            lot = adaptive_lot(equity, weight=s.weight)
            open_trades.append(_OT(
                strat=s.name, side=sig, entry=entry, sl=sl_price,
                lot=lot, bar_in=i + 1,
            ))

    # Force-close anything still open at end
    for t in open_trades:
        pnl = (closes[-1] - t.entry) / POINT * t.side * t.lot * POINT_VALUE_PER_LOT
        equity += pnl
        closed.append({"strat": t.strat, "side": t.side, "entry": t.entry,
                       "exit": closes[-1], "lot": t.lot, "bar_in": t.bar_in,
                       "bar_out": n - 1, "pnl_usd": pnl})

    eq_hist[-1] = equity
    eq_curve = pd.Series(eq_hist, index=df.index).ffill()

    if not closed:
        return {"trades": 0, "pf": 0, "net_pnl": 0, "win_rate": 0,
                "max_dd_pct": 0, "sharpe": 0, "final_equity": equity,
                "equity_curve": eq_curve, "trades_df": pd.DataFrame()}

    trades_df = pd.DataFrame(closed)
    wins = trades_df.loc[trades_df["pnl_usd"] > 0, "pnl_usd"].sum()
    losses = -trades_df.loc[trades_df["pnl_usd"] < 0, "pnl_usd"].sum()
    pf = wins / losses if losses > 0 else (99.0 if wins > 0 else 0)
    rets = eq_curve.pct_change().dropna()
    sharpe = (rets.mean() / rets.std()) * np.sqrt(252 * 96) if rets.std() > 0 else 0
    running = eq_curve.cummax()
    dd = ((eq_curve - running) / running).min()
    # Per-strategy breakdown
    by_strat = trades_df.groupby("strat").agg(
        trades=("pnl_usd", "size"),
        net_pnl=("pnl_usd", "sum"),
        win_rate=("pnl_usd", lambda x: (x > 0).mean()),
    ).round(2)

    return {
        "trades": int(len(trades_df)),
        "pf": float(pf),
        "net_pnl": float(trades_df["pnl_usd"].sum()),
        "win_rate": float((trades_df["pnl_usd"] > 0).mean()),
        "max_dd_pct": float(dd),
        "sharpe": float(sharpe),
        "final_equity": float(eq_curve.iloc[-1]),
        "equity_curve": eq_curve,
        "trades_df": trades_df,
        "by_strat": by_strat,
    }
