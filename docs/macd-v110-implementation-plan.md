# MACD_Momentum v1.10 Implementation Plan

## Goal

Harden `CStrategy_MACD_Momentum.mqh` before MT5 optimization. MACD should act as a trend-confirmation strategy, not a naked crossover system.

## Project Rules

- Do not touch `CStrategy_MA_Trend.mqh`.
- Do not change MA_Trend inputs in `quantumking.mq5`.
- Do not touch the ATR(7)/ATR(50) x 1.2 regime gate in `CStrategyManager.mqh`.
- Do not change locked SMC or ADX strategy logic.
- Keep BIAS_Reversion experimental and disabled by default.
- Compile after implementation before any MT5 optimization.

## Phase 0 - Baseline Sync

- [x] Start from the real MT5 project folder state, not the older GitHub `main`.
- [x] Preserve v1.51 source state, BIAS_Reversion wiring, ADX locked values, and updated `CLAUDE.md`.

## Phase 1 - MACD Strategy Refactor

- [x] Bump `CStrategy_MACD_Momentum.mqh` from v1.00 to v1.10.
- [x] Add tunable MACD periods:
  - `MACD_Fast_EMA`
  - `MACD_Slow_EMA`
  - `MACD_Signal_SMA`
- [x] Add tunable structural risk controls:
  - `MACD_SL_Buffer_Pts`
  - `MACD_Max_SL_Pts`
- [x] Keep H1 + H4 EMA 50/200 trend filter always ON.
- [x] Add London/NY session filter, always ON:
  - Session 1: 9-12 server time
  - Session 2: 14-17 server time
- [x] Keep closed-candle logic only; never use bar 0 for signals.
- [x] Add Max SL skip logic:
  - If calculated structural SL exceeds `MACD_Max_SL_Pts`, skip the trade.
  - Do not clamp the SL tighter than structure.
- [x] Change trailing stop to effectively OFF:
  - `50000 / 50000 / 1000`

## Phase 2 - EA Wiring

- [x] Add `Custom_Enable_MACD_Momentum` for CUSTOM preset control.
- [x] Add `MACD_Momentum_Weight`.
- [x] Add `QK_PRESET_MACD_ONLY` for clean standalone testing.
- [x] Add MACD input section in `quantumking.mq5`.
- [x] Replace old commented MACD call with a real preset-routed `AddStrategy` block.
- [x] Keep default `Runtime_Preset = QK_PRESET_MA_ONLY`.

## Phase 3 - Documentation

- [x] Update `CLAUDE.md` section 16 with the implemented v1.10 state.
- [x] Record that MACD is not locked yet.
- [x] Record the MT5 testing instructions.

## Phase 4 - Verification

- [x] Compile `quantumking.mq5` in MetaEditor.
- [x] Confirm 0 errors and 0 warnings.
- [x] Confirm generated `quantumking.ex5` timestamp updates.
- [x] Confirm MA_Trend, SMC, ADX, `CRiskManager`, and `CPositionManager` were not modified by the MACD implementation.
- [x] Confirm ATR x 1.2 regime gate remains unchanged.

## Phase 5 - MT5 Optimization After Compile

Use `Runtime_Preset = QK_PRESET_MACD_ONLY`.

Settings:
- Symbol: XAUUSD
- Timeframe: M15
- Initial deposit: 400 USD
- Modelling: Every tick based on real ticks
- Period: 2020-05-09 to 2026-05-09
- Optimization criterion: Custom max / OnTester

Sweep:

| Input | Values |
|---|---|
| `MACD_Fast_EMA` | 6, 8, 10, 12 |
| `MACD_Slow_EMA` | 20, 24, 26, 30, 40 |
| `MACD_Signal_SMA` | 5, 7, 9, 11 |
| `MACD_SL_Buffer_Pts` | 50, 100, 150 |
| `MACD_Max_SL_Pts` | 400, 600, 800, 1000 |

Accept only candidates with:
- Balance DD Maximal <= 20%
- Profit Factor preferably >= 1.6
- At least 100 trades over 6 years
- Profit in pips recorded

## Later, Not Phase 1

- ADX gate for MACD.
- VWAP confluence.
- ATR-based SL/TP.
- News filter.
- Divergence scanner.

These are useful ideas from the research, but adding them now would make optimization noisy.
