"""SMC pair-test: run SMC (Pass 0 config from user's MT5) paired with each other
strategy at $400 deposit. Tells us which OTHER strategy combines best with SMC.

Pass 0 SMC config (validated in user's MT5):
  SL_Buf=75, Fib_Tol=150, SL_Mult=0.5, Max_SL=400, H4 filter OFF,
  Trail 1000/1000/500. Result alone: PF 1.41, DD 19.46%, 511 trades.

We cap SMC's sl_pts at Max_SL (400) to mirror the v1.12 cap in MQL5.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.filters import apply_filters
from quantumking.indicators import atr
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.risk import POINT, TrailParams
from quantumking.strategies import (
    adx_trend, ma_trend, macd_momentum, pivot_divergence, smc_orderblock,
)

POINTS_PER_PIP = 10.0


def _data():
    d = ROOT / "data"
    return {
        "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
        "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
        "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
        "D1": pd.read_parquet(d / "XAUUSD_D1.parquet"),
    }


def smc_pass0_spec(data: dict) -> StratSpec:
    """SMC at Pass 0 config: SL_Buf=75, Fib_Tol=150, SL_Mult=0.5, Max_SL=400,
    H4 OFF, Trail 1000/1000/500."""
    p = smc_orderblock.SmcParams(sl_buffer_pts=75, fib_tolerance_pts=150, scan_window=80)
    sigs = smc_orderblock.generate_signals(data["M15"], p)
    # SL_Mult = 0.5
    sigs["sl_pts"] = sigs["sl_pts"] * 0.5
    # Max_SL = 400 (v1.12 cap)
    sigs["sl_pts"] = sigs["sl_pts"].clip(upper=400)
    # H4 filter OFF — do NOT apply_filters(df_h4=...)
    return StratSpec(name="SMC_OrderBlock", signals=sigs,
                     trail=TrailParams(1000, 1000, 500), kind="trend", weight=1.0)


def ma_locked_spec(data: dict) -> StratSpec:
    """MA_Trend at the user's live LOCKED spec (Fast20/Slow70/KDJ7/etc)."""
    p = ma_trend.MAParams(fast_ema=20, slow_ema=70, kdj_period=7, kdj_d=2, kdj_s=2,
                          stoch_ob=70, stoch_os=40, fibo_top=0.5, fibo_bottom=0.677,
                          zone_buffer_pts=150, sl_buffer_pts=300, max_sl_pts=800)
    sigs = ma_trend.generate_signals(data["M15"], data["H4"], p)
    return StratSpec(name="MA_Trend", signals=sigs,
                     trail=TrailParams(1400, 1400, 100), kind="trend", weight=1.0)


def best_variant_spec(strategy: str, data: dict) -> StratSpec | None:
    """Build a strategy spec from its best layer1/layer1b research row."""
    d = ROOT / "data"
    l1 = pd.read_csv(d / "layer1_top50_full.csv")
    l1b_path = d / "layer1b_top50_full.csv"

    if strategy == "ADX_Trend":
        row = l1[l1["strategy"] == "ADX_Trend"].sort_values("score", ascending=False).iloc[0]
        sigs = adx_trend.generate_signals(data["M15"],
                 adx_trend.AdxParams(period=int(row["period"]),
                                     threshold=float(row["threshold"])))
        mtf = str(row.get("mtf", "none"))
        if mtf == "H1": sigs = apply_filters(sigs, df_h1=data["H1"])
        elif mtf == "H4": sigs = apply_filters(sigs, df_h4=data["H4"])
        elif mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=data["H1"], df_h4=data["H4"])
        sigs["sl_pts"] = sigs["sl_pts"] * float(row.get("sl_mult", 1.0))
        return StratSpec("ADX_Trend", sigs, TrailParams(*eval(row["trail"])),
                         kind="trend", weight=0.5)

    if strategy == "MACD_Momentum":
        row = l1[l1["strategy"] == "MACD_Momentum"].sort_values("score", ascending=False).iloc[0]
        sigs = macd_momentum.generate_signals(data["M15"], data["H1"], data["H4"],
                 macd_momentum.MacdParams(fast=int(row["fast"]), slow=int(row["slow"]),
                                          signal=int(row["sig"])))
        mtf = str(row.get("mtf", "none"))
        if mtf == "H1": sigs = apply_filters(sigs, df_h1=data["H1"])
        elif mtf == "H4": sigs = apply_filters(sigs, df_h4=data["H4"])
        elif mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=data["H1"], df_h4=data["H4"])
        sigs["sl_pts"] = sigs["sl_pts"] * float(row.get("sl_mult", 1.0))
        return StratSpec("MACD_Momentum", sigs, TrailParams(*eval(row["trail"])),
                         kind="trend", weight=0.5)

    if strategy == "Pivot_Divergence_noGrid" and l1b_path.exists():
        l1b = pd.read_csv(l1b_path)
        row = l1b[l1b["strategy"] == "Pivot_Divergence_noGrid"]\
              .sort_values("score", ascending=False).iloc[0]
        sigs = pivot_divergence.generate_signals(data["M15"], data["D1"],
                 pivot_divergence.PivotParams(rsi_period=int(row["rsi_p"]),
                                              touch_buffer_pts=int(row["touch"]),
                                              sl_pts=1500))
        mtf = str(row.get("mtf", "none"))
        if mtf == "H1": sigs = apply_filters(sigs, df_h1=data["H1"])
        elif mtf == "H4": sigs = apply_filters(sigs, df_h4=data["H4"])
        sigs["sl_pts"] = sigs["sl_pts"] * float(row.get("sl_mult", 1.0))
        return StratSpec("Pivot_Divergence", sigs, TrailParams(1400, 1400, 100),
                         kind="reversion", weight=0.5)

    return None


def pips_from_trades(tdf: pd.DataFrame):
    if tdf is None or tdf.empty:
        return 0.0, 0.0, 0.0
    pts = ((tdf["exit"] - tdf["entry"]) / POINT * tdf["side"])
    total_pts = float(pts.sum())
    pos = float(pts[pts > 0].sum())
    neg = float(-pts[pts < 0].sum())
    pip_pf = (pos / neg) if neg > 0 else (99.0 if pos > 0 else 0.0)
    return total_pts / POINTS_PER_PIP, pip_pf, total_pts


def run_pair(label: str, specs: list, data: dict) -> dict:
    reg = atr(data["M15"], 7) > atr(data["M15"], 50) * 1.2
    cfg = PortfolioConfig(initial_equity=400, max_positions=6, spread_cap_pts=400,
                          danger_hours=(23, 0), drawdown_kill_pct=0.95,
                          spread_pts=17, slippage_pts=5)
    res = run_portfolio(data["M15"], specs, cfg, regime=reg)
    pips, pip_pf, _ = pips_from_trades(res.get("trades_df"))
    return {
        "pair": label,
        "n_strats": len(specs),
        "trades": res["trades"],
        "pip_pf": round(pip_pf, 3),
        "usd_pf": round(res["pf"], 3),
        "profit_pips": round(pips, 1),
        "max_dd_pct": round(abs(res["max_dd_pct"]) * 100, 2),
        "sharpe": round(res["sharpe"], 2),
        "net_pnl_usd": round(res["net_pnl"], 1),
    }


def main():
    data = _data()
    smc = smc_pass0_spec(data)

    pairs = [
        ("SMC alone (baseline)", [smc]),
        ("SMC + MA_Trend",       [smc, ma_locked_spec(data)]),
        ("SMC + ADX_Trend",      [smc, best_variant_spec("ADX_Trend", data)]),
        ("SMC + MACD_Momentum",  [smc, best_variant_spec("MACD_Momentum", data)]),
        ("SMC + Pivot_noGrid",   [smc, best_variant_spec("Pivot_Divergence_noGrid", data)]),
    ]

    rows = []
    for label, specs in pairs:
        specs = [s for s in specs if s is not None]
        if len(specs) == 0:
            continue
        print(f"Running: {label} ... ", end="", flush=True)
        try:
            row = run_pair(label, specs, data)
            rows.append(row)
            print(f"PF {row['pip_pf']}  DD {row['max_dd_pct']}%  "
                  f"trades {row['trades']}  pips {row['profit_pips']}")
        except Exception as e:
            print(f"FAILED: {e}")

    df = pd.DataFrame(rows)
    df["dd_pass"] = df["max_dd_pct"] <= 20.0
    df = df.sort_values(["dd_pass", "pip_pf"], ascending=[False, False])
    df.to_csv(ROOT / "data" / "smc_pair_test.csv", index=False)

    print("\n=== SMC PAIR-TEST RESULTS (sorted: DD<=20% first, then by pip-PF) ===")
    cols = ["pair", "pip_pf", "profit_pips", "trades", "max_dd_pct", "sharpe"]
    with pd.option_context("display.max_colwidth", 40, "display.width", 200):
        print(df[cols].to_string(index=False))
    print("\nSaved: data/smc_pair_test.csv")


if __name__ == "__main__":
    main()
