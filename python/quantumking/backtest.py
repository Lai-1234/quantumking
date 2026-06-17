"""Bar-by-bar backtest engine.

Closer to MT5's bar-close semantics than vectorbt's vectorized model.
Intentionally simple: one open trade per strategy at a time, fixed SL
at entry, three-parameter trailing stop, optional grid (not used by
trend strategies).

Signal interface
----------------
A strategy exposes ``generate_signals(df: DataFrame) -> DataFrame``
with columns ``signal`` (int in {-1, 0, +1}), ``sl_pts`` (float),
and optional ``trail_params`` (or strategy supplies via attribute).
Signal at bar i means: open the trade at bar i+1's open (no
look-ahead). Default exit: SL hit, or trailing-stop activated then
hit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from .risk import (
    POINT,
    POINT_VALUE_PER_LOT,
    ClosedTrade,
    OpenTrade,
    TrailParams,
    adaptive_lot,
    trade_pnl_usd,
    update_trailing,
)


@dataclass
class BacktestConfig:
    initial_equity: float = 10_000.0
    weight: float = 1.0
    trail: TrailParams = field(default_factory=lambda: TrailParams(1400, 1400, 100))
    danger_hours: tuple[int, ...] = (23, 0)  # global pause window (UTC)
    spread_cap_pts: int = 400
    use_atr_regime: bool = True
    regime_mult: float = 1.2


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity_curve: pd.Series
    stats: dict


def _is_safe_hour(ts: pd.Timestamp, danger: tuple[int, ...]) -> bool:
    return ts.hour not in danger


def run(df: pd.DataFrame, signals: pd.DataFrame,
        cfg: BacktestConfig = BacktestConfig(),
        *, regime: pd.Series | None = None,
        strategy_kind: str = "trend") -> BacktestResult:
    """Run a bar-by-bar backtest.

    Parameters
    ----------
    df : OHLCV indexed by UTC timestamps
    signals : columns ``signal`` (-1/0/+1) and ``sl_pts`` (float, may be NaN)
    regime : optional boolean/category aligned to df; ``True``/``"trend"`` allows
        trend strategies; reversion strategies inverted via strategy_kind.
    strategy_kind : "trend" or "reversion" — controls regime gating.
    """
    df = df.copy()
    sig = signals["signal"].fillna(0).astype(int).to_numpy()
    sl_pts = signals["sl_pts"].astype(float).to_numpy()
    spread = df.get("spread", pd.Series(0, index=df.index)).to_numpy()

    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    times = df.index

    open_trade: OpenTrade | None = None
    closed: list[ClosedTrade] = []
    equity = cfg.initial_equity
    eq_history = np.full(len(df), np.nan)

    if regime is not None:
        regime_arr = regime.reindex(df.index).to_numpy()
    else:
        regime_arr = None

    for i in range(len(df) - 1):
        bid = closes[i]
        ask = closes[i] + spread[i] * POINT

        # ---- Manage open trade on current bar ----
        if open_trade is not None:
            update_trailing(open_trade, bid, ask, cfg.trail)
            # SL/trail hit check using bar's high/low
            hit = False
            exit_price = None
            reason = ""
            if open_trade.side > 0:
                # Long: gets stopped if low touches SL or trailing stop
                effective_sl = max(open_trade.sl, open_trade.stop) if open_trade.stop > 0 else open_trade.sl
                if lows[i] <= effective_sl:
                    exit_price = effective_sl
                    hit = True
                    reason = "trail" if open_trade.stop > 0 and effective_sl == open_trade.stop else "sl"
            else:
                effective_sl = min(open_trade.sl, open_trade.stop) if open_trade.stop > 0 else open_trade.sl
                if highs[i] >= effective_sl:
                    exit_price = effective_sl
                    hit = True
                    reason = "trail" if open_trade.stop > 0 and effective_sl == open_trade.stop else "sl"
            if hit:
                pnl = trade_pnl_usd(open_trade, exit_price)
                equity += pnl
                closed.append(ClosedTrade(
                    side=open_trade.side, entry=open_trade.entry,
                    exit=exit_price, lot=open_trade.lot,
                    bar_in=open_trade.bar_in, bar_out=i,
                    pnl_usd=pnl, reason=reason,
                ))
                open_trade = None
                # Emergency drawdown check
                if equity <= cfg.initial_equity * (1 - 0.20):
                    eq_history[i] = equity
                    break

        eq_history[i] = equity

        # ---- Consider new entry on bar i, executes on bar i+1 open ----
        if open_trade is not None:
            continue
        if sig[i] == 0:
            continue
        ts = times[i + 1]
        if not _is_safe_hour(ts, cfg.danger_hours):
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
        entry_price = opens[i + 1]
        if not np.isfinite(entry_price) or not np.isfinite(sl_pts[i]):
            continue
        sl_price = entry_price - side * sl_pts[i] * POINT
        lot = adaptive_lot(equity, weight=cfg.weight)
        open_trade = OpenTrade(
            side=side, entry=entry_price, sl=sl_price,
            lot=lot, bar_in=i + 1,
        )

    eq_history[-1] = equity
    eq_curve = pd.Series(eq_history, index=df.index).ffill()

    trades_df = pd.DataFrame([t.__dict__ for t in closed])
    stats = _summarize(trades_df, eq_curve, cfg.initial_equity)
    return BacktestResult(trades=trades_df, equity_curve=eq_curve, stats=stats)


def _summarize(trades: pd.DataFrame, equity: pd.Series, init: float) -> dict:
    if trades.empty:
        return {"trades": 0, "pf": float("nan"), "net_pnl": 0.0,
                "win_rate": float("nan"), "max_dd_pct": 0.0,
                "sharpe": float("nan"), "expectancy": 0.0}
    wins = trades.loc[trades["pnl_usd"] > 0, "pnl_usd"].sum()
    losses = -trades.loc[trades["pnl_usd"] < 0, "pnl_usd"].sum()
    pf = wins / losses if losses > 0 else float("inf")
    win_rate = (trades["pnl_usd"] > 0).mean()
    net = trades["pnl_usd"].sum()
    rets = equity.pct_change().dropna()
    sharpe = (rets.mean() / rets.std()) * np.sqrt(252 * 96) if rets.std() > 0 else float("nan")
    running_max = equity.cummax()
    dd = (equity - running_max) / running_max
    return {
        "trades": int(len(trades)),
        "pf": float(pf),
        "net_pnl": float(net),
        "win_rate": float(win_rate),
        "expectancy": float(trades["pnl_usd"].mean()),
        "max_dd_pct": float(dd.min()),
        "sharpe": float(sharpe),
        "final_equity": float(equity.iloc[-1]),
    }
