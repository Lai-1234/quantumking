"""Read optuna trial CSVs and print the best params per strategy."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TRIALS = ROOT / "data" / "optuna"

print(f"{'Strategy':30s} {'Best':>6s} {'Trials':>7s}  Params")
print("-" * 110)
for p in sorted(TRIALS.glob("*_trials.csv")):
    name = p.stem.replace("_trials", "")
    df = pd.read_csv(p)
    if df.empty or "value" not in df.columns:
        print(f"{name:30s} {'-':>6s} {'-':>7s}")
        continue
    best_idx = df["value"].astype(float).idxmax()
    best_score = df.loc[best_idx, "value"]
    n = len(df)
    # extract params columns
    param_cols = [c for c in df.columns if c.startswith("params_")]
    params = {c.replace("params_", ""): df.loc[best_idx, c] for c in param_cols}
    print(f"{name:30s} {best_score:>6.3f} {n:>7d}  {params}")
