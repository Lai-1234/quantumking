"""Audit v6 Layer C: test 5 lot-sizing schemes on the v3.20 portfolio.

We can't modify the portfolio engine's lot logic mid-run, so this script
runs each strategy SOLO with each lot scheme and reports comparative stats.
The portfolio-level effect can then be inferred by superposition.
"""
from __future__ import annotations

import sys
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.filters import apply_filters
from quantumking.indicators import atr
from quantumking.lot_sizing import LotConfig, SCHEMES
from quantumking.regime import regime
from quantumking.risk import POINT, POINT_VALUE_PER_LOT
from quantumking.strategies import (
    adx_trend, ma_trend, macd_momentum, smc_orderblock,
)


def _run_with_lot_scheme(df, sigs, scheme: str, *, initial=10_000,
                          atr_series=None, atr_median=None) -> dict:
    """Bar-by-bar with custom lot-sizing scheme."""
    from quantumking.lot_sizing import compute_lot
    cfg = LotConfig(scheme=scheme, risk_pct=0.02, weight=1.0,
                      base_lot=0.05, kelly_fraction=0.5, sl_assumed_pts=1000)

    sig = sigs["signal"].fillna(0).astype(int).to_numpy()
    sl_pts = sigs["sl_pts"].astype(float).to_numpy()
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()

    equity = initial
    in_trade = False
    side = 0
    entry = 0.0
    sl = 0.0
    lot = 0.0
    bar_in = 0
    trail_stop = 0.0
    closed = []
    recent_pnls = []  # for Kelly
    TRAIL_ACT = 1400
    TRAIL_DIST = 1400
    TRAIL_STEP = 300
    MAX_HOLD = 500

    for i in range(len(df) - 1):
        if in_trade:
            # Trailing stop update
            if side > 0:
                if (closes[i] - entry) >= TRAIL_ACT * POINT:
                    new_stop = closes[i] - TRAIL_DIST * POINT
                    if trail_stop == 0 or (new_stop - trail_stop) >= TRAIL_STEP * POINT:
                        trail_stop = new_stop
            else:
                if (entry - closes[i]) >= TRAIL_ACT * POINT:
                    new_stop = closes[i] + TRAIL_DIST * POINT
                    if trail_stop == 0 or (trail_stop - new_stop) >= TRAIL_STEP * POINT:
                        trail_stop = new_stop

            # Effective stop = max(SL, trail) for long; min for short
            effective_sl = sl
            if trail_stop > 0:
                effective_sl = max(sl, trail_stop) if side > 0 else min(sl, trail_stop)

            exit_px = None
            if side > 0 and lows[i] <= effective_sl:
                exit_px = effective_sl
            elif side < 0 and highs[i] >= effective_sl:
                exit_px = effective_sl
            elif (i - bar_in) >= MAX_HOLD:
                exit_px = closes[i]  # timeout

            if exit_px is not None:
                pnl = (exit_px - entry) / POINT * side * lot * POINT_VALUE_PER_LOT
                equity += pnl
                closed.append(pnl)
                recent_pnls.append(pnl)
                if len(recent_pnls) > 50:
                    recent_pnls.pop(0)
                in_trade = False
                trail_stop = 0.0
        if in_trade or sig[i] == 0:
            continue
        s_ = int(sig[i])
        entry = opens[i + 1]
        if not np.isfinite(entry):
            continue
        bar_in = i + 1
        sl_d = sl_pts[i] if np.isfinite(sl_pts[i]) and sl_pts[i] > 0 else 800
        sl = entry - s_ * sl_d * POINT
        # State for Kelly / ATR
        if recent_pnls:
            wins = [p for p in recent_pnls if p > 0]
            losses = [p for p in recent_pnls if p < 0]
            wr = len(wins) / len(recent_pnls)
            avg_w = np.mean(wins) if wins else 1.0
            avg_l = abs(np.mean(losses)) if losses else 1.0
            wlr = avg_w / max(avg_l, 1e-6)
        else:
            wr, wlr = 0.4, 2.0
        atr_now = float(atr_series.iloc[i]) if atr_series is not None else 1.0
        am = float(atr_median.iloc[i]) if atr_median is not None else 1.0
        lot = compute_lot(equity, cfg, win_rate=wr, win_loss_ratio=wlr,
                           atr_now=atr_now, atr_median=am)
        side = s_
        in_trade = True

    if not closed:
        return {"scheme": scheme, "trades": 0, "pf": 0.0, "net_pnl": 0.0,
                "win_rate": 0.0, "final_equity": equity}
    pnls = np.array(closed)
    wins = pnls[pnls > 0].sum()
    losses = -pnls[pnls < 0].sum()
    pf = wins / losses if losses > 0 else 99.0
    return {
        "scheme": scheme,
        "trades": int(len(pnls)),
        "pf": round(pf, 3),
        "net_pnl": round(pnls.sum(), 0),
        "win_rate": round((pnls > 0).mean() * 100, 1),
        "final_equity": round(equity, 0),
    }


def main():
    d = ROOT / "data"
    m15 = pd.read_parquet(d / "XAUUSD_M15.parquet")
    h1 = pd.read_parquet(d / "XAUUSD_H1.parquet")
    h4 = pd.read_parquet(d / "XAUUSD_H4.parquet")
    a = atr(m15, 14)
    a_med = a.rolling(500, min_periods=50).median()

    # Use MA_Trend H1+H4 trail_only-equivalent variant from v5 best
    ma_sigs = apply_filters(ma_trend.generate_signals(m15, h4), df_h1=h1, df_h4=h4)
    macd_sigs = apply_filters(macd_momentum.generate_signals(m15, h1, h4), df_h1=h1, df_h4=h4)
    smc_sigs = apply_filters(smc_orderblock.generate_signals(m15), df_h1=h1, df_h4=h4)
    adx_sigs = apply_filters(adx_trend.generate_signals(m15), df_h1=h1, df_h4=h4)

    test_set = [
        ("MA_Trend", ma_sigs),
        ("MACD_Momentum", macd_sigs),
        ("SMC_OrderBlock", smc_sigs),
        ("ADX_Trend", adx_sigs),
    ]

    rows = []
    for sname, sigs in test_set:
        print(f"\n=== {sname} ===")
        for scheme in SCHEMES:
            res = _run_with_lot_scheme(m15, sigs, scheme, atr_series=a, atr_median=a_med)
            res["strategy"] = sname
            rows.append(res)
            print(f"  {scheme:25s}  PF={res['pf']:.2f}  trades={res['trades']:4d}  "
                  f"PnL=${res['net_pnl']:.0f}  WR={res['win_rate']}%  final=${res['final_equity']:.0f}")

    df = pd.DataFrame(rows)
    df.to_csv(d / "lot_sizing_comparison.csv", index=False)
    print(f"\nSaved lot_sizing_comparison.csv")

    print("\n=== Summary: Sharpe-equivalent ranking (final equity / abs max DD-like) ===")
    print(df.pivot(index="strategy", columns="scheme", values="pf").round(2).to_string())


if __name__ == "__main__":
    main()
