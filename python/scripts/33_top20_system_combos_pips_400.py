"""TOP-20 system combinations at a $400 account, reported in PIPS.

User's spec (2026-05-30):
- MA_Trend is LOCKED to its live spec (Fast20/Slow70/KDJ7(2,2)/OB70/OS40/
  Fibo0.5-0.677/Zone150/SL300/MaxSL800/Trail1400/100). Never varied.
- The ATR regime gate that MA_Trend depends on stays at x1.2. Never varied.
- Only the OTHER strategies (SMC, MACD, ADX, Pivot_noGrid) and the system
  knobs (time-pause, position cap) are searched.
- Account = $400 (adaptive lot pins to ~0.01). Profit reported in PIPS
  (lot-independent edge) AND points; PF reported as pip-PF (also lot-indep).
- Constraint: keep only combinations whose TRUE max drawdown <= 20%.
- Rank survivors by pip-PF, take top 20.

Profit in pips: sum over closed trades of (exit-entry)/POINT*side / 10
(XAUUSD: 1 point = 0.01 price; 1 pip = 10 points).
"""
from __future__ import annotations

import importlib.util
import itertools
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.indicators import atr
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.risk import POINT, TrailParams
from quantumking.strategies import ma_trend

POINTS_PER_PIP = 10.0

# Reuse the layer-3 spec builders for the non-MA strategies.
_spec23 = importlib.util.spec_from_file_location(
    "l3", ROOT / "scripts" / "23b_layer3_parallel.py")
_mod23 = importlib.util.module_from_spec(_spec23)
_spec23.loader.exec_module(_mod23)
_safe_build_spec = _mod23._safe_build_spec

# ---- system knobs that actually bite at $400 ----
TIME_PAUSE = {
    "none": (),
    "23-00": (23, 0),          # the original EA's danger zone
    "22-01": (22, 23, 0, 1),
}
CAPS = [3, 4, 5, 6]
REGIME_MULT = 1.2              # LOCKED (MA_Trend depends on it)
RISK_PCT = 0.02                # original
SPREAD_CAP = 400              # original
MEASURE_KILL = 0.95            # high kill so we measure TRUE max DD, then filter <=20%
INITIAL_EQUITY = 400.0

VARYING = ["SMC_OrderBlock", "MACD_Momentum", "ADX_Trend", "Pivot_Divergence_noGrid"]
WEIGHTS = {"MA_Trend": 1.0, "SMC_OrderBlock": 0.7, "MACD_Momentum": 0.3,
           "ADX_Trend": 0.3, "Pivot_Divergence_noGrid": 0.4}
TOP_VAR = 3  # top-3 variants per varying strategy

# Lazy per-worker cache of the built specs (signal generation is the costly bit).
_CACHE: dict = {}


def _data():
    if "data" not in _CACHE:
        d = ROOT / "data"
        _CACHE["data"] = {
            "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
            "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
            "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
            "D1": pd.read_parquet(d / "XAUUSD_D1.parquet"),
        }
    return _CACHE["data"]


def _ma_locked_spec():
    """MA_Trend with the user's exact LIVE input values."""
    data = _data()
    p = ma_trend.MAParams(
        fast_ema=20, slow_ema=70, kdj_period=7, kdj_d=2, kdj_s=2,
        stoch_ob=70, stoch_os=40, fibo_top=0.5, fibo_bottom=0.677,
        zone_buffer_pts=150, sl_buffer_pts=300, max_sl_pts=800)
    sigs = ma_trend.generate_signals(data["M15"], data["H4"], p)
    return StratSpec(name="MA_Trend", signals=sigs,
                     trail=TrailParams(1400, 1400, 100), kind="trend", weight=1.0)


def _variant_pools():
    """Build top-3 StratSpec variants for each varying strategy."""
    if "pools" in _CACHE:
        return _CACHE["pools"], _CACHE["pool_rows"]
    data = _data()
    d = ROOT / "data"
    l1 = pd.read_csv(d / "layer1_top50_full.csv")
    l1b = pd.read_csv(d / "layer1b_top50_full.csv")
    pools, rows = {}, {}
    for sname in VARYING:
        src = l1b if sname.endswith("_noGrid") else l1
        sub = src[src["strategy"] == sname].sort_values("score", ascending=False).head(TOP_VAR)
        specs, rowdicts = [], []
        for _, r in sub.iterrows():
            rd = r.to_dict()
            try:
                spec = _safe_build_spec(sname, rd, data, WEIGHTS[sname])
            except Exception:
                spec = None
            specs.append(spec)
            rowdicts.append(rd)
        pools[sname] = specs
        rows[sname] = rowdicts
    _CACHE["pools"] = pools
    _CACHE["pool_rows"] = rows
    return pools, rows


def _variant_label(sname: str, rd: dict) -> str:
    """Human-readable one-liner for a chosen variant."""
    g = lambda k: rd.get(k)
    if sname == "SMC_OrderBlock":
        return f"SMC[slbuf={g('sl_buf')},fibtol={g('fib_tol')},scan={g('scan')},mtf={g('mtf')},slx{g('sl_mult')}]"
    if sname == "MACD_Momentum":
        return f"MACD[{g('fast')}/{g('slow')}/{g('sig')},mtf={g('mtf')},slx{g('sl_mult')}]"
    if sname == "ADX_Trend":
        return f"ADX[p={g('period')},thr={g('threshold')},mtf={g('mtf')},slx{g('sl_mult')}]"
    if sname == "Pivot_Divergence_noGrid":
        return f"Pivot[rsi={g('rsi_p')},touch={g('touch')},mtf={g('mtf')},slx{g('sl_mult')}]"
    return sname


def _pips_from_trades(tdf: pd.DataFrame):
    if tdf is None or tdf.empty:
        return 0.0, 0.0, 0.0, 0.0
    pts = (tdf["exit"] - tdf["entry"]) / POINT * tdf["side"]
    total_pts = float(pts.sum())
    pos = float(pts[pts > 0].sum())
    neg = float(-pts[pts < 0].sum())
    pip_pf = (pos / neg) if neg > 0 else (99.0 if pos > 0 else 0.0)
    return total_pts, total_pts / POINTS_PER_PIP, total_pts / len(tdf), pip_pf


def _eval(job):
    time_pause, cap, vidx = job
    data = _data()
    pools, _ = _variant_pools()
    reg = atr(data["M15"], 7) > atr(data["M15"], 50) * REGIME_MULT
    specs = [_ma_locked_spec()]
    for k, sname in enumerate(VARYING):
        sp = pools[sname][vidx[k]]
        if sp is not None and sp.signals is not None:
            specs.append(sp)
    if len(specs) < 2:
        return None
    cfg = PortfolioConfig(initial_equity=INITIAL_EQUITY, max_positions=cap,
                          spread_cap_pts=SPREAD_CAP, danger_hours=TIME_PAUSE[time_pause],
                          drawdown_kill_pct=MEASURE_KILL, spread_pts=17, slippage_pts=5)
    res = run_portfolio(data["M15"], specs, cfg, regime=reg)
    tdf = res.get("trades_df")
    total_pts, pips, ppt, pip_pf = _pips_from_trades(tdf)
    return {
        "time_pause": time_pause, "cap": cap, "regime_mult": REGIME_MULT,
        "variant_idx": str(vidx),
        "n_strats": len(specs), "trades": res["trades"],
        "pip_pf": round(pip_pf, 3), "usd_pf": round(res["pf"], 3),
        "profit_pips": round(pips, 1), "profit_points": round(total_pts, 1),
        "pips_per_trade": round(ppt / POINTS_PER_PIP, 2),
        "max_dd_pct": round(abs(res["max_dd_pct"]) * 100, 2),
        "sharpe": round(res["sharpe"], 2),
        "net_pnl_usd": round(res["net_pnl"], 1),
    }


def main():
    d = ROOT / "data"
    # Build job list: time_pause x cap x variant-combos (3^4 = 81)
    var_combos = list(itertools.product(range(TOP_VAR), repeat=len(VARYING)))
    jobs = [(tp, cap, vc) for tp in TIME_PAUSE for cap in CAPS for vc in var_combos]
    print(f"Total system combinations: {len(jobs)} "
          f"({len(TIME_PAUSE)} time-pause x {len(CAPS)} caps x {len(var_combos)} variant combos)")
    print(f"Account=${INITIAL_EQUITY:.0f} | regime x{REGIME_MULT} (locked) | MA_Trend locked\n")

    rows = Parallel(n_jobs=-2, verbose=5)(delayed(_eval)(j) for j in jobs)
    rows = [r for r in rows if r is not None]
    full = pd.DataFrame(rows)
    full.to_csv(d / "system_combos_400_pips_full.csv", index=False)
    print(f"\nSaved system_combos_400_pips_full.csv ({len(full)} rows)")

    # Resolve readable variant labels.
    _, pool_rows = _variant_pools()
    def labels(vstr):
        vc = eval(vstr)
        return " + ".join(_variant_label(s, pool_rows[s][vc[k]]) for k, s in enumerate(VARYING))
    full["strategies"] = full["variant_idx"].map(labels)

    # Constraint: true max DD <= 20%. Rank survivors by pip-PF.
    ok = full[full["max_dd_pct"] <= 20.0].copy()
    ok = ok.sort_values(["pip_pf", "profit_pips"], ascending=False)
    top20 = ok.head(20)
    cols = ["pip_pf", "usd_pf", "profit_pips", "profit_points", "pips_per_trade",
            "trades", "max_dd_pct", "sharpe", "time_pause", "cap", "strategies"]
    top20[cols].to_csv(d / "TOP20_system_combos_400_pips.csv", index=False)

    print(f"\nSurvivors with MaxDD<=20%: {len(ok)} of {len(full)}")
    print(f"Saved TOP20_system_combos_400_pips.csv\n")
    print("=== TOP 20 SYSTEM COMBINATIONS ($400, pips, MaxDD<=20%) ===")
    with pd.option_context("display.max_colwidth", 60, "display.width", 200):
        print(top20[["pip_pf", "profit_pips", "pips_per_trade", "trades",
                     "max_dd_pct", "sharpe", "time_pause", "cap"]].to_string(index=False))
    if len(ok) == 0:
        print("\n[!] No combination kept MaxDD <= 20% at a $400 account.")
        worst = full.sort_values("max_dd_pct").head(10)
        print("Closest (lowest DD) combos:")
        print(worst[["pip_pf", "profit_pips", "trades", "max_dd_pct", "time_pause", "cap"]].to_string(index=False))


if __name__ == "__main__":
    main()
