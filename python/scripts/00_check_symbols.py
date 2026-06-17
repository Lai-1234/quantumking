"""List broker symbols matching gold patterns and show point/tick info."""
from __future__ import annotations

import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 init failed:", mt5.last_error())
    raise SystemExit(1)

print(f"Account login: {mt5.account_info().login if mt5.account_info() else 'N/A'}")
print(f"Server       : {mt5.terminal_info().company if mt5.terminal_info() else 'N/A'}")
print()

all_symbols = mt5.symbols_get()
print(f"Total symbols on broker: {len(all_symbols)}")
print()

gold_like = [s.name for s in all_symbols
             if "XAU" in s.name.upper() or "GOLD" in s.name.upper()]
print("Gold-like symbols on this broker:")
for n in gold_like:
    info = mt5.symbol_info(n)
    if info:
        print(f"  {n:20s} point={info.point}  digits={info.digits}  "
              f"visible={info.visible}  spread={info.spread}")

print()
print("Pick the one you trade in MT5 and tell me the exact name.")
mt5.shutdown()
