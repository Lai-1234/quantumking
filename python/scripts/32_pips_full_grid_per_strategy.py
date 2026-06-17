"""Compute profit-in-PIPS for the FULL fine grid, then output top 200 per strategy.

Re-runs every entry-param x exit-variant combo (same grid as 21b_layer1_cached),
captures lot-independent pips = sum((exit-entry)/POINT*side)/10, and writes:
  - pips_top200_<STRATEGY>.csv  (one per strategy, ranked by pips)
  - pips_all_per_strategy.csv   (combined, categorized)
"""
from __future__ import annotations

import itertools
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.backtest import BacktestConfig, run
from quantumking.filters import apply_filters
from quantumking.regime import regime
from quantumking.risk import POINT, TrailParams
from quantumking.strategies import (
    adx_trend, asian_breakout, fractal_breakout, ma_trend, macd_momentum, smc_orderblock,
)

POINTS_PER_PIP = 10.0
TRAILS = [(500, 500, 100), (1000, 1000, 200), (1400, 1400, 100),
          (1400, 1400, 300), (2000, 1500, 500), (300, 150, 50)]
MTFS = ["none", "H1", "H4", "H1+H4"]
SL_MULTS = [0.5, 1.0, 1.5, 2.0]

_D = {}
def D():
    if not _D:
        d = ROOT / "data"
        _D["M15"] = pd.read_parquet(d / "XAUUSD_M15.parquet")
        _D["H1"] = pd.read_parquet(d / "XAUUSD_H1.parquet")
        _D["H4"] = pd.read_parquet(d / "XAUUSD_H4.parquet")
        _D["reg"] = regime(_D["M15"])
    return _D


def pips(trades):
    if trades is None or trades.empty:
        return 0.0, 0
    pts = ((trades["exit"] - trades["entry"]) / POINT * trades["side"]).sum()
    return float(pts) / POINTS_PER_PIP, len(trades)


def _filt(sigs, mtf, h1, h4):
    if mtf == "H1": return apply_filters(sigs, df_h1=h1)
    if mtf == "H4": return apply_filters(sigs, df_h4=h4)
    if mtf == "H1+H4": return apply_filters(sigs, df_h1=h1, df_h4=h4)
    return sigs


def _bt(sigs, trail, reg, m15):
    res = run(m15, sigs, BacktestConfig(initial_equity=10_000, trail=TrailParams(*trail)),
              regime=reg, strategy_kind="trend")
    pp, nt = pips(res.trades)
    return pp, nt, res.stats["pf"], res.stats["net_pnl"], res.stats["max_dd_pct"]


def _variants(base_sigs, meta, m15, reg, h1, h4, use_mtf=True, use_sl=True):
    rows = []
    mtfs = MTFS if use_mtf else ["none"]
    slm = SL_MULTS if use_sl else [1.0]
    for mtf in mtfs:
        s0 = _filt(base_sigs, mtf, h1, h4)
        for sl in slm:
            s = s0.copy(); s["sl_pts"] = s["sl_pts"] * sl
            for tr in TRAILS:
                pp, nt, pf, pnl, dd = _bt(s, tr, reg, m15)
                rows.append({**meta, "mtf": mtf, "sl_mult": sl, "trail": str(tr),
                             "profit_pips": round(pp, 1), "profit_points": round(pp*10, 1),
                             "points_per_trade": round(pp*10/nt, 1) if nt else 0,
                             "trades": nt, "pf": round(pf, 3),
                             "net_pnl": round(pnl, 0), "max_dd_pct": round(dd*100, 2)})
    return rows


def eval_ma(p, d):
    f, sl, kp, kd, fb = p
    if sl <= f: return []
    mp = ma_trend.MAParams(fast_ema=f, slow_ema=sl, kdj_period=kp, kdj_d=kd, kdj_s=2,
                              fibo_top=0.5, fibo_bottom=fb)
    base = ma_trend.generate_signals(d["M15"], d["H4"], mp)
    return _variants(base, {"strategy":"MA_Trend","fast":f,"slow":sl,"kdj":kp,"kdj_d":kd,"fibo":fb},
                     d["M15"], d["reg"], d["H1"], d["H4"], use_mtf=False, use_sl=False)

def eval_macd(p, d):
    f, s, sig = p
    if s <= f: return []
    base = macd_momentum.generate_signals(d["M15"], d["H1"], d["H4"], macd_momentum.MacdParams(f, s, sig))
    return _variants(base, {"strategy":"MACD_Momentum","fast":f,"slow":s,"sig":sig},
                     d["M15"], d["reg"], d["H1"], d["H4"])

def eval_smc(p, d):
    sb, ft, sc = p
    base = smc_orderblock.generate_signals(d["M15"], smc_orderblock.SmcParams(sb, ft, sc))
    return _variants(base, {"strategy":"SMC_OrderBlock","sl_buf":sb,"fib_tol":ft,"scan":sc},
                     d["M15"], d["reg"], d["H1"], d["H4"])

def eval_adx(p, d):
    per, th = p
    base = adx_trend.generate_signals(d["M15"], adx_trend.AdxParams(per, th))
    return _variants(base, {"strategy":"ADX_Trend","period":per,"threshold":th},
                     d["M15"], d["reg"], d["H1"], d["H4"])

def eval_asian(p, d):
    sh, eh, wh, body, sb = p
    if eh <= sh: return []
    base = asian_breakout.generate_signals(d["M15"], asian_breakout.AsianParams(sh, eh, wh, body, sb))
    return _variants(base, {"strategy":"Asian_Breakout","start":sh,"end":eh,"win":wh,"body":body,"sl_buf":sb},
                     d["M15"], d["reg"], d["H1"], d["H4"], use_mtf=False)

def eval_fractal(p, d):
    bp, sb = p
    base = fractal_breakout.generate_signals(d["M15"], fractal_breakout.FractalParams(bp, sb))
    return _variants(base, {"strategy":"Fractal_Breakout","buf":bp,"sl_buf":sb},
                     d["M15"], d["reg"], d["H1"], d["H4"])

GRIDS = {
    "MA_Trend": (eval_ma, list(itertools.product(
        [10,20,30,40,50,60,70,80,90,100],[40,60,80,100,120,140,160,180,200],
        [5,7,9,11,13,15],[2,3,4,5],[0.40,0.45,0.50,0.55,0.60,0.65,0.70]))),
    "MACD_Momentum": (eval_macd, list(itertools.product([8,10,12,14,16,18],[21,26,30,35,40],[5,7,9,11]))),
    "SMC_OrderBlock": (eval_smc, list(itertools.product([15,30,45,60,80,100],[50,100,150,200,300],[50,60,70,80,100]))),
    "ADX_Trend": (eval_adx, list(itertools.product([7,10,14,18,21,28],[15,20,22.5,25,27.5,30,35]))),
    "Asian_Breakout": (eval_asian, list(itertools.product([0,1,2],[7,8,9],[3,4,5],[0.4,0.5,0.6,0.7],[30,50,80,120,200]))),
    "Fractal_Breakout": (eval_fractal, list(itertools.product([10,20,30,50,80],[10,20,40,60,100]))),
}


def main():
    d = D()
    combined = []
    for sname, (fn, combos) in GRIDS.items():
        print(f"\n=== {sname}: {len(combos)} entry combos ===")
        t0 = time.time()
        results = Parallel(n_jobs=-2, verbose=2)(delayed(fn)(c, d) for c in combos)
        rows = [r for sub in results if sub for r in sub]
        df = pd.DataFrame(rows)
        # user request: filter to >=200 trades over 6 years (robust frequency)
        df = df[df["trades"] >= 200].sort_values("profit_pips", ascending=False)
        top200 = df.head(200)
        top200.to_csv(ROOT / "data" / f"pips_top200_{sname}.csv", index=False)
        combined.append(top200)
        print(f"  {len(df)} valid configs in {time.time()-t0:.0f}s; top pip = {df['profit_pips'].iloc[0] if len(df) else 0}")
        print(f"  saved pips_top200_{sname}.csv")
        print(df.head(5)[["profit_pips","points_per_trade","trades","pf","max_dd_pct"]].to_string(index=False))

    allc = pd.concat(combined, ignore_index=True)
    allc.to_csv(ROOT / "data" / "pips_all_per_strategy.csv", index=False)
    print(f"\nSaved pips_all_per_strategy.csv ({len(allc)} rows = up to 200 x 6 strategies)")


if __name__ == "__main__":
    main()
