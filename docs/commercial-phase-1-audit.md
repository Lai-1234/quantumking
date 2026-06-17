# QuantumKing Commercial Phase 1 Audit

Date: 2026-06-18
Branch: `codex/commercial-step-1-audit`

## Purpose

This phase creates a clean commercial baseline before changing EA behavior. It records the current code state, the documented target state, and the safest next branches.

No trading logic is changed in this phase.

## Current Repo State

- GitHub repo: `https://github.com/Lai-1234/quantumking`
- Current branch: `codex/commercial-step-1-audit`
- Main EA file: `quantumking.mq5`
- Main runtime modules:
  - `CStrategyManager.mqh`
  - `CRiskManager.mqh`
  - `CPositionManager.mqh`
  - `CStrategy_MA_Trend.mqh`
  - `CStrategy_SMC_OrderBlock.mqh`
  - `CStrategy_ADX_Trend.mqh`

## Key Finding 1: SMC Champion Config Is Documented But Not Synced In Source Defaults

`CLAUDE.md` and `QuantumKing_COMPLETE_EDITION.docx` describe a locked SMC champion configuration:

| Input | Documented champion value |
|---|---:|
| `SMC_SL_Buffer_Pts` | `105` |
| `SMC_Fib_Tol_Pts` | `400` |
| `SMC_SL_Mult` | `0.5` |
| `SMC_Max_SL_Pts` | `400` |
| `SMC_OTE_Level1` | `0.382` |
| `SMC_OTE_Level2` | `0.886` |
| `SMC_Require_FVG` | `false` |
| `SMC_Use_H4_Filter` | `false` |
| `SMC_Use_KDJ_Filter` | `true` |
| `SMC_KDJ_OB` | `70` |
| `SMC_Use_ADX_Filter` | `true` |
| `SMC_ADX_Min` | `30.0` |
| `SMC_Use_H4_BOS_Filter` | `false` |
| `SMC_Use_Session_Filter` | `true` |
| `SMC_Session1_Start/End` | `9 / 12` |
| `SMC_Session2_Start/End` | `14 / 17` |
| `SMC_Use_Fixed_RR` | `false` |
| `SMC_Trail_Start/Dist/Step` | `50000 / 50000 / 1000` |

But `quantumking.mq5` currently has older source defaults:

| Input | Current source value | Issue |
|---|---:|---|
| `SMC_SL_Buffer_Pts` | `60` | Should be `105` for champion default |
| `SMC_Fib_Tol_Pts` | `300` | Should be `400` |
| `SMC_Use_H4_Filter` | `true` | Champion uses `false` |
| `SMC_Trail_Start` | `2000` | Champion uses `50000` |
| `SMC_Trail_Dist` | `1500` | Champion uses `50000` |
| `SMC_Max_SL_Pts` | `5000` | Champion uses `400` |
| `SMC_OTE_Level1` | `0.705` | Champion uses `0.382` |
| `SMC_OTE_Level2` | `0.786` | Champion uses `0.886` |
| `SMC_Require_FVG` | `true` | Champion uses `false` |
| `SMC_Use_KDJ_Filter` | `false` | Champion uses `true` |
| `SMC_Use_ADX_Filter` | `false` | Champion uses `true` |
| `SMC_ADX_Min` | `20.0` | Champion uses `30.0` |
| `SMC_Use_Session_Filter` | `false` | Champion uses `true` |

Commercial implication: before adding new features, source defaults should match the documented champion, otherwise MT5 users can compile/load the EA with the wrong behavior.

## Key Finding 2: SMC Is Present But Currently Disabled In Runtime

`quantumking.mq5` contains a full `CStrategy_SMC_OrderBlock` registration block, but it is inside a block comment. The current runtime setup is effectively MA-led.

Commercial implication: the strongest documented strategy is not currently active by default. That is acceptable for testing, but a commercial build needs explicit presets:

- MA only
- SMC champion only
- MA + SMC
- commercial balanced portfolio

## Key Finding 3: ADX Trend Is Too Hardcoded For Commercial Optimization

`CStrategy_ADX_Trend.mqh` exposes only constructor parameters for:

- ADX period
- ADX threshold

But important live/optimization controls are hardcoded:

- SL buffer: `150`
- TP: `10000`
- trailing: `1000 / 1000 / 500`
- no H1/H4 filter
- no session filter
- no max SL cap
- no explicit day-of-week behavior

Commercial implication: ADX cannot be tested cleanly as a product-grade module until these are inputs.

## Key Finding 4: Existing Safety Layer Is Good But Not Commercial Complete

Current `CRiskManager.mqh` already has:

- spread filter
- adaptive lot ceiling
- emergency floating-drawdown close

Current `CPositionManager.mqh` already has:

- hard SL/TP order execution
- trailing stop manager
- breakeven helper
- emergency close all
- non-martingale grid logic for selected strategies

Missing for commercial/prop-ready packaging:

- daily loss guard
- peak-equity trailing drawdown guard
- persistent pause state after risk breach
- news pause input or schedule hook
- prop mode with max grid layers = 1
- user-visible risk mode presets

## Key Finding 5: Day/Session Filter Is The Highest-Value Low-Risk Addition

The complete edition document repeatedly points to time filtering as a major XAUUSD edge:

- Monday often noisy
- Tuesday to Thursday best for trend continuation
- Friday late session should block new entries
- London and New York windows are the highest-quality periods
- 15:00-16:00 server time is marked as a premium Silver Bullet window

Commercial implication: add this as a global optional filter first, not buried inside one strategy.

## Recommended Phase Order

### Phase 2: Sync SMC Champion Defaults

Branch: `codex/exp-001-smc-champion-sync`

Scope:

- Update only SMC input defaults in `quantumking.mq5`.
- Preserve the SMC block disabled unless explicitly activating a preset.
- Add clear comments marking the champion values.

Why first:

- It aligns source code with project memory.
- It does not alter MA behavior.
- It prevents accidental wrong SMC testing.

### Phase 3: Add Commercial Time Filter Toggles

Branch: `codex/exp-002-commercial-time-filters`

Scope:

- Add global day/session filter inputs.
- Apply only to new entries.
- Do not block existing position management.
- Keep defaults conservative/off where needed for compatibility.

### Phase 4: Make ADX Trend Tunable

Branch: `codex/exp-003-adx-tunable`

Scope:

- Expose ADX period/threshold, SL buffer, max SL, TP, trail values.
- Add optional H1/H4 filter hooks if low-risk.
- Add constructor inputs from `quantumking.mq5`.

### Phase 5: Add Commercial Risk Modes

Branch: `codex/exp-004-commercial-risk-guards`

Scope:

- Daily loss guard.
- Peak-equity drawdown guard.
- prop mode switches.
- optional max grid layer input.

## What The User Needs To Do

Nothing for Phase 1. This is a documentation-only checkpoint.

When Phase 2 is complete, the user only needs to decide whether the commercial default should remain MA-only or switch to SMC champion / balanced preset.
