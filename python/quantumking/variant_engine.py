"""Multi-mode backtest engine for variant testing.

Exit modes supported per trade:
    "sl_trail"    : fixed SL at entry + trailing stop (default)
    "sl_only"     : fixed SL at entry, no trail (TP at fixed pts or no TP)
    "trail_only"  : no fixed SL, trailing kicks in after activation
    "be_only"     : breakeven escape only (close when price >= entry + N pts)
    "grid"        : non-Martingale grid (delegates to grid_backtest)
    "fixed_tp"    : fixed SL + fixed TP (R:R style)

Each variant produces standard stats so they're directly comparable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from .risk import (
    POINT,
    POINT_VALUE_PER_LOT,
    TrailParams,
    adaptive_lot,
)


ExitMode = Literal["sl_trail", "sl_only", "trail_only", "be_only", "fixed_tp"]


@dataclass
class VariantConfig:
    initial_equity: float = 10_000.0
    weight: float = 1.0
    exit_mode: ExitMode = "sl_trail"
    trail: TrailParams = field(default_factory=lambda: TrailParams(1000, 1000, 100))
    breakeven_pts: int = 150       # for be_only
    fixed_tp_pts: int = 0          # for fixed_tp (0 = no TP)
    sl_multiplier: float = 1.0     # scale strategy's suggested SL
    spread_cap_pts: int = 400
    danger_hours: tuple[int, ...] = (23, 0)
    use_regime: bool = True
    drawdown_kill_pct: float = 0.20
    # Safety: catastrophic stop applied in modes without explicit SL.
    # Prevents an unlucky open trade from blocking all future entries.
    catastrophic_sl_pts: int = 5000   # 5000 pts = $50 per lot of move
    max_hold_bars: int = 500          # ~5 trading days on M15


@dataclass
class _OpenTrade:
    side: int
    entry: float
    sl: float    # 0 = no SL
    tp: float    # 0 = no TP
    lot: float
    bar_in: int
    stop: float = 0.0  # trailing stop level (0 = inactive)


@dataclass
class _ClosedTrade:
    side: int
    entry: float
    exit: float
    lot: float
    bar_in: int
    bar_out: int
    pnl_usd: float
    reason: str


def _pnl(t: _OpenTrade, exit_px: float) -> float:
    pts = (exit_px - t.entry) / POINT * t.side
    return pts * t.lot * POINT_VALUE_PER_LOT


def run_variant(df: pd.DataFrame, signals: pd.DataFrame,
                cfg: VariantConfig = VariantConfig(),
                *, regime: pd.Series | None = None,
                strategy_kind: str = "trend") -> dict:
    sig = signals["signal"].fillna(0).astype(int).to_numpy()
    sl_pts_arr = signals["sl_pts"].astype(float).to_numpy()
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    spread = df.get("spread", pd.Series(0, index=df.index)).to_numpy()
    times = df.index

    reg_arr = regime.reindex(df.index).to_numpy() if regime is not None and cfg.use_regime else None

    open_t: _OpenTrade | None = None
    closed: list[_ClosedTrade] = []
    equity = cfg.initial_equity
    eq_hist = np.full(len(df), np.nan)

    use_sl = cfg.exit_mode in ("sl_trail", "sl_only", "fixed_tp")
    use_trail = cfg.exit_mode in ("sl_trail", "trail_only")
    use_tp = cfg.exit_mode == "fixed_tp" and cfg.fixed_tp_pts > 0
    use_be = cfg.exit_mode == "be_only"

    for i in range(len(df) - 1):
        bid = closes[i]
        ask = closes[i] + spread[i] * POINT

        if open_t is not None:
            # Catastrophic SL (always active, prevents stuck open trades).
            cat_sl = open_t.entry - open_t.side * cfg.catastrophic_sl_pts * POINT
            if open_t.side > 0 and lows[i] <= cat_sl:
                pnl = _pnl(open_t, cat_sl)
                equity += pnl
                closed.append(_ClosedTrade(
                    side=open_t.side, entry=open_t.entry, exit=cat_sl,
                    lot=open_t.lot, bar_in=open_t.bar_in, bar_out=i,
                    pnl_usd=pnl, reason="catastrophic_sl",
                ))
                open_t = None
                eq_hist[i] = equity
                if equity <= cfg.initial_equity * (1 - cfg.drawdown_kill_pct):
                    break
                continue
            if open_t is not None and open_t.side < 0 and highs[i] >= cat_sl:
                pnl = _pnl(open_t, cat_sl)
                equity += pnl
                closed.append(_ClosedTrade(
                    side=open_t.side, entry=open_t.entry, exit=cat_sl,
                    lot=open_t.lot, bar_in=open_t.bar_in, bar_out=i,
                    pnl_usd=pnl, reason="catastrophic_sl",
                ))
                open_t = None
                eq_hist[i] = equity
                if equity <= cfg.initial_equity * (1 - cfg.drawdown_kill_pct):
                    break
                continue

            # Max-hold timeout.
            if open_t is not None and (i - open_t.bar_in) >= cfg.max_hold_bars:
                px = closes[i]
                pnl = _pnl(open_t, px)
                equity += pnl
                closed.append(_ClosedTrade(
                    side=open_t.side, entry=open_t.entry, exit=px,
                    lot=open_t.lot, bar_in=open_t.bar_in, bar_out=i,
                    pnl_usd=pnl, reason="timeout",
                ))
                open_t = None
                eq_hist[i] = equity
                if equity <= cfg.initial_equity * (1 - cfg.drawdown_kill_pct):
                    break
                continue

            # Trailing update
            if use_trail:
                if open_t.side > 0 and (bid - open_t.entry) >= cfg.trail.activation_pts * POINT:
                    new_sl = bid - cfg.trail.distance_pts * POINT
                    if open_t.stop == 0 or (new_sl - open_t.stop) >= cfg.trail.step_pts * POINT:
                        open_t.stop = new_sl
                elif open_t.side < 0 and (open_t.entry - ask) >= cfg.trail.activation_pts * POINT:
                    new_sl = ask + cfg.trail.distance_pts * POINT
                    if open_t.stop == 0 or (open_t.stop - new_sl) >= cfg.trail.step_pts * POINT:
                        open_t.stop = new_sl

            # Exit checks
            exit_px = None
            reason = ""
            if open_t.side > 0:
                effective_sl = 0.0
                if use_sl and open_t.sl > 0:
                    effective_sl = open_t.sl
                if use_trail and open_t.stop > 0:
                    effective_sl = max(effective_sl, open_t.stop)
                if effective_sl > 0 and lows[i] <= effective_sl:
                    exit_px = effective_sl
                    reason = "trail" if (use_trail and open_t.stop == effective_sl) else "sl"
                if exit_px is None and use_tp and highs[i] >= open_t.tp:
                    exit_px = open_t.tp
                    reason = "tp"
                if exit_px is None and use_be and highs[i] >= open_t.entry + cfg.breakeven_pts * POINT:
                    exit_px = open_t.entry + cfg.breakeven_pts * POINT
                    reason = "be"
            else:
                effective_sl = 0.0
                if use_sl and open_t.sl > 0:
                    effective_sl = open_t.sl
                if use_trail and open_t.stop > 0:
                    effective_sl = min(effective_sl, open_t.stop) if effective_sl > 0 else open_t.stop
                if effective_sl > 0 and highs[i] >= effective_sl:
                    exit_px = effective_sl
                    reason = "trail" if (use_trail and open_t.stop == effective_sl) else "sl"
                if exit_px is None and use_tp and lows[i] <= open_t.tp:
                    exit_px = open_t.tp
                    reason = "tp"
                if exit_px is None and use_be and lows[i] <= open_t.entry - cfg.breakeven_pts * POINT:
                    exit_px = open_t.entry - cfg.breakeven_pts * POINT
                    reason = "be"

            if exit_px is not None:
                pnl = _pnl(open_t, exit_px)
                equity += pnl
                closed.append(_ClosedTrade(
                    side=open_t.side, entry=open_t.entry, exit=exit_px,
                    lot=open_t.lot, bar_in=open_t.bar_in, bar_out=i,
                    pnl_usd=pnl, reason=reason,
                ))
                open_t = None
                if equity <= cfg.initial_equity * (1 - cfg.drawdown_kill_pct):
                    eq_hist[i] = equity
                    break

        eq_hist[i] = equity

        # Entry
        if open_t is not None:
            continue
        if sig[i] == 0:
            continue
        ts = times[i + 1]
        if ts.hour in cfg.danger_hours:
            continue
        if spread[i] > cfg.spread_cap_pts:
            continue
        if reg_arr is not None:
            r = reg_arr[i]
            if strategy_kind == "trend" and not bool(r):
                continue
            if strategy_kind == "reversion" and bool(r):
                continue

        side = int(sig[i])
        entry = opens[i + 1]
        if not np.isfinite(entry):
            continue

        sl_price = 0.0
        if use_sl:
            sl = sl_pts_arr[i] * cfg.sl_multiplier
            if not np.isfinite(sl) or sl <= 0:
                sl = 800  # default
            sl_price = entry - side * sl * POINT

        tp_price = 0.0
        if use_tp:
            tp_price = entry + side * cfg.fixed_tp_pts * POINT

        lot = adaptive_lot(equity, weight=cfg.weight)
        open_t = _OpenTrade(side=side, entry=entry, sl=sl_price, tp=tp_price,
                            lot=lot, bar_in=i + 1)

    # Force-close any open trade at the last bar's close, account for floating PnL.
    if open_t is not None:
        last_px = closes[-1]
        pnl = _pnl(open_t, last_px)
        equity += pnl
        closed.append(_ClosedTrade(
            side=open_t.side, entry=open_t.entry, exit=last_px,
            lot=open_t.lot, bar_in=open_t.bar_in, bar_out=len(df) - 1,
            pnl_usd=pnl, reason="eod_close",
        ))
        open_t = None

    # Safety: if trail_only/be_only let a trade run forever past N bars without
    # an exit signal, force a stale-trade timeout at 500 bars (~5 trading days
    # on M15). Without this, sticky open positions hide losses.
    # (Already handled by EOD close above for the last open trade.)

    eq_hist[-1] = equity
    eq_curve = pd.Series(eq_hist, index=df.index).ffill()

    if not closed:
        return {"trades": 0, "pf": 0.0, "net_pnl": 0.0, "win_rate": 0.0,
                "expectancy": 0.0, "max_dd_pct": 0.0, "sharpe": 0.0,
                "final_equity": float(equity), "equity_curve": eq_curve,
                "trades_df": pd.DataFrame()}

    trades_df = pd.DataFrame([t.__dict__ for t in closed])
    wins = trades_df.loc[trades_df["pnl_usd"] > 0, "pnl_usd"].sum()
    losses = -trades_df.loc[trades_df["pnl_usd"] < 0, "pnl_usd"].sum()
    pf = wins / losses if losses > 0 else (float("inf") if wins > 0 else 0.0)
    rets = eq_curve.pct_change().dropna()
    sharpe = (rets.mean() / rets.std()) * np.sqrt(252 * 96) if rets.std() > 0 else 0.0
    running = eq_curve.cummax()
    dd = ((eq_curve - running) / running).min()
    return {
        "trades": int(len(trades_df)),
        "pf": float(pf if pf != float("inf") else 99.0),
        "net_pnl": float(trades_df["pnl_usd"].sum()),
        "win_rate": float((trades_df["pnl_usd"] > 0).mean()),
        "expectancy": float(trades_df["pnl_usd"].mean()),
        "max_dd_pct": float(dd),
        "sharpe": float(sharpe),
        "final_equity": float(eq_curve.iloc[-1]),
        "equity_curve": eq_curve,
        "trades_df": trades_df,
    }
