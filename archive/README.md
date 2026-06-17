# Archived strategies (Audit v2.00, 2026-05-27)

These 7 strategy files were removed from the active EA based on the
Python audit (see `../python/reports/strategy_audit.md`).

| File | Audited PF | Reason archived |
|---|---:|---|
| CStrategy_Bands_Extreme.mqh | 0.36 | Grid disaster — 99% WR but tail events kill account |
| CStrategy_Pivot_Divergence.mqh | 0.10 | Worst performer; tested 60 grid variants, all lose |
| CStrategy_VWAP_Reversion.mqh | 0.50 | Same grid death-spiral pattern as Pivot |
| CStrategy_Fractal_Breakout.mqh | 0.82 | No edge found after 50 optuna trials |
| CStrategy_Pulse_Momentum.mqh | 1.00 | Break-even on M1, dies in real spread |
| CStrategy_Asian_Breakout.mqh | 1.16 | Marginal — re-add at weight 0.3 if MT5 real-tick validates |
| CStrategy_ADX_Trend.mqh | 2.61 | High PF but only 24 trades/6yr — high variance, validate in MT5 first |

To re-enable any of these:
1. Move the `.mqh` back to the parent directory.
2. Add `#include "CStrategy_<Name>.mqh"` to `quantumking.mq5`.
3. Add a `StrategyMgr.AddStrategy(new CStrategy_<Name>(...))` call in `OnInit()`.

ADX_Trend and Asian_Breakout are the best re-add candidates after MT5
real-tick validation. The grid-based three (Bands, Pivot, VWAP) are
fundamentally incompatible with gold's trend behavior — don't re-add.
