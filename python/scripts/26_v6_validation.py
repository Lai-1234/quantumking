"""Audit v6 validation: walk-forward + Monte Carlo on the v6 5-strategy portfolio.

Confirms the exhaustive-grid winner is not curve-fit.
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
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, ma_trend, macd_momentum, pivot_divergence, smc_orderblock,
)

SPLIT = pd.Timestamp("2024-01-01", tz="UTC")


def build_v6_specs(data, weight_scale=1.0):
    """The exact v6 winning portfolio config."""
    m15, h1, h4, d1 = data["M15"], data["H1"], data["H4"], data["D1"]

    # MA_Trend: Fast 10, Slow 80, KDJ 9/2/2, Fibo 0.4
    ma_p = ma_trend.MAParams(fast_ema=10, slow_ema=80, kdj_period=9, kdj_d=2, kdj_s=2,
                                stoch_ob=70, stoch_os=40, fibo_top=0.5, fibo_bottom=0.4,
                                zone_buffer_pts=150, sl_buffer_pts=300, max_sl_pts=800)
    ma_sigs = ma_trend.generate_signals(m15, h4, ma_p)

    # MACD: Fast 18, Slow 35, Signal 7, H1+H4, sl_mult 0.5
    macd_p = macd_momentum.MacdParams(fast=18, slow=35, signal=7)
    macd_sigs = apply_filters(macd_momentum.generate_signals(m15, h1, h4, macd_p), df_h1=h1, df_h4=h4)
    macd_sigs["sl_pts"] = macd_sigs["sl_pts"] * 0.5

    # SMC: sl_buf 60, fib_tol 200, scan 100, H1+H4, sl_mult 0.5
    smc_p = smc_orderblock.SmcParams(sl_buffer_pts=60, fib_tolerance_pts=200, scan_window=100)
    smc_sigs = apply_filters(smc_orderblock.generate_signals(m15, smc_p), df_h1=h1, df_h4=h4)
    smc_sigs["sl_pts"] = smc_sigs["sl_pts"] * 0.5

    # ADX: period 14, threshold 25, H1+H4, sl_mult 1.0
    adx_p = adx_trend.AdxParams(period=14, threshold=25.0)
    adx_sigs = apply_filters(adx_trend.generate_signals(m15, adx_p), df_h1=h1, df_h4=h4)

    # Pivot no-grid: rsi 10, touch 300, H1+H4, sl_mult 0.5
    piv_p = pivot_divergence.PivotParams(rsi_period=10, touch_buffer_pts=300, sl_pts=1500)
    piv_sigs = apply_filters(pivot_divergence.generate_signals(m15, d1, piv_p), df_h1=h1, df_h4=h4)
    piv_sigs["sl_pts"] = piv_sigs["sl_pts"] * 0.5

    trail = TrailParams(2000, 1500, 500)
    return [
        StratSpec("MA_Trend", ma_sigs, trail, "trend", 1.0 * weight_scale),
        StratSpec("SMC_OrderBlock", smc_sigs, trail, "trend", 0.7 * weight_scale),
        StratSpec("MACD_Momentum", macd_sigs, trail, "trend", 0.3 * weight_scale),
        StratSpec("ADX_Trend", adx_sigs, trail, "trend", 0.3 * weight_scale),
        StratSpec("Pivot_Divergence", piv_sigs, trail, "reversion", 0.4 * weight_scale),
    ]


def slice_data(data, start, end):
    out = {}
    for k, df in data.items():
        out[k] = df[(df.index >= start) & (df.index < end)]
    return out


def main():
    d = ROOT / "data"
    data = {
        "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
        "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
        "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
        "D1": pd.read_parquet(d / "XAUUSD_D1.parquet"),
    }
    cfg = PortfolioConfig(initial_equity=10_000, max_positions=6,
                          danger_hours=(), drawdown_kill_pct=0.25,
                          spread_pts=17, slippage_pts=5)

    # ============================================================
    # PART 1: Full-period baseline
    # ============================================================
    print("=" * 60)
    print("PART 1: Full 6-year baseline (v6 config)")
    print("=" * 60)
    specs = build_v6_specs(data)
    reg = regime(data["M15"])
    res_full = run_portfolio(data["M15"], specs, cfg, regime=reg)
    print(f"  PF={res_full['pf']:.3f}  Sharpe={res_full['sharpe']:.2f}  "
          f"DD={res_full['max_dd_pct']*100:.1f}%  PnL=${res_full['net_pnl']:.0f}  "
          f"trades={res_full['trades']}")
    print("\n  Per-strategy breakdown:")
    print(res_full["by_strat"].to_string())

    # ============================================================
    # PART 2: Walk-forward (IS 2020-23 vs OOS 2024-26)
    # ============================================================
    print("\n" + "=" * 60)
    print("PART 2: Walk-forward (IS 2020-2023 vs OOS 2024-2026)")
    print("=" * 60)
    is_data = slice_data(data, pd.Timestamp("2020-01-01", tz="UTC"), SPLIT)
    oos_data = slice_data(data, SPLIT, pd.Timestamp("2026-05-01", tz="UTC"))

    is_specs = build_v6_specs(is_data)
    is_reg = regime(is_data["M15"])
    res_is = run_portfolio(is_data["M15"], is_specs, cfg, regime=is_reg)

    oos_specs = build_v6_specs(oos_data)
    oos_reg = regime(oos_data["M15"])
    res_oos = run_portfolio(oos_data["M15"], oos_specs, cfg, regime=oos_reg)

    print(f"  IS  (2020-23): PF={res_is['pf']:.3f}  Sharpe={res_is['sharpe']:.2f}  "
          f"DD={res_is['max_dd_pct']*100:.1f}%  trades={res_is['trades']}")
    print(f"  OOS (2024-26): PF={res_oos['pf']:.3f}  Sharpe={res_oos['sharpe']:.2f}  "
          f"DD={res_oos['max_dd_pct']*100:.1f}%  trades={res_oos['trades']}")
    ratio = res_oos['pf'] / res_is['pf'] if res_is['pf'] > 0 else 0
    print(f"  OOS/IS PF ratio: {ratio:.2f}  ({'ROBUST' if ratio >= 0.7 else 'CURVE-FIT WARNING'})")

    # Per-strategy walk-forward (which strategy degrades?)
    print("\n  Per-strategy IS vs OOS:")
    print("  IS:")
    print(res_is["by_strat"].to_string())
    print("  OOS:")
    print(res_oos["by_strat"].to_string())

    # ============================================================
    # PART 3: Monte Carlo bootstrap (trade reorder)
    # ============================================================
    print("\n" + "=" * 60)
    print("PART 3: Monte Carlo 5000-iter bootstrap on full-period trades")
    print("=" * 60)
    trades = res_full["trades_df"]
    pnls = trades["pnl_usd"].to_numpy()
    n = len(pnls)
    rng = np.random.default_rng(42)
    init = 10_000

    pfs, dds = np.zeros(5000), np.zeros(5000)
    for k in range(5000):
        seq = pnls[rng.permutation(n)]
        wins = seq[seq > 0].sum()
        losses = -seq[seq < 0].sum()
        pfs[k] = wins / losses if losses > 0 else 99
        eq = init + np.cumsum(seq)
        run_max = np.maximum.accumulate(eq)
        dds[k] = ((eq - run_max) / run_max).min()

    pct = lambda a, p: np.percentile(a, p)
    print(f"  PF      median={np.median(pfs):.3f}  90% CI=[{pct(pfs,5):.3f}, {pct(pfs,95):.3f}]")
    print(f"  MaxDD   median={np.median(dds)*100:.1f}%  90% CI=[{pct(dds,5)*100:.1f}%, {pct(dds,95)*100:.1f}%]  worst1%={pct(dds,1)*100:.1f}%")
    print(f"  P(PF>1.0)={np.mean(pfs>1.0)*100:.1f}%   P(PF>1.3)={np.mean(pfs>1.3)*100:.1f}%")
    print(f"  P(MaxDD>20%)={np.mean(dds<=-0.20)*100:.1f}%   P(MaxDD>25%)={np.mean(dds<=-0.25)*100:.1f}%")

    pd.DataFrame({"pf": pfs, "max_dd": dds}).to_csv(d / "v6_monte_carlo.csv", index=False)
    print("\n  Saved v6_monte_carlo.csv")


if __name__ == "__main__":
    main()
