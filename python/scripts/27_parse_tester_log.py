"""Parse MT5 Strategy Tester log to compute PF / win-rate / DD from deals.

MT5 logs deals as: 'deal #N <buy|sell> <vol> XAUUSD at <price> done'.
We reconstruct per-position PnL by FIFO matching of buy/sell deals.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TLOG = Path(r"C:\Users\laisi\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\Tester\logs\20260528.log")

deal_re = re.compile(r"deal #(\d+)\s+(buy|sell)\s+([\d.]+)\s+XAUUSD\s+at\s+([\d.]+)\s+done")


def main():
    # Read with error-tolerant decoding (log may have null bytes / mixed encoding)
    raw = TLOG.read_bytes().replace(b"\x00", b"")
    text = raw.decode("utf-8", errors="ignore")

    deals = []
    for m in deal_re.finditer(text):
        deals.append({
            "id": int(m.group(1)),
            "side": m.group(2),
            "vol": float(m.group(3)),
            "price": float(m.group(4)),
        })
    # Dedup by id (log may repeat)
    seen = {}
    for d in deals:
        seen[d["id"]] = d
    deals = [seen[k] for k in sorted(seen)]
    print(f"Unique deals: {len(deals)}")
    if not deals:
        print("No deals parsed.")
        return

    # FIFO position reconstruction. XAUUSD: $1 per pt per lot? Use contract=100 oz.
    # PnL per closed trade = (exit - entry) * direction * vol * 100 (oz per lot).
    # Match buy->sell pairs in sequence (each strategy opens then closes).
    CONTRACT = 100.0  # oz per lot
    position = 0.0    # net oz
    avg_entry = 0.0
    realized = []

    for d in deals:
        signed = d["vol"] * (1 if d["side"] == "buy" else -1) * CONTRACT
        if position == 0:
            position = signed
            avg_entry = d["price"]
        elif (position > 0 and signed > 0) or (position < 0 and signed < 0):
            # adding to position
            total = position + signed
            avg_entry = (avg_entry * abs(position) + d["price"] * abs(signed)) / abs(total)
            position = total
        else:
            # reducing/closing
            close_oz = min(abs(signed), abs(position))
            direction = 1 if position > 0 else -1
            pnl = (d["price"] - avg_entry) * direction * close_oz
            realized.append(pnl)
            position += signed
            if (signed > 0) != (position > 0) and position != 0:
                avg_entry = d["price"]
            if position == 0:
                avg_entry = 0.0

    import numpy as np
    pnls = np.array(realized)
    if len(pnls) == 0:
        print("No closed trades reconstructed.")
        return
    wins = pnls[pnls > 0].sum()
    losses = -pnls[pnls < 0].sum()
    pf = wins / losses if losses > 0 else float("inf")
    print(f"Closed trades   : {len(pnls)}")
    print(f"Win rate        : {(pnls > 0).mean()*100:.1f}%")
    print(f"Gross profit    : ${wins:.2f}")
    print(f"Gross loss      : ${losses:.2f}")
    print(f"Net profit      : ${pnls.sum():.2f}")
    print(f"Profit factor   : {pf:.3f}")
    # Equity curve / DD
    eq = 10000 + np.cumsum(pnls)
    run_max = np.maximum.accumulate(eq)
    dd = ((eq - run_max) / run_max).min()
    print(f"Max drawdown    : {dd*100:.2f}%")
    print(f"Final equity    : ${eq[-1]:.2f}")


if __name__ == "__main__":
    main()
