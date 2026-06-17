"""Compute profit in PIPS (lot-independent) for the TOP-200 x3 result sets.

pips = sum over closed trades of (exit - entry)/POINT * side / 10
   (XAUUSD: 1 point = 0.01; 1 pip = 10 points = $0.10 price move)
Also reports raw points and points-per-trade.
"""
from __future__ import annotations

import ast
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.backtest import BacktestConfig, run
from quantumking.filters import apply_filters
from quantumking.indicators import atr
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.regime import regime
from quantumking.risk import POINT, TrailParams
from quantumking.strategies import (
    adx_trend, asian_breakout, fractal_breakout, ma_trend, macd_momentum,
    pivot_divergence, smc_orderblock,
)

POINTS_PER_PIP = 10.0  # gold convention: 1 pip = 0.10 price = 10 points

_DATA = {}
def D():
    if not _DATA:
        d = ROOT / "data"
        _DATA["M15"] = pd.read_parquet(d / "XAUUSD_M15.parquet")
        _DATA["H1"] = pd.read_parquet(d / "XAUUSD_H1.parquet")
        _DATA["H4"] = pd.read_parquet(d / "XAUUSD_H4.parquet")
        _DATA["D1"] = pd.read_parquet(d / "XAUUSD_D1.parquet")
        _DATA["reg"] = regime(_DATA["M15"])
    return _DATA


def pips_from_trades(trades: pd.DataFrame) -> tuple[float, float, float]:
    if trades is None or trades.empty:
        return 0.0, 0.0, 0.0
    pts = ((trades["exit"] - trades["entry"]) / POINT * trades["side"])
    total_points = float(pts.sum())
    return total_points, total_points / POINTS_PER_PIP, total_points / len(trades)


def parse_trail(s, default=(2000, 1500, 500)):
    try:
        return tuple(ast.literal_eval(str(s)))
    except Exception:
        return default


# ---------- strategy solo re-run ----------
def run_strategy_row(row):
    d = D()
    m15, h1, h4, d1, reg = d["M15"], d["H1"], d["H4"], d["D1"], d["reg"]
    strat = row["strategy"]
    trail = TrailParams(*parse_trail(row.get("trail")))
    kind = "trend"
    sigs = None
    if strat == "MA_Trend":
        p = ma_trend.MAParams(fast_ema=int(row["fast_ema"]), slow_ema=int(row["slow_ema"]),
                                  kdj_period=int(row["kdj_p"]), kdj_d=int(row["kdj_d"]), kdj_s=2,
                                  fibo_top=0.5, fibo_bottom=float(row["fibo_b"]))
        sigs = ma_trend.generate_signals(m15, h4, p)
    elif strat == "MACD_Momentum":
        p = macd_momentum.MacdParams(fast=int(row["fast"]), slow=int(row["slow"]), signal=int(row["sig"]))
        sigs = macd_momentum.generate_signals(m15, h1, h4, p)
        mtf = str(row.get("mtf", "none"))
        if mtf == "H1": sigs = apply_filters(sigs, df_h1=h1)
        elif mtf == "H4": sigs = apply_filters(sigs, df_h4=h4)
        elif mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=h1, df_h4=h4)
        sigs["sl_pts"] *= float(row.get("sl_mult", 1.0))
    elif strat == "SMC_OrderBlock":
        p = smc_orderblock.SmcParams(sl_buffer_pts=int(row["sl_buf"]), fib_tolerance_pts=int(row["fib_tol"]), scan_window=int(row["scan"]))
        sigs = smc_orderblock.generate_signals(m15, p)
        mtf = str(row.get("mtf", "none"))
        if mtf == "H1": sigs = apply_filters(sigs, df_h1=h1)
        elif mtf == "H4": sigs = apply_filters(sigs, df_h4=h4)
        elif mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=h1, df_h4=h4)
        sigs["sl_pts"] *= float(row.get("sl_mult", 1.0))
    elif strat == "ADX_Trend":
        p = adx_trend.AdxParams(period=int(row["period"]), threshold=float(row["threshold"]))
        sigs = adx_trend.generate_signals(m15, p)
        mtf = str(row.get("mtf", "none"))
        if mtf == "H1": sigs = apply_filters(sigs, df_h1=h1)
        elif mtf == "H4": sigs = apply_filters(sigs, df_h4=h4)
        elif mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=h1, df_h4=h4)
        sigs["sl_pts"] *= float(row.get("sl_mult", 1.0))
    elif strat == "Asian_Breakout":
        p = asian_breakout.AsianParams(start_hour=int(row["start_hour"]), end_hour=int(row["end_hour"]),
                                           breakout_window_hours=int(row["window_hours"]),
                                           min_body_ratio=float(row["min_body"]), sl_buffer_pts=int(row["sl_buf"]))
        sigs = asian_breakout.generate_signals(m15, p)
    elif strat == "Fractal_Breakout":
        p = fractal_breakout.FractalParams(buffer_pts=int(row["buf_pts"]), sl_buffer_pts=int(row["sl_buf"]))
        sigs = fractal_breakout.generate_signals(m15, p)
        mtf = str(row.get("mtf", "none"))
        if mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=h1, df_h4=h4)
        elif mtf == "H1": sigs = apply_filters(sigs, df_h1=h1)
        elif mtf == "H4": sigs = apply_filters(sigs, df_h4=h4)
        sigs["sl_pts"] *= float(row.get("sl_mult", 1.0))
    if sigs is None:
        return None
    res = run(m15, sigs, BacktestConfig(initial_equity=10_000, trail=trail), regime=reg, strategy_kind=kind)
    tp, pips, ppt = pips_from_trades(res.trades)
    return {"profit_points": round(tp, 1), "profit_pips": round(pips, 1),
            "points_per_trade": round(ppt, 1), "trades": res.stats["trades"],
            "net_pnl": round(res.stats["net_pnl"], 0), "pf": round(res.stats["pf"], 3)}


# ---------- portfolio re-run (managers + combinations) ----------
TIME_PAUSE = {"none": (), "23-00": (23, 0), "22-01": (22, 23, 0, 1), "23-01": (23, 0, 1),
              "00-02": (0, 1, 2), "22-00": (22, 23, 0), "21-00": (21, 22, 23, 0),
              "20-01": (20, 21, 22, 23, 0, 1), "news_block_13_14": (13, 14)}

def portfolio_specs():
    d = D()
    m15, h1, h4, d1 = d["M15"], d["H1"], d["H4"], d["D1"]
    tr = TrailParams(2000, 1500, 500)
    ma = ma_trend.generate_signals(m15, h4, ma_trend.MAParams(fast_ema=10, slow_ema=40, kdj_period=7, kdj_d=2, kdj_s=2, fibo_top=0.5, fibo_bottom=0.677))
    macd = apply_filters(macd_momentum.generate_signals(m15, h1, h4, macd_momentum.MacdParams(18, 35, 7)), df_h1=h1, df_h4=h4); macd["sl_pts"] *= 0.5
    smc = apply_filters(smc_orderblock.generate_signals(m15, smc_orderblock.SmcParams(60, 200, 100)), df_h1=h1, df_h4=h4); smc["sl_pts"] *= 0.5
    adx = apply_filters(adx_trend.generate_signals(m15, adx_trend.AdxParams(14, 25.0)), df_h1=h1, df_h4=h4)
    piv = apply_filters(pivot_divergence.generate_signals(m15, d1, pivot_divergence.PivotParams(10, 300, 1500)), df_h1=h1, df_h4=h4); piv["sl_pts"] *= 0.5
    return [("MA_Trend", ma, "trend", 1.0), ("SMC", smc, "trend", 0.7),
            ("MACD", macd, "trend", 0.3), ("ADX", adx, "trend", 0.3),
            ("Pivot", piv, "reversion", 0.4)], tr

_PSPECS = None
def run_portfolio_row(time_pause, regime_mult, cap, risk_pct, dd_thresh):
    global _PSPECS
    d = D()
    if _PSPECS is None:
        _PSPECS = portfolio_specs()
    base, tr = _PSPECS
    if regime_mult == 0:
        reg = None
    else:
        reg = atr(d["M15"], 7) > atr(d["M15"], 50) * regime_mult
    rp = risk_pct / 0.02
    specs = [StratSpec(n, s, tr, k, w * rp) for (n, s, k, w) in base]
    cfg = PortfolioConfig(initial_equity=10_000, max_positions=int(cap),
                          danger_hours=TIME_PAUSE.get(time_pause, ()),
                          drawdown_kill_pct=float(dd_thresh), spread_pts=17, slippage_pts=5)
    res = run_portfolio(d["M15"], specs, cfg, regime=reg)
    tp, pips, ppt = pips_from_trades(res["trades_df"])
    return {"profit_points": round(tp, 1), "profit_pips": round(pips, 1),
            "points_per_trade": round(ppt, 1), "trades": res["trades"],
            "net_pnl": round(res["net_pnl"], 0), "pf": round(res["pf"], 3)}


def main():
    d = ROOT / "data"

    print("[1/3] Strategy variants (204)...")
    sv = pd.read_csv(d / "TOP200_strategy_variants.csv")
    out = []
    for i, row in sv.iterrows():
        try:
            r = run_strategy_row(row)
            if r: r["strategy"] = row["strategy"]; out.append(r)
        except Exception as e:
            pass
        if i % 30 == 0: print(f"   {i}/{len(sv)}")
    sv_pips = pd.DataFrame(out).sort_values("profit_pips", ascending=False)
    sv_pips.to_csv(d / "pips_strategy_variants.csv", index=False)
    print(f"   saved pips_strategy_variants.csv ({len(sv_pips)} rows)")

    print("[2/3] Manager configs (200)...")
    mg = pd.read_csv(d / "TOP200_manager_configs.csv")
    out = []
    for i, row in mg.iterrows():
        try:
            r = run_portfolio_row(row["time_pause"], row["regime_mult"], row["cap"], row["risk_pct"], row["dd_thresh"])
            r.update({"time_pause": row["time_pause"], "regime_mult": row["regime_mult"],
                      "cap": row["cap"], "risk_pct": row["risk_pct"], "dd_thresh": row["dd_thresh"]})
            out.append(r)
        except Exception:
            pass
        if i % 40 == 0: print(f"   {i}/{len(mg)}")
    mg_pips = pd.DataFrame(out).sort_values("profit_pips", ascending=False)
    mg_pips.to_csv(d / "pips_manager_configs.csv", index=False)
    print(f"   saved pips_manager_configs.csv ({len(mg_pips)} rows)")

    print("[3/3] Combinations (18)...")
    cb = pd.read_csv(d / "TOP200_combinations.csv")
    out = []
    for i, row in cb.iterrows():
        try:
            r = run_portfolio_row(row["mgr_time_pause"], row["mgr_regime_mult"], row["mgr_cap"], row["mgr_risk_pct"], row.get("mgr_dd_thresh", 0.25))
            r.update({"time_pause": row["mgr_time_pause"], "regime": row["mgr_regime_mult"],
                      "cap": row["mgr_cap"], "risk_pct": row["mgr_risk_pct"]})
            out.append(r)
        except Exception:
            pass
    cb_pips = pd.DataFrame(out).drop_duplicates(subset=["profit_pips","trades"]).sort_values("profit_pips", ascending=False)
    cb_pips.to_csv(d / "pips_combinations.csv", index=False)
    print(f"   saved pips_combinations.csv ({len(cb_pips)} rows)")

    # Combined master file
    print("\n=== SUMMARY (top pips each) ===")
    print("STRATEGY VARIANTS top 10 by pips:")
    print(sv_pips.head(10)[["strategy","profit_pips","profit_points","points_per_trade","trades","pf"]].to_string(index=False))
    print("\nMANAGER CONFIGS top 10 by pips:")
    print(mg_pips.head(10)[["time_pause","regime_mult","cap","risk_pct","profit_pips","trades","pf"]].to_string(index=False))
    print("\nCOMBINATIONS top by pips:")
    print(cb_pips.head(10)[["time_pause","risk_pct","profit_pips","profit_points","trades","pf"]].to_string(index=False))


if __name__ == "__main__":
    main()
