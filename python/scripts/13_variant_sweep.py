"""Wide variant sweep per strategy.

For each strategy we test the cartesian product of:
  exit_mode      : sl_trail, sl_only, trail_only, be_only, fixed_tp, grid
  mtf_filter     : none, H1, H4, H1+H4
  sl_multiplier  : 0.5, 1.0, 1.5, 2.0
  trail variants : (act, dist, step) tuples
  breakeven_pts  : for be_only / grid (100, 150, 200, 300)

Then we rank top 10 variants per strategy by a composite score that
penalizes low trade counts and drawdown spikes.
"""
from __future__ import annotations

import itertools
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.filters import apply_filters
from quantumking.grid_backtest import GridConfig, run_grid
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.variant_engine import VariantConfig, run_variant
from quantumking.strategies import (
    adx_trend, asian_breakout, bands_extreme, fractal_breakout,
    ma_trend, macd_momentum, pivot_divergence, pulse_momentum,
    smc_orderblock, vwap_reversion,
)


def composite_score(s: dict, min_trades: int = 30) -> float:
    """Penalize low trade count and large drawdowns."""
    pf = s["pf"]
    t = s["trades"]
    dd = abs(s["max_dd_pct"])
    if pf <= 0 or t < min_trades:
        return -1.0
    # PF * sqrt(min(t,200)/200) * (1 - min(dd, 0.4))
    import math
    conf = math.sqrt(min(t, 200) / 200)
    dd_penalty = 1.0 - min(dd, 0.4)
    return pf * conf * dd_penalty


def sweep(name, sig_gen_fn, df_run, kind, *, df_h1=None, df_h4=None,
          atr_df=None, base_sigs=None, can_grid=False, reg=None,
          mtf_options=("none",), sl_mults=(1.0,),
          trail_options=None, exit_modes=("sl_trail",), be_pts=(150,),
          tp_pts=(0,)):
    if base_sigs is None:
        base_sigs = sig_gen_fn()
    if trail_options is None:
        trail_options = [TrailParams(1000, 1000, 200)]
    results = []
    for mtf in mtf_options:
        if mtf == "none":
            sigs = base_sigs
        elif mtf == "H1":
            sigs = apply_filters(base_sigs, df_h1=df_h1)
        elif mtf == "H4":
            sigs = apply_filters(base_sigs, df_h4=df_h4)
        elif mtf == "H1+H4":
            sigs = apply_filters(base_sigs, df_h1=df_h1, df_h4=df_h4)
        else:
            sigs = base_sigs

        for exit_mode in exit_modes:
            for sl_mult in sl_mults:
                for trail in trail_options:
                    for be in be_pts:
                        for tp in tp_pts:
                            if exit_mode == "grid":
                                if not can_grid:
                                    continue
                                cfg = GridConfig(breakeven_pts=be)
                                res = run_grid(df_run, sigs, cfg,
                                                regime=reg, strategy_kind=kind)
                                s = res["stats"]
                            else:
                                cfg = VariantConfig(
                                    exit_mode=exit_mode,
                                    trail=trail,
                                    breakeven_pts=be,
                                    fixed_tp_pts=tp,
                                    sl_multiplier=sl_mult,
                                    use_regime=(reg is not None),
                                )
                                res = run_variant(df_run, sigs, cfg,
                                                    regime=reg, strategy_kind=kind)
                                s = res
                            results.append({
                                "strategy": name,
                                "mtf": mtf,
                                "exit_mode": exit_mode,
                                "sl_mult": sl_mult,
                                "trail": f"{trail.activation_pts}/{trail.distance_pts}/{trail.step_pts}",
                                "be_pts": be,
                                "tp_pts": tp,
                                "trades": s["trades"],
                                "pf": round(s["pf"], 3),
                                "net_pnl": round(s["net_pnl"], 0),
                                "win_rate": round(s["win_rate"] * 100, 1),
                                "max_dd_pct": round(s["max_dd_pct"] * 100, 2),
                                "sharpe": round(s.get("sharpe", 0), 2),
                                "score": round(composite_score(s), 3),
                            })
    return results


def main():
    d = ROOT / "data"
    m1 = pd.read_parquet(d / "XAUUSD_M1.parquet")
    m15 = pd.read_parquet(d / "XAUUSD_M15.parquet")
    h1 = pd.read_parquet(d / "XAUUSD_H1.parquet")
    h4 = pd.read_parquet(d / "XAUUSD_H4.parquet")
    d1 = pd.read_parquet(d / "XAUUSD_D1.parquet")
    reg_m15 = regime(m15)

    trail_set = [
        TrailParams(500, 500, 100),
        TrailParams(1000, 1000, 200),
        TrailParams(1400, 1400, 100),
        TrailParams(1400, 1400, 300),
        TrailParams(2000, 1500, 500),
        TrailParams(300, 150, 50),
    ]
    mtf_all = ("none", "H1", "H4", "H1+H4")
    sl_mults = (0.5, 1.0, 1.5, 2.0)
    be_pts = (100, 150, 200, 300)

    all_results = []

    print("[1/10] MA_Trend variants...")
    all_results += sweep(
        "MA_Trend",
        lambda: ma_trend.generate_signals(m15, h4),
        m15, "trend",
        df_h1=h1, df_h4=h4, reg=reg_m15,
        mtf_options=("none", "H1", "H1+H4"),  # H4 already baked in
        sl_mults=sl_mults,
        trail_options=trail_set,
        exit_modes=("sl_trail", "sl_only", "trail_only"),
        be_pts=(150,),
    )

    print("[2/10] MACD_Momentum variants...")
    all_results += sweep(
        "MACD_Momentum",
        lambda: macd_momentum.generate_signals(m15, h1, h4),
        m15, "trend",
        df_h1=h1, df_h4=h4, reg=reg_m15,
        mtf_options=("none", "H1", "H4", "H1+H4"),
        sl_mults=sl_mults,
        trail_options=trail_set,
        exit_modes=("sl_trail", "sl_only", "trail_only"),
        be_pts=(150,),
    )

    print("[3/10] SMC_OrderBlock variants...")
    all_results += sweep(
        "SMC_OrderBlock",
        lambda: smc_orderblock.generate_signals(m15),
        m15, "trend",
        df_h1=h1, df_h4=h4, reg=reg_m15,
        mtf_options=mtf_all,
        sl_mults=sl_mults,
        trail_options=trail_set,
        exit_modes=("sl_trail", "sl_only", "trail_only"),
        be_pts=(150,),
    )

    print("[4/10] ADX_Trend variants...")
    all_results += sweep(
        "ADX_Trend",
        lambda: adx_trend.generate_signals(m15),
        m15, "trend",
        df_h1=h1, df_h4=h4, reg=reg_m15,
        mtf_options=mtf_all,
        sl_mults=sl_mults,
        trail_options=trail_set,
        exit_modes=("sl_trail", "sl_only", "trail_only"),
        be_pts=(150,),
    )

    print("[5/10] Asian_Breakout variants...")
    all_results += sweep(
        "Asian_Breakout",
        lambda: asian_breakout.generate_signals(m15),
        m15, "trend",
        df_h1=h1, df_h4=h4, reg=reg_m15,
        mtf_options=mtf_all,
        sl_mults=sl_mults,
        trail_options=trail_set,
        exit_modes=("sl_trail", "sl_only", "trail_only"),
        be_pts=(150,),
    )

    print("[6/10] Fractal_Breakout variants...")
    all_results += sweep(
        "Fractal_Breakout",
        lambda: fractal_breakout.generate_signals(m15),
        m15, "trend",
        df_h1=h1, df_h4=h4, reg=reg_m15,
        mtf_options=mtf_all,
        sl_mults=sl_mults,
        trail_options=trail_set,
        exit_modes=("sl_trail", "sl_only", "trail_only"),
        be_pts=(150,),
    )

    print("[7/10] Pulse_Momentum variants...")
    all_results += sweep(
        "Pulse_Momentum",
        lambda: pulse_momentum.generate_signals(m1),
        m1, "trend",
        df_h1=h1, df_h4=h4, reg=None,
        mtf_options=("none", "H1", "H4", "H1+H4"),
        sl_mults=sl_mults,
        trail_options=trail_set,
        exit_modes=("sl_trail", "sl_only", "trail_only"),
        be_pts=(150,),
    )

    # Grid strategies: add grid mode + fixed SL alternative
    print("[8/10] Bands_Extreme variants...")
    all_results += sweep(
        "Bands_Extreme",
        lambda: bands_extreme.generate_signals(m15),
        m15, "reversion",
        df_h1=h1, df_h4=h4, reg=reg_m15,
        can_grid=True,
        mtf_options=("none", "H1"),  # reversion + heavy H4 doesn't make sense
        sl_mults=sl_mults,
        trail_options=trail_set,
        exit_modes=("sl_trail", "sl_only", "be_only", "grid"),
        be_pts=(100, 150, 200, 300),
    )

    print("[9/10] Pivot_Divergence variants...")
    all_results += sweep(
        "Pivot_Divergence",
        lambda: pivot_divergence.generate_signals(m15, d1),
        m15, "reversion",
        df_h1=h1, df_h4=h4, reg=reg_m15,
        can_grid=True,
        mtf_options=("none", "H1"),
        sl_mults=sl_mults,
        trail_options=trail_set,
        exit_modes=("sl_trail", "sl_only", "be_only", "grid"),
        be_pts=(100, 150, 200, 300),
    )

    print("[10/10] VWAP_Reversion variants...")
    all_results += sweep(
        "VWAP_Reversion",
        lambda: vwap_reversion.generate_signals(m15),
        m15, "reversion",
        df_h1=h1, df_h4=h4, reg=reg_m15,
        can_grid=True,
        mtf_options=("none", "H1"),
        sl_mults=sl_mults,
        trail_options=trail_set,
        exit_modes=("sl_trail", "sl_only", "be_only", "grid"),
        be_pts=(100, 150, 200, 300),
    )

    df = pd.DataFrame(all_results)
    print(f"\nTotal variants tested: {len(df)}")
    df.to_csv(ROOT / "data" / "variant_sweep_all.csv", index=False)

    # Top 10 per strategy by score
    print("\n" + "=" * 130)
    for name in df["strategy"].unique():
        sub = df[df["strategy"] == name].sort_values("score", ascending=False).head(10)
        print(f"\n### TOP 10 — {name}")
        print(sub.to_string(index=False))
    print("\n" + "=" * 130)

    # Save top-10 per strategy
    top10s = []
    for name in df["strategy"].unique():
        sub = df[df["strategy"] == name].sort_values("score", ascending=False).head(10)
        top10s.append(sub)
    top10 = pd.concat(top10s)
    top10.to_csv(ROOT / "data" / "variant_top10_per_strategy.csv", index=False)
    print(f"\nSaved variant_top10_per_strategy.csv ({len(top10)} rows)")


if __name__ == "__main__":
    main()
