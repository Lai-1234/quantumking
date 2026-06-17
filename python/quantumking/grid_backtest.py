"""Grid-based backtest engine (faithful port of CPositionManager::ManagePositions).

Used for the 3 strategies that escape via grid rather than fixed SL:
Bands_Extreme, Pivot_Divergence, VWAP_Reversion.

Mechanics (matches MQL5 CPositionManager.mqh exactly):
- Initial signal opens a single position at adaptive lot size.
- New signals while a stack is open are BLOCKED (HasPosition lock).
- When unrealized price moves grid_spacing pts against the lowest fill
  (long) or highest fill (short), add an equal-volume layer (same lot
  as the average of existing layers). Up to max_grids layers total.
- When market price crosses avg_price + breakeven_pts in the favorable
  direction, CLOSE all stack positions (microprofit escape).
- Global drawdown cap of 20% closes everything (CRiskManager rule).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from .risk import POINT, POINT_VALUE_PER_LOT, adaptive_lot


@dataclass
class GridConfig:
    initial_equity: float = 10_000.0
    weight: float = 1.0
    breakeven_pts: int = 150
    grid_spacing_pts: int = 1000
    max_grids: int = 10
    spread_cap_pts: int = 400
    danger_hours: tuple[int, ...] = (23, 0)
    drawdown_kill_pct: float = 0.20


@dataclass
class GridLayer:
    entry: float
    lot: float


@dataclass
class GridStack:
    side: Literal[1, -1]
    layers: list[GridLayer] = field(default_factory=list)
    bar_in: int = 0

    @property
    def total_lot(self) -> float:
        return sum(l.lot for l in self.layers)

    @property
    def avg_entry(self) -> float:
        tv = self.total_lot
        if tv == 0:
            return 0.0
        return sum(l.entry * l.lot for l in self.layers) / tv

    @property
    def lowest(self) -> float:
        return min(l.entry for l in self.layers)

    @property
    def highest(self) -> float:
        return max(l.entry for l in self.layers)


@dataclass
class GridClosedTrade:
    side: int
    avg_entry: float
    exit: float
    total_lot: float
    layers: int
    bar_in: int
    bar_out: int
    pnl_usd: float
    reason: str


def run_grid(df: pd.DataFrame, signals: pd.DataFrame,
             cfg: GridConfig = GridConfig(),
             *, regime: pd.Series | None = None,
             strategy_kind: str = "reversion") -> dict:
    sig = signals["signal"].fillna(0).astype(int).to_numpy()
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    spread = df.get("spread", pd.Series(0, index=df.index)).to_numpy()
    times = df.index

    if regime is not None:
        regime_arr = regime.reindex(df.index).to_numpy()
    else:
        regime_arr = None

    stack: GridStack | None = None
    closed: list[GridClosedTrade] = []
    equity = cfg.initial_equity
    eq_hist = np.full(len(df), np.nan)

    for i in range(len(df) - 1):
        bid = closes[i]
        ask = closes[i] + spread[i] * POINT

        # Manage existing stack
        if stack is not None:
            cur_low = lows[i]
            cur_high = highs[i]
            # Microprofit escape: bid >= avg + breakeven (long), ask <= avg - breakeven (short)
            breakeven_price = (
                stack.avg_entry + cfg.breakeven_pts * POINT
                if stack.side > 0 else
                stack.avg_entry - cfg.breakeven_pts * POINT
            )
            close_stack = False
            exit_price = breakeven_price
            reason = "breakeven"
            if stack.side > 0 and cur_high >= breakeven_price:
                close_stack = True
            elif stack.side < 0 and cur_low <= breakeven_price:
                close_stack = True

            if close_stack:
                pts = (exit_price - stack.avg_entry) / POINT * stack.side
                pnl = pts * stack.total_lot * POINT_VALUE_PER_LOT
                equity += pnl
                closed.append(GridClosedTrade(
                    side=stack.side, avg_entry=stack.avg_entry,
                    exit=exit_price, total_lot=stack.total_lot,
                    layers=len(stack.layers), bar_in=stack.bar_in,
                    bar_out=i, pnl_usd=pnl, reason=reason,
                ))
                stack = None
            else:
                # Grid add: price moved spacing against lowest (long) or highest (short)
                if len(stack.layers) < cfg.max_grids:
                    if stack.side > 0 and cur_low <= stack.lowest - cfg.grid_spacing_pts * POINT:
                        base_vol = stack.total_lot / len(stack.layers)
                        add_price = stack.lowest - cfg.grid_spacing_pts * POINT
                        stack.layers.append(GridLayer(entry=add_price, lot=base_vol))
                    elif stack.side < 0 and cur_high >= stack.highest + cfg.grid_spacing_pts * POINT:
                        base_vol = stack.total_lot / len(stack.layers)
                        add_price = stack.highest + cfg.grid_spacing_pts * POINT
                        stack.layers.append(GridLayer(entry=add_price, lot=base_vol))
                # Drawdown kill: mark-to-market unrealized PnL
                mtm_price = bid if stack.side > 0 else ask
                pts = (mtm_price - stack.avg_entry) / POINT * stack.side
                unrealized = pts * stack.total_lot * POINT_VALUE_PER_LOT
                if equity + unrealized <= cfg.initial_equity * (1 - cfg.drawdown_kill_pct):
                    equity += unrealized
                    closed.append(GridClosedTrade(
                        side=stack.side, avg_entry=stack.avg_entry,
                        exit=mtm_price, total_lot=stack.total_lot,
                        layers=len(stack.layers), bar_in=stack.bar_in,
                        bar_out=i, pnl_usd=unrealized, reason="drawdown_kill",
                    ))
                    stack = None
                    eq_hist[i] = equity
                    break

        eq_hist[i] = equity

        # New entry on bar i, execute at bar i+1 open
        if stack is not None:
            continue
        if sig[i] == 0:
            continue
        ts = times[i + 1]
        if ts.hour in cfg.danger_hours:
            continue
        if spread[i] > cfg.spread_cap_pts:
            continue
        if regime_arr is not None:
            r = regime_arr[i]
            if strategy_kind == "trend" and not bool(r):
                continue
            if strategy_kind == "reversion" and bool(r):
                continue

        side = int(sig[i])
        entry = opens[i + 1]
        if not np.isfinite(entry):
            continue
        lot = adaptive_lot(equity, weight=cfg.weight)
        stack = GridStack(side=side, layers=[GridLayer(entry=entry, lot=lot)], bar_in=i + 1)

    eq_hist[-1] = equity
    eq_curve = pd.Series(eq_hist, index=df.index).ffill()

    trades_df = pd.DataFrame([t.__dict__ for t in closed])
    if trades_df.empty:
        stats = {"trades": 0, "pf": float("nan"), "net_pnl": 0.0,
                 "win_rate": float("nan"), "max_dd_pct": 0.0,
                 "sharpe": float("nan"), "expectancy": 0.0,
                 "final_equity": equity,
                 "avg_layers": 0.0, "kill_events": 0}
    else:
        wins = trades_df.loc[trades_df["pnl_usd"] > 0, "pnl_usd"].sum()
        losses = -trades_df.loc[trades_df["pnl_usd"] < 0, "pnl_usd"].sum()
        pf = wins / losses if losses > 0 else float("inf")
        net = trades_df["pnl_usd"].sum()
        wr = (trades_df["pnl_usd"] > 0).mean()
        rets = eq_curve.pct_change().dropna()
        sharpe = (rets.mean() / rets.std()) * np.sqrt(252 * 96) if rets.std() > 0 else float("nan")
        running_max = eq_curve.cummax()
        dd = (eq_curve - running_max) / running_max
        stats = {
            "trades": int(len(trades_df)),
            "pf": float(pf),
            "net_pnl": float(net),
            "win_rate": float(wr),
            "expectancy": float(trades_df["pnl_usd"].mean()),
            "max_dd_pct": float(dd.min()),
            "sharpe": float(sharpe),
            "final_equity": float(eq_curve.iloc[-1]),
            "avg_layers": float(trades_df["layers"].mean()),
            "kill_events": int((trades_df["reason"] == "drawdown_kill").sum()),
        }
    return {"trades": trades_df, "equity_curve": eq_curve, "stats": stats}
