# ADX_Trend Phase 1 Optimization

## Phase 1a — Core ADX params (Slow Complete, ~42 combos, ~2 hours)

Lock: `ADX_SL_Buffer_Pts=150`, `ADX_Max_SL_Pts=800`, trail `1000/1000/500`, H1+H4 filters OFF.

Sweep:

| Input | Values |
|---|---|
| `ADX_Period` | 7, 10, 14, 18, 21, 28 |
| `ADX_Threshold` | 15, 20, 22.5, 25, 27.5, 30, 35 |

Criterion: Custom max (`OnTester`).

## Phase 1b — Risk params (Slow Complete, 25 combos, ~1.5 hours)

Lock Phase 1a winners + trail/H1+H4 unchanged.

Sweep:

| Input | Values |
|---|---|
| `ADX_SL_Buffer_Pts` | 50, 100, 150, 200, 300 |
| `ADX_Max_SL_Pts` | 400, 600, 800, 1200, 0 |

`ADX_Max_SL_Pts=0` means no cap.

## Phase 1c — Trail params (Fast Genetic, ~60 combos, ~1 hour)

Lock Phase 1a + 1b winners.

Sweep:

| Input | Values |
|---|---|
| `ADX_Trail_Start_Pts` | 800, 1200, 1500, 2000, 5000 |
| `ADX_Trail_Dist_Pts` | 500, 1000, 1500, 5000 |
| `ADX_Trail_Step_Pts` | 100, 300, 500 |

Include the high `5000` values to test "trail effectively off" because that won for SMC.

## Phase 1d — MTF filters (Slow Complete, 4 combos, ~15 min)

Lock Phase 1a + 1b + 1c winners.

Sweep:

| Input | Values |
|---|---|
| `ADX_Use_H1_Filter` | false, true |
| `ADX_Use_H4_Filter` | false, true |

## MT5 Strategy Tester Settings

Use these settings for all phases:

| Setting | Value |
|---|---|
| Symbol | XAUUSD |
| Timeframe | M15 |
| Initial deposit | 400 USD |
| Modelling | Every tick based on real ticks |
| Period | 2020-05-09 to 2026-05-09 |
| `Runtime_Preset` | `QK_PRESET_ADX_ONLY` |
| Alternative preset | `QK_PRESET_CUSTOM` with only `Custom_Enable_ADX_Trend=true` |
| Optimization criterion | Custom max (`OnTester` score) |

## Goals

| Metric | Target |
|---|---|
| Profit Factor | >= 1.8 preferred |
| Drawdown | <= 20% hard limit |
| Trades | 250-500 over 6 years; ~40-80/year is acceptable |
| Profit in pips | Report alongside PF/DD/trades; `OnTester()` prints `profit_pips` in the Journal |

Profit in pips convention: XAUUSD `1 pip = 10 points = 0.10 price`.

## OnTester Score

The EA now returns a commercial optimization score through `OnTester()`:

```text
0 if DD > 20%
0 if trades < 100
otherwise score = PF x sqrt(trades / 200) x (1 - DD / 0.20)
```

Use MT5's **Custom max** optimization criterion so passes are ranked by commercial quality, not raw profit alone.

`OnTester()` also prints `profit_pips` using closed tester deal history. This value is for reporting and comparison; the returned Custom max value remains the commercial score.

## Reporting Template

For the best 10-20 passes, record:

| Pass | PF | DD % | Trades | Net Profit | Profit Pips | ADX Period | ADX Threshold | SL Buffer | Max SL | Trail Start | Trail Dist | Trail Step | H1 | H4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|

Reject any pass with DD above 20%, fewer than 100 trades, or obvious one-shot overfitting.
