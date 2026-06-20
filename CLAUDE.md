# QuantumKing — Project Guide for Claude

This file is durable project memory. Read it at the start of every session before touching code.

---

## 1. What this project is

`quantumking` is a multi-strategy MQL5 Expert Advisor that trades **XAUUSD (gold) on the M15 timeframe** in MetaTrader 5. It has a modular architecture: one orchestrator plus pluggable strategy classes, a risk manager, and a position manager.

The author/owner is the user (Lai Si Xiang). The EA is tested in the **MT5 Strategy Tester using real-tick modeling**.

---

## 2. Goal

- **Primary**: keep the EA profitable and robust on XAUUSD M15.
- **MA_Trend is finished and LOCKED.** Owner's MT5 real-tick baseline: **PF 1.82, DD 4.68% balance / 5.74% equity, +$1614, 476 trades over ~6 years**. Do not re-tune it. Touching it requires the user's explicit approval **and** a stated reason.
- **SMC_OrderBlock champion is locked.** Owner's MT5 real-tick baseline: **PF 3.14, DD 15.10% balance, +$954, 245 trades over ~6 years**. Other strategies still need optimization. Per-strategy target: **~1.8 PF, ~400 trades, MaxDD ≤ 20%** (20% DD is the hard ceiling).
- **Headline deliverable** = the per-strategy one-by-one workflow in §10 (optimize one strategy at a time → top-20 shortlist → user verifies in MT5 → picks → next strategy). Always report **profit in PIPS** alongside PF. Use the cached data in `python/data/`.
- Any system-level change must NOT degrade MA_Trend's standalone behavior.

> Note: a whole-portfolio search at $400 (all 5 strategies stacked) was run and **0 of 972 combinations kept DD ≤ 20%** (all 31–50%). Stacking weak strategies onto MA at a tiny account compounds drawdown. Hence the one-by-one approach in §10.

---

## 3. Current state (as of 2026-06-20)

- `Runtime_Preset` selector now controls which strategies are loaded.
- Default = `QK_PRESET_MA_ONLY`.
- Locked baselines: `MA_Trend` (**PF 1.82**, DD 4.68% balance / 5.74% equity, +$1614, 476 trades) and `SMC_OrderBlock` (**PF 3.14**, DD 15.10% balance, +$954, 245 trades).
- `QK_PRESET_FTMO_CHALLENGE` forces MA + SMC, commercial time filters, commercial risk guards, London/NY sessions, and no-grid mode internally while keeping all inputs visible.
- Account assumption remains standard USD, 400-pt max spread, 2% risk, default 20% max floating drawdown emergency stop.

---

## 4. HARD RULES (do not violate without explicit permission)

1. **MA_Trend's specification is LOCKED.** Do NOT modify `CStrategy_MA_Trend.mqh`, its input parameters in `quantumking.mq5`, or any shared logic MA_Trend depends on — **including the ATR(7)/ATR(50)×1.2 regime gate in `CStrategyManager.mqh`**. Changing it requires the user's **explicit approval AND a stated reason**. Rule of thumb: if a change would alter MA_Trend's own entries, exits, or sizing when run standalone, it is off-limits. If a parameter/strategy is NOT related to MA_Trend, you may change it freely to improve the system.
2. **Preserve original code byte-for-byte.** When restoring or referencing the user's code, copy the actual file content exactly — including all Chinese comments, version strings, and formatting. Do not "clean up," reformat, or paraphrase.
3. **MT5 Strategy Tester uses Inputs-tab values (saved in `.set`), NOT recompiled `.ex5` source defaults.** Changing source-code default values does NOT change a backtest unless the user updates the Inputs tab or loads a matching `.set` file and presses F7 to recompile. Always account for this.
4. **My file writes may not reach the user's real MT5 files.** This sandbox can be isolated from the Windows filesystem MT5/MetaEditor reads. After editing, if results don't change, suspect the edit didn't land — give the user verbatim text to paste, or ask them to confirm.
5. **Backtest results depend on the exact historical data range.** Same code + same params + different bar count = different PF. The user's PF 1.77 run had **149,831 bars**; recent runs had **147,983 bars**. Reproducing a result requires matching the data range, not just the params.
6. **Don't touch the MA_Trend spec to "improve" PF.** System-level work only, unless told otherwise.

---

## 5. Architecture (file map)

| File | Role |
|---|---|
| `quantumking.mq5` (v1.50) | Main EA. Instantiates managers, registers strategies by `Runtime_Preset`, kill-switch button, OnTick loop. Holds commercial preset, time-filter, risk-guard, MA, SMC, and ADX inputs. |
| `CStrategyManager.mqh` (v1.30) | Orchestrator. Market-regime detection, global position cap (6), 23:00–00:00 danger-zone pause, intelligent per-magic grid lock, routes signals to strategies. |
| `CRiskManager.mqh` (v1.10) | Spread filter, **adaptive lot sizing** (equity-based ceiling), 20% drawdown emergency close. |
| `CPositionManager.mqh` (v1.20) | Order execution, **non-Martingale averaging grid** (1000-pt spacing, 150-pt breakeven escape, max 10 layers), trailing stop. |
| `CStrategy.mqh` | Base class for all strategies. |
| `CStrategy_MA_Trend.mqh` (v3.30) | Locked MA strategy. Loaded by presets. See §6. |
| `CStrategy_ADX_Trend.mqh` (v1.10) | Tunable ADX strategy with optional H1/H4 EMA filters. Disabled unless selected by preset/custom mode. |
| `CStrategy_*.mqh` (others) | Other strategy implementations; loaded only when registered by preset/custom code. |

### Key mechanisms
- **Regime gate**: `ATR(7) > ATR(50) × 1.2` ⇒ `HIGH_VOL_TREND`; else `LOW_VOL_RANGE`. Strategies named "顺势" (trend) trade only in trend regime; "回归" (reversion) only in low-vol.
- **Danger zone**: hour == 23 or hour == 0 ⇒ no new entries (gold liquidity/spread is bad around midnight).
- **Adaptive lot ceiling**: `dynamic_max_lot = floor(equity / 1000) × 0.01`, floored to broker min, capped at 1.0 lot. With a $400 account this pins lot to 0.01 (pure signal PF). Larger equity grows lot and re-weights trades — this is the main reason PF differs between account sizes.
- **Grid strategies** (magic 10001/10006/10007 only): get same-direction interception. MA_Trend (10002) is NOT a grid strategy.

---

## 6. MA_Trend strategy (LOCKED — reference only)

- **Trend filter**: H4 EMA(fast) vs H4 EMA(slow). Bullish if fast > slow.
- **Momentum trigger**: M15 Stochastic ("KDJ") crossover near OB/OS bands.
- **Entry**: price must touch a Fibonacci retracement zone (Fibo_Top 0.5 → Fibo_Bottom 0.677, ± Zone_Buffer) of the recent 50/100-bar swing.
- **SL**: distance to swing low/high + SL_Buffer, capped at Max_SL. **TP**: fixed 10000 pts (effectively trail-managed).
- **Exit**: trailing stop with activation = distance = `Trail_Start` (1400), step `Trail_Step` (100).
- **Active input values in `quantumking.mq5` (re-tuned & re-locked 2026-06-01)**:
  - Fast_EMA **30** / Slow_EMA **50** (was 20/70)
  - KDJ 7(2,2) / OB 70 / OS 40 (unchanged)
  - Fibo_Top **0.525** / Fibo_Bottom **0.675** (was 0.5/0.677)
  - Zone_Buffer **80** (was 150 — tighter entry zone)
  - SL_Buf 300 / Max_SL 800 (unchanged)
  - Trail_Start 1400 / Trail_Step **140** (was 100)
- **New MA baseline (2026-06-01):** **PF 1.82, DD 4.68% (balance) / 5.74% (equity), $1614 profit, 476 trades over 6 years** — verified by user in MT5.
- This **REPLACES** the previous PF 1.6 baseline. The lock rule (§4.1) now refers to THESE values.

---

## 7. Python research (the source for the top-20 deliverable)

The `python/` folder is an independent research pipeline (pandas/numpy/optuna backtests, audits v1–v6, ~150k backtests) exploring multi-strategy portfolios and parameter grids. Cached result data lives in `python/data/`.

**The user wants me to USE this research** to pick the final **top 20 system combinations** (max PF, MaxDD ≤ 20%), reported **in pips**. The other strategies (everything except locked MA_Trend) are fair game to optimize here. Python results will differ from MT5 real-tick numbers — be honest about that gap and treat the top-20 as candidates to then validate in the user's MT5.

---

## 8. Working preferences

- Be honest about compute/feasibility tradeoffs and about what was actually tested vs. claimed.
- When a result can't be reproduced, investigate the data/settings difference rather than assuming the code changed.
- Don't add features, refactors, or abstractions beyond what's asked.

---

## 9. User decisions (answered 2026-05-30)

- **Goal metric**: MA_Trend is locked (approval + reason required to touch). For all other strategies, optimize for **max PF with MaxDD ≤ 20%** (20% is the hard ceiling). Deliverable = **top 20 system combinations** with max PF, ≤20% DD, reported **in pips**, using the `python/data/` research.
- **Strategy scope**: use the Python research picks (move toward a multi-strategy portfolio), MA_Trend stays in as the locked anchor.
- **Fair game to change**: anything NOT related to MA_Trend. Off-limits: MA_Trend's spec and any shared logic it depends on (e.g. the ATR regime gate). See §4 rule 1.
- **Account size**: keep **$400** (pins lot to 0.01). Always also report **profit in pips**.

### Still open (please fill in)

1. **Broker & data range** — Which broker/server, and what From→To dates are the canonical backtest window (the one that gives 149,831 bars)?
2. **Compile/deploy workflow** — Do you always recompile in MetaEditor (F7) and set inputs via the Inputs tab? Should I produce `.set` files, or only give you values to type in?

---

## 10. Per-strategy optimization workflow (one-by-one) — ACTIVE

The agreed working loop (set 2026-05-30). Optimize strategies **one at a time**, not all stacked:

1. **MA_Trend** — DONE / LOCKED. Baseline PF 1.82, DD 4.68% balance / 5.74% equity, +$1614, 476 trades.
2. For the **next strategy**, produce a **top-20 shortlist** of parameter variants aiming for **~1.8 PF, ~400 trades, MaxDD ≤ 20%, max performance** (my judgment), with **profit in pips** shown.
3. **Show the user the top-20.** The user backtests them one-by-one in their own MT5 and gives their picks.
4. Once the user picks, **proceed to the next strategy.** Repeat.
5. For each strategy I also **recommend keep (add) or drop (delete)** based on the research data in `python/data/`.

### Calibration note (important)
- My Python **frictionless** solo numbers are only a ranking guide. The user's locked MT5 MA_Trend baseline is now **PF 1.82** after the 2026-06-01 retune; the user verifies absolute PF/DD in MT5.
- My **cost-heavy $400** portfolio model **understates** badly (MA → 1.14 PF / 36% DD). Do NOT present those numbers as expectations. The user's broker spread is light.
- Source files: `python/data/pips_top200_<STRATEGY>.csv` (solo, ranked by pips, ≥200 trades), `pips_all_per_strategy.csv`, `layer1_top50_full.csv`, `layer1b_top50_full.csv`.

### Strategy ranking from research (best achievable solo PF, ≥200 trades)
| Strategy | Best PF | #cfgs ≥1.7 PF | trades | Verdict |
|---|---:|---:|---:|---|
| **SMC_OrderBlock** | **1.842** | 35 | 229–526 | **LOCKED champion; do not retune unless asked** |
| ADX_Trend | 1.748 | 1 | ~300 | **Optimize next** |
| MACD_Momentum | 1.684 | 0 | ~200 | Optimize (moderate) |
| VWAP_Reversion_noGrid | needs check | — | ~209 | Validate (PF=99 = artifact) |
| Pivot_Divergence_noGrid | 1.473 | 0 | ~254 | Marginal — likely drop |
| Asian_Breakout | 1.344 | 0 | ~257 | **Drop (weak)** |
| Fractal_Breakout | 1.249 | 0 | ~342 | **Drop (weak)** |
| Bands_Extreme_noGrid | artifact | — | 48 | **Drop (too few trades)** |

Current strategy order: **ADX → MACD → (validate VWAP)**. SMC is locked champion. Drop Asian, Fractal, Bands, (likely) Pivot.

---

## 11. SMC tuning log — comprehensive (as of 2026-05-31)

**Goal:** SMC at $400 with **DD ≤ 20%** AND **trades/year ≥ 300** (= ≥1800 trades over 6 years).
**Reality:** 300/yr structurally unreachable for SMC alone (90% loss rate / lottery payoff structure). Plan = stack via portfolio with ADX/MA/MACD.

### 11.1 SMC class evolution (`CStrategy_SMC_OrderBlock.mqh`)
- **v1.00 (original):** hardcoded — no inputs. SL = OB low − 15. Trail 1000/1000/500.
- **v1.10:** made tunable (SL buffer, Fib tol, scan window, SL mult, H4 EMA filter, trail).
- **v1.11:** bug fix — CalculateSignal mutates state; manager calls it twice per tick → second call returned 0. Fixed by caching pending signal in `m_pending_signal`.
- **v1.12:** added `SMC_Max_SL_Pts` (mirrors MA_Trend's Max_SL) — caps worst-case single-trade losses.
- **v1.13:** added **KDJ + ADX** dual filters, plus **OTE bounds** as inputs (`OTE_Level1`/`OTE_Level2`) and **FVG requirement** as toggle (`Require_FVG`).
- **v1.14:** added **H4 BOS** direction filter (textbook SMC's HTF rule). Uses structural breaks via H4 fractals, distinct from H4 EMA filter.
- **v1.15:** Kelly Path B cherry-picks — **session filter** (London/NY hours), **fixed R:R exit** option (replaces trail), **break-even** option. Also added `ManageBreakEven` helper to `CPositionManager` (MA_Trend untouched). All SMC input comments translated to English for readability.

### 11.2 MT5 optimization phases done (user's tester, real ticks, $400, 6 years 2020-05-09 → 2026-05-09, 141,572 M15 bars)

#### Phase 1 — initial tuning (Slow Complete, 80 combos, H4 filter ON)
Best DD 49.58%, PF 1.22 — failed 20% gate by a wide margin.

#### Phase 2 — broader sweep (Fast Genetic, 200 combos, trail + H4 filter)
**Surprise finding: H4 filter OFF beats ON.** Best: DD 20.34%, PF 1.32 (trail 1000/1000, SL_Mult=0.5, SL_Buf=105, Fib_Tol=200).

#### Phase 1v2 — re-ran Phase 1 grid with H4 OFF + Phase 2 winners locked
DD floor 20.34% (Pass 8). PF up to 1.39 (Pass 7) but DD 22%. Still couldn't break under 20%.

#### Phase 3 — Max_SL sweep (120 combos Slow Complete) — BREAKTHROUGH
- **Pass 0 winner**: SL_Buf=75, Fib_Tol=150, **Max_SL=400**, SL_Mult=0.5, H4 off, Trail 1000/1000/500 → **PF 1.41, DD 19.46%, 511 trades, +$324** over 6 years.
- Max_SL=400 dominates; values ≥800 are effectively no cap (rarely triggered).
- Confirms tail-risk cap is the structural fix to PF/DD tradeoff.

#### Phase 4-5 — relax entry + sweep all 4 filters (192 combos Fast Genetic)
Relaxed OTE 0.382-0.886, FVG OFF, Fib_Tol 400 → baseline 1,692 trades (286/yr) before filters.
**Filter sweep winner pattern: KDJ filter ON (OB=70) + ADX filter ON (Min=30), H4 EMA OFF, H4 BOS OFF.**
- Best deployable: Pass 90 → 403 trades, PF 1.32, DD 19.95% (just under limit).
- Filters can't restore 300/yr while keeping DD ≤ 20% — structural ceiling at ~400 trades / 67/yr.

#### Phase 6 — Kelly Path B single-shot tests (3-minute backtests, six tests A→F)

| Test | Config (delta from Pass 90) | Trades | PF | DD% | Profit | Notes |
|---|---|--:|--:|--:|--:|---|
| **A** | Trail only + session filter ON | 291 | **1.70** | 16.15% | **$322.94** | ⭐ Standalone winner |
| B | Fixed R:R 1:5, no BE, session ON | 300 | 1.31 | 9.60% | $141.04 | Half profit, half DD |
| C | Fixed R:R + BE @ 500pts | 300 | 1.30 | 9.94% | $118.51 | BE too tight, kills mid-winners |
| **D** | Fixed R:R + BE @ 1000pts | 300 | **1.32** | **9.60%** | **$144.04** | ⭐ Portfolio winner |
| E | Fixed R:R + BE @ 1500pts | 300 | 1.31 | 9.60% | $141.04 | BE rarely triggers (≈ B) |
| F | Fixed R:R + BE @ 2000pts | 300 | 1.31 | 9.60% | $141.04 | BE = at TP target (no effect) |

**Biggest Kelly win:** **session filter (London 09-12 server + NY 14-17 server)** — Pass 90 → Test A boosted PF 1.32 → **1.70**, profit $217 → $322 (+49%), DD 19.95% → 16.15% (-19%), while only cutting trades 403 → 291 (-28%).
**Kelly's institutional-flow theory empirically validated on user's MT5.** Off-session hours produce noise; on-session = high-quality trades.

**BE conclusion:** BE@1000 is marginally best ($144 vs $141), but the improvement is tiny. BE doesn't materially help on top of Fixed R:R 1:5.

#### Phase 8 — R:R ratio sweep (completed; see §11.8)
This sweep led into the v1.16 SMC champion path. Final locked result is recorded in §11.9.

### 11.3 Key calibration learnings (Python ↔ MT5)
- **MA_Trend**: Python frictionless solo remains useful for ranking, but the current locked user MT5 baseline is **PF 1.82** after the 2026-06-01 retune.
- **SMC**: Python solo was conservative during early tuning; the current locked MT5 v1.16 champion is **PF 3.14 / 15.10% balance DD**.
- Do not rely on old Python→MT5 multiplier rules for deployment. Use Python for shortlisting and the user's MT5 real-tick tester for final PF/DD.
- **H4 EMA filter direction surprise**: Python research said H4 EMA filter was SMC's biggest PF driver. MT5 shows the opposite — **OFF beats ON**. Real-cost arithmetic favours higher trade frequency.
- **Session filter empirical validation**: Kelly's textbook "London + NY only" rule is the single biggest PF/DD lift discovered in MT5 (PF +29%, DD -19%, profit +49% just by adding it).

### 11.4 Final SMC config candidates (post-Phase 6)

**Two genuinely good configs identified — choice depends on deployment goal:**

| Config | PF | DD% | Profit | Best for |
|---|--:|--:|--:|---|
| **Test A (Trail)** | 1.70 | 16.15% | $322 (+81%, ~10.4% CAGR) | **Standalone deployment** (max return) |
| **Test D (Fixed R:R + BE@1000)** | 1.32 | 9.60% | $144 (+36%, ~5.2% CAGR) | **Portfolio building** (10% DD headroom to stack ADX+MA) |

**Recommendation per user's stated portfolio goal:** lock **Test D** as SMC's portfolio-anchor config. Reasoning: SMC+ADX correlation ≈ moderate → Test A (16% DD) only leaves 4% headroom under 20% limit; Test D (10% DD) leaves 10% to safely stack 2 more strategies.

### 11.5 Pair survey (Python at $400) — calibrated projection to MT5

SMC (Pass 0 config) paired with each candidate partner:

| Pair | Python PF | Python DD% | Projected MT5 PF / DD |
|---|--:|--:|--:|
| **SMC + ADX_Trend** ⭐ | 1.391 | 32.63 | ~1.75 / ~20% |
| SMC + MACD_Momentum | 1.315 | 47.35 | ~1.66 / ~29% |
| SMC + MA_Trend | 1.111 | 55.05 | ~1.40 / ~34% (both H4-trend → losing days overlap) |
| SMC alone (baseline) | 1.035 | 31.29 | (MT5 actual: 1.41 / 19.46%) |
| SMC + Pivot_noGrid | 0.744 | 96.40 | catastrophic (reversion conflicts with trend) |

**Why ADX wins as SMC's partner:** ADX measures trend *strength* (not direction). Its entry conditions are structurally different from SMC's BMS+OTE → losing days don't coincide → diversification works.

### 11.6 Roadmap

1. **SMC_OrderBlock v1.16 champion is locked** — PF 3.14, DD 15.10% balance, +$954, 245 trades.
2. **ADX_Trend tunable v1.10 is implemented.** Run Phase 1 optimization on ADX alone.
3. **SMC + ADX pair test in MT5** — verify projected ~PF 1.75 / DD 20%.
4. If pair confirmed → consider adding 3rd strategy (MACD or VWAP_noGrid) to reach 300/yr.
5. Final portfolio config = locked & shippable system.

### 11.7 Open questions / decisions still pending

- Server time confirmation for session windows (assumed GMT+2 winter / 9-12 + 14-17)
- Whether to also implement Kelly Path A (full multi-TF state machine) if v1.16 plateaus

### 11.8 Phase 8 + Phase 9 — R:R sweep + Trail sweep (2026-06-01)

#### Phase 8 — R:R ratio sweep (Test D baseline, sweep R:R 2-9)
Found increasing PF with higher R:R: at R:R 9 → PF 1.68, DD 10.73%, $310. Suggests TP cap was too tight at 1:5.

#### Phase 8b — extended R:R sweep (single backtests at R:R 10, 18, 25, 50)
- R:R 1:10: PF 1.89, DD 16.66%, $391
- R:R 1:18: PF 2.49, DD 23.43% ❌
- R:R 1:25: PF 2.92, DD 22.84% ❌
- **R:R 1:50: PF 3.15, DD 16.09%, $823** — temporary champion, but equity chart showed massive ghost-profit leak

#### v1.16 — added Trail + R:R hybrid toggle to capture ghost profits
Implemented `SMC_Use_Trail_With_RR`. User decided to test pure trail mode instead (Fixed R:R off).

#### Phase 9 — Pure trail mode sweep (180 combos, Fast Genetic, sorted by DD ascending)

**BREAKTHROUGH RESULT — Pure trail mode with effectively-off trail wins everything:**

| Pass | Trail params | Trades | PF | DD% | Profit |
|---|---|--:|--:|--:|--:|
| **12-47 (band)** | various, activation 5500-8500 | **245** | **3.14** | **15.10%** | **$954.39** ⭐ |
| 20-23 | activation 5500-8500, dist 6500 | 241 | 3.05 | 16.20% | $906 |
| 7-8 | activation 5500-8500, dist 6500, step 1500 | 240 | 3.02-3.05 | 16.23-16.33% | $888-$901 |

**Discovery:** at high trail_activation (5500+), the trail effectively never activates. The "best" trail configs are actually configurations where trail is OFF. The strategy runs on pure SL (400pts) + default TP (10000pts) + KDJ/ADX/session quality filters.

### 11.9 FINAL SMC CHAMPION CONFIG (2026-06-01)

After 9 optimization phases and 6 single-shot Kelly tests, the deployable SMC config is:

| Input | Value | Rationale |
|---|---|---|
| SMC_SL_Buffer_Pts | 105 | Pass 0 winner |
| SMC_Fib_Tol_Pts | 400 | Phase 5 relaxed |
| SMC_SL_Mult | 0.5 | Phase 5 |
| SMC_Max_SL_Pts | **400** | Phase 3 structural cap |
| SMC_OTE_Level1/2 | 0.382 / 0.886 | Phase 5 relaxed |
| SMC_Require_FVG | false | Relaxed |
| SMC_Use_H4_Filter | false | H4 EMA hurts in MT5 |
| SMC_Use_KDJ_Filter | **true** (OB=70) | Phase 5 winner |
| SMC_Use_ADX_Filter | **true** (Min=30) | Phase 5 winner |
| SMC_Use_H4_BOS_Filter | false | Tested, doesn't help |
| SMC_Use_Session_Filter | **true** (London 9-12, NY 14-17) | **Kelly's biggest empirical win** |
| SMC_Use_Fixed_RR | **false** | TP=10000 default beats R:R 1:50 |
| SMC_Trail_Start/Dist/Step | **50000 / 50000 / 1000** | Mathematically guarantees trail never fires (max possible profit ~10000pts) |

**Final stats over 6 years (2020-05-09 → 2026-05-09):**
- **PF 3.14**
- **DD 15.10%** (balance) — 5% headroom under 20% limit
- **Profit: $954.39** = +238.6% return = **~22.7% CAGR**
- 245 trades = 41/yr (below 300/yr target — portfolio needed to reach 300/yr)
- Sharpe ~7.7
- This config BEATS R:R 1:50 ($823) AND Test A trail ($322) in both PF and DD.

### 11.10a Premium/Discount filter — reserved future enhancement (2026-06-01)

User asked whether the locked SMC has textbook premium/discount discipline. Honest answer recorded for future tuning:

**Current state:**
- SMC has OTE Fibonacci zone but **NO explicit premium/discount filter** (no explicit 50%-line check).
- The two OTE levels use **different anchors** in the code (line 429-432 for bull, 468-471 for bear):
  - `fib_a = wave_low + wave * m_ote_level1` (measured from swing low)
  - `fib_b = wave_high - wave * m_ote_level2` (measured from swing high)
- With **default OTE (0.705/0.786)**: zone spans both premium AND discount (NOT textbook).
- With **user's tuned OTE (0.382/0.886)**: zone is entirely in discount for buys / premium for sells (textbook-compliant ✓ by tuning luck).

**Implication:** The current locked SMC config is *empirically* in correct discount/premium because of the relaxed OTE values found by the optimizer. The logic is **not robust** — if OTE is retuned back toward defaults, it would violate textbook P/D discipline.

**Future enhancement (when user requests):** Add explicit premium/discount filter as a separate constraint:
- For BUY: require entry price < wave_low + 0.5 × wave (must be in discount)
- For SELL: require entry price > wave_low + 0.5 × wave (must be in premium)
- Make it a toggleable input `SMC_Use_PD_Filter` (default OFF preserves current behavior).
- Adds belt-and-suspenders discipline against accidental premium-buys / discount-sells if OTE is later retuned.

**Skip for now** — current SMC config is already in correct zones empirically. Revisit when user opts to add this layer.

### 11.10 Lessons learned

1. **Simple > Complex.** The winning config has the FEWEST active mechanics (no Fixed R:R, no BE, no active trail, no H4 BOS). Quality filters + tight SL + reasonable TP wins.
2. **TP at 10000pts (100 pips) is optimal for gold** at $400 — catches frequent trend-day winners.
3. **Wider TP (R:R 1:50 → 20000pts) hurts** because most gold moves don't reach 200 pips.
4. **Tight trail caps winners** — Test A's 1000/1000/500 trail produced only $322 because winners got trailed out at ~$10-15 each.
5. **Session filter is the single biggest PF lift** — Kelly's textbook validated empirically.
6. **Filters (KDJ+ADX) at OB=70 / Min=30 add ~10% PF improvement** on top of base SMC.
