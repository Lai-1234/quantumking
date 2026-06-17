"""Phase D screener: run all 10 strategies on the 6-year XAUUSD dataset,
produce a comparison table, save trades for correlation analysis.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.backtest import BacktestConfig, run
from quantumking.regime import regime
from quantumking.risk import TrailParams

from quantumking.strategies import (
    ma_trend, bands_extreme, asian_breakout, macd_momentum,
    adx_trend, pivot_divergence, vwap_reversion, fractal_breakout,
    pulse_momentum, smc_orderblock,
)


def load_all():
    d = ROOT / "data"
    return {
        "M1": pd.read_parquet(d / "XAUUSD_M1.parquet"),
        "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
        "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
        "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
        "D1": pd.read_parquet(d / "XAUUSD_D1.parquet"),
    }


def run_strategy(name, sigs, df, kind, trail, regime_series=None) -> dict:
    cfg = BacktestConfig(initial_equity=10_000, trail=trail)
    res = run(df, sigs, cfg, regime=regime_series, strategy_kind=kind)
    s = res.stats
    s["strategy"] = name
    # Save trades for correlation
    out = ROOT / "data" / "trades" / f"{name}.parquet"
    out.parent.mkdir(exist_ok=True)
    if not res.trades.empty:
        res.trades.to_parquet(out)
    # Save equity curve
    eq_out = ROOT / "data" / "trades" / f"{name}_equity.parquet"
    res.equity_curve.to_frame("equity").to_parquet(eq_out)
    return s


def main() -> None:
    data = load_all()
    m1, m15, h1, h4, d1 = data["M1"], data["M15"], data["H1"], data["H4"], data["D1"]
    print(f"M15 bars: {len(m15):,}  ({m15.index[0]} -> {m15.index[-1]})\n")

    reg_m15 = regime(m15)
    reg_m1 = regime(m1, fast=7*15, slow=50*15)  # approx scaling for M1

    results = []

    print("[1/10] MA_Trend...")
    sigs = ma_trend.generate_signals(m15, h4)
    results.append(run_strategy("MA_Trend", sigs, m15, "trend", TrailParams(1400, 1400, 100), reg_m15))

    print("[2/10] Bands_Extreme...")
    sigs = bands_extreme.generate_signals(m15)
    results.append(run_strategy("Bands_Extreme", sigs, m15, bands_extreme.KIND, bands_extreme.TRAIL, reg_m15))

    print("[3/10] Asian_Breakout...")
    sigs = asian_breakout.generate_signals(m15)
    results.append(run_strategy("Asian_Breakout", sigs, m15, asian_breakout.KIND, asian_breakout.TRAIL, reg_m15))

    print("[4/10] MACD_Momentum...")
    sigs = macd_momentum.generate_signals(m15, h1, h4)
    results.append(run_strategy("MACD_Momentum", sigs, m15, macd_momentum.KIND, macd_momentum.TRAIL, reg_m15))

    print("[5/10] ADX_Trend...")
    sigs = adx_trend.generate_signals(m15)
    results.append(run_strategy("ADX_Trend", sigs, m15, adx_trend.KIND, adx_trend.TRAIL, reg_m15))

    print("[6/10] Pivot_Divergence...")
    sigs = pivot_divergence.generate_signals(m15, d1)
    results.append(run_strategy("Pivot_Divergence", sigs, m15, pivot_divergence.KIND, pivot_divergence.TRAIL, reg_m15))

    print("[7/10] VWAP_Reversion...")
    sigs = vwap_reversion.generate_signals(m15)
    results.append(run_strategy("VWAP_Reversion", sigs, m15, vwap_reversion.KIND, vwap_reversion.TRAIL, reg_m15))

    print("[8/10] Fractal_Breakout...")
    sigs = fractal_breakout.generate_signals(m15)
    results.append(run_strategy("Fractal_Breakout", sigs, m15, fractal_breakout.KIND, fractal_breakout.TRAIL, reg_m15))

    print("[9/10] Pulse_Momentum (M1)...")
    sigs = pulse_momentum.generate_signals(m1)
    results.append(run_strategy("Pulse_Momentum", sigs, m1, pulse_momentum.KIND, pulse_momentum.TRAIL, None))

    print("[10/10] SMC_OrderBlock...")
    sigs = smc_orderblock.generate_signals(m15)
    results.append(run_strategy("SMC_OrderBlock", sigs, m15, smc_orderblock.KIND, smc_orderblock.TRAIL, reg_m15))

    df = pd.DataFrame(results)
    df = df[["strategy", "trades", "pf", "net_pnl", "win_rate", "expectancy", "max_dd_pct", "sharpe", "final_equity"]]
    df = df.sort_values("pf", ascending=False)
    df["pf"] = df["pf"].round(3)
    df["net_pnl"] = df["net_pnl"].round(0)
    df["win_rate"] = (df["win_rate"] * 100).round(1)
    df["expectancy"] = df["expectancy"].round(2)
    df["max_dd_pct"] = (df["max_dd_pct"] * 100).round(2)
    df["sharpe"] = df["sharpe"].round(2)
    df["final_equity"] = df["final_equity"].round(0)

    print("\n" + "=" * 100)
    print(df.to_string(index=False))
    print("=" * 100)

    out = ROOT / "data" / "screening_summary.csv"
    df.to_csv(out, index=False)
    print(f"\nSummary saved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
