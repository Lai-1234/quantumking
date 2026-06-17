"""Comprehensive audit of CStrategyManager + CRiskManager + CPositionManager parameters.

Tests every manager knob independently with the 4-strategy portfolio:

A. Time-pause hours
B. Regime gate ON vs OFF
C. Global position cap
D. Spread cap
E. Risk per trade
F. Drawdown emergency threshold
G. Lot-sizing ceiling per $1000 equity
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.filters import apply_filters
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, ma_trend, macd_momentum, smc_orderblock,
)


def load():
    d = ROOT / "data"
    return {
        "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
        "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
        "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
    }


def base_specs(data):
    m15, h1, h4 = data["M15"], data["H1"], data["H4"]
    return [
        StratSpec("MA_Trend", apply_filters(ma_trend.generate_signals(m15, h4), df_h1=h1, df_h4=h4),
                  TrailParams(1400, 1400, 300), kind="trend", weight=1.0),
        StratSpec("MACD_Momentum", apply_filters(macd_momentum.generate_signals(m15, h1, h4), df_h1=h1, df_h4=h4),
                  TrailParams(1000, 1000, 100), kind="trend", weight=0.3),
        StratSpec("SMC_OrderBlock", apply_filters(smc_orderblock.generate_signals(m15), df_h1=h1, df_h4=h4),
                  TrailParams(750, 1500, 500), kind="trend", weight=0.7),
        StratSpec("ADX_Trend", apply_filters(adx_trend.generate_signals(m15), df_h1=h1, df_h4=h4),
                  TrailParams(2000, 1500, 500), kind="trend", weight=0.3),
    ]


def report(label: str, res: dict) -> dict:
    s = {
        "config": label,
        "trades": res["trades"],
        "pf": round(res["pf"], 3),
        "net_pnl": round(res["net_pnl"], 0),
        "win_rate_pct": round(res["win_rate"] * 100, 1),
        "max_dd_pct": round(res["max_dd_pct"] * 100, 2),
        "sharpe": round(res["sharpe"], 2),
        "final_equity": round(res["final_equity"], 0),
    }
    print(f"  {label:45s}  PF={s['pf']:.2f}  Sharpe={s['sharpe']:.2f}  DD={s['max_dd_pct']:.1f}%  PnL=${s['net_pnl']:.0f}  trades={s['trades']}")
    return s


def main():
    data = load()
    m15 = data["M15"]
    reg = regime(m15)

    # Base config (current production after v4)
    base_cfg = PortfolioConfig(
        initial_equity=10_000,
        max_positions=6,
        spread_cap_pts=400,
        danger_hours=(23, 0),
        drawdown_kill_pct=0.25,
        spread_pts=17,
        slippage_pts=5,
    )
    specs = base_specs(data)

    all_results = []

    # ============================================================
    # A. TIME-PAUSE VARIANTS  (the user's specific question)
    # ============================================================
    print("\n=== A. TIME-PAUSE VARIANTS ===")
    time_options = [
        ("No pause (24/7)", ()),
        ("23-00 (current)", (23, 0)),
        ("22-01 wider", (22, 23, 0, 1)),
        ("23-01", (23, 0, 1)),
        ("00-02 only", (0, 1, 2)),
        ("Asian close 22-00", (22, 23, 0)),
        ("23-00 + Fri close 21+", (21, 22, 23, 0)),
    ]
    for label, hours in time_options:
        cfg = replace(base_cfg, danger_hours=tuple(hours))
        res = run_portfolio(m15, specs, cfg, regime=reg)
        all_results.append(report(f"time:{label}", res))

    # ============================================================
    # B. REGIME GATE ON/OFF
    # ============================================================
    print("\n=== B. REGIME GATE ===")
    res = run_portfolio(m15, specs, base_cfg, regime=reg)
    all_results.append(report("regime:ON (ATR fast > slow*1.2)", res))
    res = run_portfolio(m15, specs, base_cfg, regime=None)
    all_results.append(report("regime:OFF (always trade)", res))

    # Regime variants: different multipliers
    from quantumking.indicators import atr
    for mult in [1.0, 1.1, 1.2, 1.3, 1.5, 2.0]:
        a_fast = atr(m15, 7)
        a_slow = atr(m15, 50)
        reg_v = a_fast > a_slow * mult
        res = run_portfolio(m15, specs, base_cfg, regime=reg_v)
        all_results.append(report(f"regime:mult={mult}", res))

    # ============================================================
    # C. GLOBAL POSITION CAP
    # ============================================================
    print("\n=== C. GLOBAL POSITION CAP ===")
    for cap in [2, 3, 4, 5, 6, 8, 10, 12]:
        cfg = replace(base_cfg, max_positions=cap)
        res = run_portfolio(m15, specs, cfg, regime=reg)
        all_results.append(report(f"cap:{cap}", res))

    # ============================================================
    # D. SPREAD CAP
    # ============================================================
    print("\n=== D. SPREAD CAP ===")
    for sc in [100, 200, 300, 400, 500, 700, 1000, 99999]:
        cfg = replace(base_cfg, spread_cap_pts=sc)
        res = run_portfolio(m15, specs, cfg, regime=reg)
        all_results.append(report(f"spread_cap:{sc}", res))

    # ============================================================
    # E. RISK % (per trade, via weight adjustment in specs)
    # ============================================================
    print("\n=== E. RISK PCT PER TRADE (weight = risk_pct/0.02) ===")
    for rp in [0.005, 0.01, 0.015, 0.02, 0.03, 0.05]:
        m = rp / 0.02  # scale all weights proportionally
        specs_r = [StratSpec(s.name, s.signals, s.trail, s.kind, s.weight * m) for s in specs]
        res = run_portfolio(m15, specs_r, base_cfg, regime=reg)
        all_results.append(report(f"risk_pct:{rp}", res))

    # ============================================================
    # F. DD EMERGENCY THRESHOLD
    # ============================================================
    print("\n=== F. DRAWDOWN EMERGENCY THRESHOLD ===")
    for dd in [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.99]:
        cfg = replace(base_cfg, drawdown_kill_pct=dd)
        res = run_portfolio(m15, specs, cfg, regime=reg)
        all_results.append(report(f"dd_threshold:{dd}", res))

    # ============================================================
    # SAVE
    # ============================================================
    df = pd.DataFrame(all_results)
    df.to_csv(ROOT / "data" / "manager_audit.csv", index=False)

    print("\n" + "=" * 110)
    print("RANKED BY SHARPE")
    print("=" * 110)
    print(df.sort_values("sharpe", ascending=False).head(20).to_string(index=False))


if __name__ == "__main__":
    main()
