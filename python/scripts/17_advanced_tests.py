"""Advanced tests: spread/slippage, confluence ensemble, vol-adaptive SL, news filter.

For each enhancement, run the 4-strategy portfolio and report PF/Sharpe/DD delta.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.filters import apply_filters
from quantumking.indicators import atr
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.regime import regime
from quantumking.risk import POINT, TrailParams
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


def base_specs(data, atr_scale: pd.Series | None = None) -> list:
    m15, h1, h4 = data["M15"], data["H1"], data["H4"]
    # Apply MTF filters consistent with audit v3 best variants
    ma_sigs = apply_filters(ma_trend.generate_signals(m15, h4), df_h1=h1, df_h4=h4)
    macd_sigs = apply_filters(macd_momentum.generate_signals(m15, h1, h4), df_h1=h1, df_h4=h4)
    smc_sigs = apply_filters(smc_orderblock.generate_signals(m15), df_h1=h1, df_h4=h4)
    adx_sigs = apply_filters(adx_trend.generate_signals(m15), df_h1=h1, df_h4=h4)

    # Volatility-adaptive SL: scale sl_pts by ATR ratio
    if atr_scale is not None:
        for s in [ma_sigs, macd_sigs, smc_sigs, adx_sigs]:
            s["sl_pts"] = s["sl_pts"] * atr_scale

    return [
        StratSpec("MA_Trend", ma_sigs, TrailParams(1400, 1400, 300), kind="trend", weight=1.0),
        StratSpec("MACD_Momentum", macd_sigs, TrailParams(1000, 1000, 100), kind="trend", weight=0.5),
        StratSpec("SMC_OrderBlock", smc_sigs, TrailParams(750, 1500, 500), kind="trend", weight=0.7),
        StratSpec("ADX_Trend", adx_sigs, TrailParams(2000, 1500, 500), kind="trend", weight=0.4),
    ]


def block_news_hours(sigs: pd.DataFrame, hours: list[tuple[int, int]]) -> pd.DataFrame:
    """Zero out signals during specified UTC hour windows."""
    out = sigs.copy()
    for h_start, h_end in hours:
        mask = (out.index.hour >= h_start) & (out.index.hour <= h_end)
        out.loc[mask, "signal"] = 0
        out.loc[mask, "sl_pts"] = np.nan
    return out


def confluence_filter(specs: list, min_agree: int = 2) -> list:
    """Replace each strategy's signal with: only fire when min_agree strategies agree."""
    # Build a long-confluence and short-confluence mask
    long_count = sum((s.signals["signal"] == 1).astype(int) for s in specs)
    short_count = sum((s.signals["signal"] == -1).astype(int) for s in specs)
    out = []
    for s in specs:
        sigs = s.signals.copy()
        sigs.loc[(sigs["signal"] == 1) & (long_count < min_agree), "signal"] = 0
        sigs.loc[(sigs["signal"] == 1) & (long_count < min_agree), "sl_pts"] = np.nan
        sigs.loc[(sigs["signal"] == -1) & (short_count < min_agree), "signal"] = 0
        sigs.loc[(sigs["signal"] == -1) & (short_count < min_agree), "sl_pts"] = np.nan
        out.append(StratSpec(s.name, sigs, s.trail, s.kind, s.weight))
    return out


def report(name: str, res: dict) -> dict:
    s = {
        "config": name,
        "trades": res["trades"],
        "pf": round(res["pf"], 3),
        "net_pnl": round(res["net_pnl"], 0),
        "win_rate_pct": round(res["win_rate"] * 100, 1),
        "max_dd_pct": round(res["max_dd_pct"] * 100, 2),
        "sharpe": round(res["sharpe"], 2),
        "final_equity": round(res["final_equity"], 0),
    }
    print(f"{name:55s}  PF={s['pf']:.2f}  Sharpe={s['sharpe']:.2f}  DD={s['max_dd_pct']:.1f}%  PnL=${s['net_pnl']:.0f}  trades={s['trades']}")
    return s


def main():
    data = load()
    m15 = data["M15"]
    reg = regime(m15)

    results = []

    # ============================================================
    # BASELINE: No execution costs, no filters
    # ============================================================
    print("\n=== BASELINE (no spread, no news filter, no confluence) ===")
    specs = base_specs(data)
    cfg = PortfolioConfig(initial_equity=10_000, spread_pts=0, slippage_pts=0)
    res = run_portfolio(m15, specs, cfg, regime=reg)
    results.append(report("Baseline (no costs)", res))

    # ============================================================
    # +1: Realistic spread (17 pts) + slippage (5 pts)
    # ============================================================
    print("\n=== +SPREAD+SLIPPAGE (17 pts spread, 5 pts slippage) ===")
    specs = base_specs(data)
    cfg = PortfolioConfig(initial_equity=10_000, spread_pts=17, slippage_pts=5)
    res = run_portfolio(m15, specs, cfg, regime=reg)
    results.append(report("+ Spread 17pts + Slippage 5pts", res))

    # ============================================================
    # +2: Volatility-adaptive SL (scale by ATR-vs-median)
    # ============================================================
    print("\n=== +VOL-ADAPTIVE SL (ATR-scaled) ===")
    a = atr(m15, 14)
    a_med = a.rolling(500, min_periods=50).median()
    atr_scale = (a / a_med).clip(0.5, 2.0).fillna(1.0)
    specs = base_specs(data, atr_scale=atr_scale)
    cfg = PortfolioConfig(initial_equity=10_000, spread_pts=17, slippage_pts=5)
    res = run_portfolio(m15, specs, cfg, regime=reg)
    results.append(report("+ ATR-adaptive SL", res))

    # ============================================================
    # +3: News filter (block 30 min around 12:30, 13:30, 14:00, 18:00 UTC)
    #     12:30 = NFP / CPI release (1st Friday / monthly)
    #     14:00 = FOMC release
    #     18:00 = FOMC press conf
    # ============================================================
    print("\n=== +NEWS FILTER (block 12:00-14:30, 18:00-19:00 UTC) ===")
    specs = base_specs(data, atr_scale=atr_scale)
    news_hours = [(12, 14), (18, 18)]
    specs = [StratSpec(s.name, block_news_hours(s.signals, news_hours),
                       s.trail, s.kind, s.weight) for s in specs]
    res = run_portfolio(m15, specs, cfg, regime=reg)
    results.append(report("+ News filter", res))

    # ============================================================
    # +4: Confluence-only (2+ strategies must agree)
    # ============================================================
    print("\n=== +CONFLUENCE-ONLY (min 2 strategies agree same direction) ===")
    specs = base_specs(data, atr_scale=atr_scale)
    specs = [StratSpec(s.name, block_news_hours(s.signals, news_hours),
                       s.trail, s.kind, s.weight) for s in specs]
    specs_conf = confluence_filter(specs, min_agree=2)
    res = run_portfolio(m15, specs_conf, cfg, regime=reg)
    results.append(report("+ Confluence 2+", res))

    # ============================================================
    # +5: Confluence-only at 3+ (super strict)
    # ============================================================
    print("\n=== +CONFLUENCE 3+ (very strict) ===")
    specs_conf3 = confluence_filter(specs, min_agree=3)
    res = run_portfolio(m15, specs_conf3, cfg, regime=reg)
    results.append(report("+ Confluence 3+", res))

    # ============================================================
    # Save & summary
    # ============================================================
    df = pd.DataFrame(results)
    df.to_csv(ROOT / "data" / "advanced_tests.csv", index=False)

    print("\n" + "=" * 100)
    print("SUMMARY: cumulative-improvement progression")
    print("=" * 100)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
