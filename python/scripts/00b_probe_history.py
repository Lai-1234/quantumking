"""Probe how much XAUUSD history this broker exposes."""
from __future__ import annotations

from datetime import datetime, timezone

import MetaTrader5 as mt5

if not mt5.initialize():
    print("init failed:", mt5.last_error())
    raise SystemExit(1)

sym = "XAUUSD"
mt5.symbol_select(sym, True)

# Use copy_rates_from_pos with a large count to see how far the broker goes.
for tf, name in [(mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_H4, "H4")]:
    rates = mt5.copy_rates_from_pos(sym, tf, 0, 200_000)
    if rates is None or len(rates) == 0:
        print(f"{name}: no data ({mt5.last_error()})")
        continue
    first = datetime.fromtimestamp(rates[0]["time"], tz=timezone.utc)
    last = datetime.fromtimestamp(rates[-1]["time"], tz=timezone.utc)
    print(f"{name}: {len(rates):,} bars  from {first}  to {last}")

mt5.shutdown()
