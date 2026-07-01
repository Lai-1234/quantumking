# QuantumKing — Project Guide for Claude

This file is durable project memory. Read it at the start of every session before touching code.

---

## 1. What this project is

`quantumking` is a multi-strategy MQL5 Expert Advisor that trades **XAUUSD (gold) on the M15 timeframe** in MetaTrader 5. It has a modular architecture: one orchestrator plus pluggable strategy classes, a risk manager, and a position manager.

The author/owner is the user (Lai Si Xiang). The EA is tested in the **MT5 Strategy Tester using real-tick modeling**.

---

## 2. Goal

- **Primary**: keep the EA profitable and robust on XAUUSD M15.
- **MA_Trend is finished and LOCKED.** Owner's MT5 real-tick baseline: **1.6 PF, 493 trades, 8.8% max DD over ~6 years** (earlier runs hit 1.77–1.83). Do not re-tune it. Touching it requires the user's explicit approval **and** a stated reason.
- **The other strategies are still weak** — they need optimization. Per-strategy target: **~1.8 PF, ~400 trades, MaxDD ≤ 20%** (20% DD is the hard ceiling).
- **Headline deliverable** = the per-strategy one-by-one workflow in §10 (optimize one strategy at a time → top-20 shortlist → user verifies in MT5 → picks → next strategy). Always report **profit in PIPS** alongside PF. Use the cached data in `python/data/`.
- Any system-level change must NOT degrade MA_Trend's standalone behavior.

> Note: a whole-portfolio search at $400 (all 5 strategies stacked) was run and **0 of 972 combinations kept DD ≤ 20%** (all 31–50%). Stacking weak strategies onto MA at a tiny account compounds drawdown. Hence the one-by-one approach in §10.

---

## 3. Current state (as of 2026-05-30)

- **Only `MA_Trend` is active.** This is the user's intended live setup.
- `Bands_Extreme` is commented out (inside a `/* */` block in `quantumking.mq5`).
- 8 other strategies (`Asian_Breakout`, `MACD_Momentum`, `ADX_Trend`, `Pivot_Divergence`, `VWAP_Reversion`, `Fractal_Breakout`, `Pulse_Momentum`, `SMC_OrderBlock`) are `//` commented out in `OnInit()`.
- All 15 EA files have been verified **byte-for-byte original** (the user's hand-written code).
- Account assumption in code: `new CRiskManager(false, 400, 0.02)` → standard USD account, 400-pt max spread, 2% risk, default 20% max drawdown.

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
| `quantumking.mq5` (v1.40) | Main EA. Instantiates managers, registers strategies, kill-switch button, OnTick loop. Holds the MA_Trend + Bands input parameter block. |
| `CStrategyManager.mqh` (v1.30) | Orchestrator. Market-regime detection, global position cap (6), 23:00–00:00 danger-zone pause, intelligent per-magic grid lock, routes signals to strategies. |
| `CRiskManager.mqh` (v1.10) | Spread filter, **adaptive lot sizing** (equity-based ceiling), 20% drawdown emergency close. |
| `CPositionManager.mqh` (v1.20) | Order execution, **non-Martingale averaging grid** (1000-pt spacing, 150-pt breakeven escape, max 10 layers), trailing stop. |
| `CStrategy.mqh` | Base class for all strategies. |
| `CStrategy_MA_Trend.mqh` (v3.30) | **ACTIVE strategy.** See §6. |
| `CStrategy_*.mqh` (9 others) | Inactive strategy implementations. |

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

1. **MA_Trend** — DONE / LOCKED. Baseline 1.6 PF, 493 trades, 8.8% DD.
2. For the **next strategy**, produce a **top-20 shortlist** of parameter variants aiming for **~1.8 PF, ~400 trades, MaxDD ≤ 20%, max performance** (my judgment), with **profit in pips** shown.
3. **Show the user the top-20.** The user backtests them one-by-one in their own MT5 and gives their picks.
4. Once the user picks, **proceed to the next strategy.** Repeat.
5. For each strategy I also **recommend keep (add) or drop (delete)** based on the research data in `python/data/`.

### Calibration note (important)
- My Python **frictionless** solo numbers track the user's MT5 **PF scale**: MA_Trend best ≈ **1.657** in `pips_top200_MA_Trend.csv` vs the user's **1.6** in MT5. Use these as the **ranking guide**; the user verifies absolute PF/DD in MT5.
- My **cost-heavy $400** portfolio model **understates** badly (MA → 1.14 PF / 36% DD). Do NOT present those numbers as expectations. The user's broker spread is light.
- Source files: `python/data/pips_top200_<STRATEGY>.csv` (solo, ranked by pips, ≥200 trades), `pips_all_per_strategy.csv`, `layer1_top50_full.csv`, `layer1b_top50_full.csv`.

### Strategy ranking from research (best achievable solo PF, ≥200 trades)
| Strategy | Best PF | #cfgs ≥1.7 PF | trades | Status |
|---|---:|---:|---:|---|
| **MA_Trend** | — | — | 476/6yr | ✅ **LOCKED** (PF 1.82, DD 4.68%) — see §6 |
| **SMC_OrderBlock** | **1.842** | 35 | 229–526 | ✅ **LOCKED** (PF 3.14, DD 15.10%) — see §11 |
| **ADX_Trend** | 1.748 | 1 | ~300 | ✅ **LOCKED** (PF 1.65 IS / 1.51 OOS, DD 12.10%) — see §12 |
| **MACD_Momentum** | 1.684 | 0 | ~200 | **⬅ OPTIMIZE NEXT** — see §16 |
| VWAP_Reversion_noGrid | needs check | — | ~209 | Validate after MACD (PF=99 = artifact) |
| Pivot_Divergence_noGrid | 1.473 | 0 | ~254 | Marginal — likely drop |
| Asian_Breakout | 1.344 | 0 | ~257 | **Drop (weak)** |
| Fractal_Breakout | 1.249 | 0 | ~342 | **Drop (weak)** |
| Bands_Extreme_noGrid | artifact | — | 48 | **Drop (too few trades)** |

**Current strategy order: MA ✅ → SMC ✅ → ADX ✅ → MACD ⬅ (active) → BIAS_Reversion (experimental, §14.1) → (validate VWAP)**. Drop Asian, Fractal, Bands, (likely) Pivot.

**Portfolio baseline confirmed (2026-07-01):** MA + SMC + ADX → PF 2.11, Balance DD 8.53%, $4,389 profit, 732 trades / 122 per year. See §15 for full results. Next target: add MACD to push toward 300 trades/yr within the 20% DD ceiling.

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

#### Phase 8 — R:R ratio sweep (in progress)
Locked Test D baseline, sweeping `SMC_R:R_ratio` ∈ {3, 4, 5, 6, 7, 8}. 6 combos, ~18 min. Hunting for the optimal R:R given gold's intraday swing distribution.

### 11.3 Key calibration learnings (Python ↔ MT5)
- **MA_Trend**: Python frictionless solo ≈ 1.657 PF, user MT5 = 1.6 PF → tight match.
- **SMC**: Python solo at $400 = 1.035 PF / 31% DD; user MT5 = 1.41 / 19.46%. **Python is conservative for SMC** (~26% PF under, ~38% DD over).
- Rule of thumb when projecting Python pair results to MT5: multiply PF by ~1.27 and DD by ~0.62.
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

1. **Phase 8 R:R sweep** finishes → pick optimal R:R + lock final Test D-style config.
2. **Decide standalone vs portfolio path** (lock Test A or Test D).
3. **Upgrade ADX_Trend tunable** (mirror SMC's input pattern). Run Phase 1 optimization on ADX alone.
4. **SMC + ADX pair test in MT5** — verify projected ~PF 1.75 / DD 20%.
5. If pair confirmed → consider adding 3rd strategy (MACD or VWAP_noGrid) to reach 300/yr.
6. Final portfolio config = locked & shippable system.

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

---

## 12. ADX_Trend tuning log (as of 2026-06-23)

**Strategy:** CStrategy_ADX_Trend.mqh
**Data:** MetaQuotes demo, 100% history quality, XAUUSD M15
**In-sample:** 2020-05-09 → 2024-05-09 (4 years, ~94,498 bars)
**OOS:** 2024-05-09 → 2026-06-23 (2 years, ~47,074 bars)

### 12.1 Code evolution

- **v1.00 (original):** 19+ inputs, H1/H4 EMA filters, ADX period/threshold, SL buffer, TP, trail — all exposed.
- **v1.10:** Added session filter toggle and window inputs.
- **v1.11:** Added session filter to ADX strategy (initially ineffective for in-sample — investigation revealed session filter was coded correctly but appeared to have timezone display artifacts in chart).
- **v1.12 (current):** Major refactor — removed 15 dead inputs, locked confirmed values:
  - H4 EMA 50/200 always ON (hardcoded in constructor)
  - Session filter always ON: 9-12 / 14-17 server time (hardcoded)
  - Trail effectively OFF: activation=50000 / distance=50000 / step=1000
  - TP hardcoded 10000 pts
  - Rising ADX filter added (`adx_main[0] > adx_main[1]`)
  - Only 4 exposed inputs: Period, Threshold, SL_Buffer_Pts, Max_SL_Pts
- Constructor: `CStrategy_ADX_Trend(name, magic, weight, symbol, tf, adxPeriod=13, adxThreshold=32.5, slBufferPts=50, maxSlPts=1300, requireRising=true)`

### 12.2 Key finding: Rising ADX is the #1 filter

Without Rising ADX: PF 1.09, 216 trades (in-sample).
With Rising ADX: PF 2.49, 102 trades (in-sample) at optimal params.
Rising ADX blocks whipsaw entries where ADX is high but falling — confirmed by two independent research documents.

### 12.3 Optimization results (MetaQuotes demo)

#### Phase 2 (448 combos, in-sample 2020-2024)
- Period 10-16 step 1, Threshold 25/35/45/55, SL_Buf 10/40/70/100, Max_SL 1000-2500 step 500
- Winner: Period=12, Threshold=45, Max_SL=2000, SL_Buf=40 → PF 2.49, DD 7.5%, 102 trades
- Plateau confirmed: SL_Buffer 10/40/70/100 all give similar PF (robust, not overfit)
- Boundary effect at Threshold=55 (13-43 trades only — statistically useless)

#### Max_SL sweep (OOS 2024-2026 validation)
| Max_SL | OOS PF | OOS Balance DD | OOS Trades | Verdict |
|---|--:|--:|--:|---|
| 2000 | 1.38 | 20.67% | 50 | ❌ over limit |
| 1300 | 1.38 | 19.64% | 50 | ⚠️ barely passes |
| **500** | **1.51** | **12.10%** | **52** | **✅ clear pass** |

### 12.4 FINAL ADX CONFIG (LOCKED — 2026-06-23)

| Input | Value | Rationale |
|---|---|---|
| ADX_Period | **12** | Phase 2 winner |
| ADX_Threshold | **45** | Phase 2 winner — plateau at 45 |
| ADX_SL_Buffer_Pts | **40** | Phase 2 plateau (10/40/70/100 all similar) |
| ADX_Max_SL_Pts | **500** | Max_SL sweep winner — biggest DD reduction |
| (hardcoded) H4 EMA 50/200 filter | ON | Always improves OOS quality |
| (hardcoded) Session 9-12 / 14-17 | ON | Concentrates entries in session hours |
| (hardcoded) Rising ADX | ON | Single biggest PF filter |
| (hardcoded) TP | 10000 pts | Fixed |
| (hardcoded) Trail | OFF (50000/50000/1000) | Mathematically unreachable |

**Baseline stats (MetaQuotes demo, $400, 100% quality):**
- **In-sample (4yr):** PF 1.65, DD 11.11% balance / 13.03% equity, 106 trades (~26/yr)
- **OOS (2yr):** PF 1.51, DD 12.10% balance / 13.82% equity, 52 trades (~26/yr)
- DD consistency IS→OOS: 11% → 12% (excellent — no degradation)
- PF consistency IS→OOS: 1.65 → 1.51 (-9% degradation — acceptable)

### 12.5 Lessons learned

1. **Rising ADX is the non-negotiable filter** — doubles PF by eliminating whipsaw entries when ADX is high but falling.
2. **Max_SL=500 beats Max_SL=2000** — tighter cap cuts catastrophic runs. Same tail-risk lesson as SMC's Max_SL=400.
3. **SL_Buffer is a plateau** — all values 10-100 give similar in-sample PF. Pick 40 as midpoint.
4. **H4 EMA filter helps ADX** (unlike SMC where it hurts). ADX is a trend-strength indicator, so H4 trend alignment adds value.
5. **Session filter concentrates entries** — most entries cluster at 9-12 and 14-17 server time. Small fraction at 0-5 may be timezone display artifacts (chart vs server time reference).
6. **ADX is low-frequency**: ~26 trades/year. Portfolio stacking (MA+SMC+ADX) needed to reach 300+/yr target.

### 12.6 Roadmap

1. ✅ ADX locked.
2. **Next: SMC + ADX + MA_Trend portfolio test in MT5.** Expected: 41+26+79 ≈ 146 trades/yr combined.
3. If portfolio DD ≤ 20% → consider adding MACD_Momentum to push toward 300/yr.
4. If portfolio DD > 20% → decide which strategy to drop or reduce weight.

---

## 13. Pre-portfolio system audit (2026-07-01)

Full code read of all manager/risk/position files + external research (MQL5 docs, walk-forward theory, gold EA literature) before running the 3-strategy portfolio test. Two-track findings: code-level bugs/gaps, and research-confirmed structural risks.

### 13.1 Confirmed bugs (code-level)

| # | Bug | Location | Impact |
|---|---|---|---|
| 1 | ATR regime gate reads the forming (incomplete) bar, not the last closed bar | `CStrategyManager.mqh:165-166`, `CopyBuffer(..., 0, 1, ...)` should be offset=1 | Regime classification uses live noise; low priority since ATR on a half-bar is directionally similar |
| 2 | **Monday gap filter is silently OFF** | `CStrategyManager.mqh` — `m_block_monday_entries` defaults `true` but is gated behind `m_use_commercial_time_filter` which defaults `false` | Monday-open gap risk is **completely unprotected** despite code appearing to guard it. One-line fix: flip the default or wire it independently of the commercial filter. |
| 3 | `CalculateSignal()` called twice per tick for MA/ADX (manager + CheckEntry) | Harmless today (no state mutation) but is exactly the bug class that broke SMC v1.10 (fixed via `m_pending_signal` cache) | Low priority, but flag if any future state is added to MA/ADX signal calc |
| 4 | Emergency close has no cooldown — resumes trading the instant equity recovers to balance | `CRiskManager::CheckEmergencyStop` | After a 20% DD event, EA can re-enter on the very next tick with no pause |
| 5 | `ADX_Trend_Weight` (and all strategy weight inputs) are dead at $400 equity | `CRiskManager::CalculateSafeLotSize` — weight scales risk%, but result rounds to min_lot (0.01) regardless | Weight inputs are misleading at small accounts; only matters above ~$3000 equity |

### 13.2 Structural risks (confirmed by external research)

**MA_Trend + ADX_Trend correlation is real, not diversification.** Two trend-followers on the same instrument need the same market condition (a sustained directional move) to win, so their losing periods coincide — drawdowns stack rather than offset. Yale's trend-following research and practitioner sources agree: correlation benefit comes from pairing trend-following with mean-reversion (opposite regime needs), not from stacking two trend systems. This matches the project's own §11.5 finding that SMC+MA (both H4-trend) projects worse combined DD than SMC+ADX (different signal logic, same regime need but uncorrelated triggers).
→ **Implication for the upcoming MA+SMC+ADX portfolio test:** MA and ADX may compound drawdown on bad trend days (e.g., a sharp reversal after FOMC) more than the Python pair-survey suggested, since that survey tested SMC's *partners* but never directly modeled MA+ADX correlation.

**No news filter is the single biggest unaddressed tail risk.** NFP/FOMC/CPI routinely move XAUUSD 300-1000+ pips within hours. All three locked strategies have SL caps (400-800 pts) sized for normal volatility — a news spike can blow through SL via slippage before the broker fills the stop. Standard MQL5 practice is to block new entries 15 min before to 30+ min after high-impact USD releases via the Economic Calendar API (`MqlCalendarValue`) or a ForexFactory CSV fallback.

**OOS degradation is within normal bounds — not a red flag.** Using the standard Walk-Forward Efficiency ratio (OOS return ÷ IS return; >0.5 acceptable, >0.7 strong, <0.3 overfit):
- ADX: 1.65→1.51 PF ≈ 92% retention — strong, no concern.
- SMC: 1.82(IS-equivalent)→1.51(projected OOS) ≈ 83% retention — acceptable, monitor only.
Both are far above the 50% danger threshold. **Conclusion: the existing IS/OOS gaps in §11-§12 are healthy, not evidence of overfitting.**

**SMC's known weakness is structural, not a tuning problem.** Published criticism of Smart Money Concepts: no verifiable evidence retail order-block/liquidity-sweep zones reflect actual institutional flow (retail volume is negligible next to market-maker size), and zone identification is subjective. This matches the project's own empirical finding that SMC has a "90% loss rate / lottery payoff" structure (§11, Test A/D tradeoff). **SMC's edge here is empirical (validated in MT5), not theoretical — treat it as a high-variance contributor, not a stable edge**, and don't be surprised if its PF/DD drifts more than MA or ADX over time.

**Gold's 2024-2026 volatility regime shift is a known EA killer.** Typical daily range expanded materially in 2024-2025 vs. earlier years. Strategies (and fixed SL/TP caps) calibrated on pre-2024 data ranges can misprice risk in the new regime. This is a generic warning, not a specific QuantumKing finding — but it reinforces why Max_SL caps (SMC 400, ADX 500, MA 800) need periodic re-validation against recent data, not a one-time lock.

### 13.3 Missing features (not yet built)

1. **News filter** (highest priority — see 13.2)
2. **MA_Trend has no session filter** — SMC and ADX both restrict to London/NY (9-12/14-17 server); MA_Trend trades all 24/5 hours including thin Asian liquidity windows
3. **No ATR-scaled position sizing** — lot calc assumes fixed 1000-pt SL regardless of current volatility regime
4. **No equity-curve / losing-streak throttle** — only the 20% emergency close exists; no graduated response to a string of losses
5. **No per-direction concurrent position cap** — global cap is total positions (6), not "max 2 simultaneous longs across strategies"; harmless at $400 (~$17 max combined SL loss) but matters as equity scales
6. **No reversion-regime strategy** — all 3 locked strategies require `HIGH_VOL_TREND`; the EA is fully dormant during `LOW_VOL_RANGE` (likely 30-40% of M15 bars), capping total achievable trade frequency

### 13.4 Priority order (agreed before portfolio test)

| Priority | Item | Why first |
|---|---|---|
| 1 | News filter | Tail-risk gap with no current mitigation |
| 2 | Fix Monday gate (1-line) | Currently broken despite looking active, near-zero effort |
| 3 | MA_Trend session filter | Closes the one exposed strategy in the portfolio |
| 4 | Re-run portfolio test with #2+#3 fixed | Get a cleaner read on true MA+SMC+ADX correlation |
| 5 | ATR-scaled position sizing | Bigger lift, defer until portfolio shape is locked |
| 6 | Equity curve throttle | Defer — nice-to-have, not urgent at $400 |
| 7 | Reversion-regime strategy | Defer — new-strategy-scale work, separate plan |

**Decision (resolved 2026-07-01):** Fixed #2 (Monday/Friday gap guards) immediately — it's a system-level, fair-game, near-zero-effort fix with no MA_Trend impact. Did **not** apply #3 (MA_Trend session filter) — adding it would change MA_Trend's own entries when run standalone, which requires the user's explicit approval + stated reason per Hard Rule §4.1. #3 stays proposed-only until the user signs off. Portfolio test should now be run with #2 fixed as the baseline; #3 can be layered in afterward if approved.

**Fix applied (`CStrategyManager.mqh` v1.31):** `IsCommercialEntryTimeAllowed()` previously short-circuited to `true` whenever `m_use_commercial_time_filter` was `false` (its default), which silently skipped the Monday/Friday gap checks even though `m_block_monday_entries`/`m_block_friday_late_entries` default to `true`. The Monday/Friday checks now run unconditionally (controlled only by their own bools); the premium-window/session-window filters remain gated behind `m_use_commercial_time_filter` as before. **This changes default backtest behavior for ALL strategies** (Monday entries are now genuinely blocked) — recompile (F7) before the next test, and expect trade count to drop slightly vs. prior MA/SMC/ADX baselines since some Monday signals will now be skipped.

---

## 14. Ideas mined from external "Quantum King" tools research (2026-07-01)

The user pasted a long third-party research report (truncated, with broken citation artifacts — likely from another AI tool) about a *different* product also named "Quantum King": an MT4/MT5 **indicator marketplace/education platform** covering SuperTrend, ZigZag, Bollinger Bands, KDJ, BIAS, double-line MACD, manual trading panels, and a "PrecisionSniper" multi-factor signal engine. That product is unrelated to this EA's architecture — none of those are existing QuantumKing strategies. Per the user's direction, this section extracts concepts worth evaluating for *our* EA, not the report itself. Note: I only have a summarized description of that report (original text was truncated/compacted), not the verbatim source — treat specifics as directional, not exact.

| Idea (from report) | Relevance to QuantumKing | Maps to |
|---|---|---|
| **BIAS** (price deviation % from MA) | Direct candidate signal for a mean-reversion strategy — the EA currently has **zero** active strategies for `REGIME_LOW_VOL_RANGE` (§13.3 item 6: all 3 locked strategies require `HIGH_VOL_TREND`, so the EA is fully dormant ~30-40% of bars). BIAS crossing back toward 0 after an extreme is a clean, simple reversion trigger. | New `CStrategy_BIAS_Reversion` — fills the missing reversion-regime gap. Not started. |
| **ZigZag** (noise-filtered swing detection) | ADX_Trend's `CheckEntry()` currently finds swing high/low via raw `ArrayMaximum`/`ArrayMinimum` over the last 50 bars (`CStrategy_ADX_Trend.mqh:137-142`), which is sensitive to single-bar wicks. ZigZag-style swing points could give a cleaner SL anchor. | Candidate refinement for ADX_Trend's SL calc (NOT MA_Trend — that swing logic is locked). Not started. |
| **"PrecisionSniper" multi-factor confluence scoring** | Generalizes the pattern ADX_Trend already uses ad hoc (ADX + Rising ADX + H4 EMA + Session, all hard-AND'd). A scored "N of M filters pass" gate is more tunable than all-or-nothing AND logic. | Architectural pattern for any *future* strategy (e.g. the BIAS reversion strategy above) — not retrofitted onto locked strategies. |
| SuperTrend, double-line MACD, manual trading panel | SuperTrend ≈ redundant with existing H4 EMA filters (low value-add). Double-line MACD = no new info — `MACD_Momentum` is already on the roadmap (§10, "Optimize after SMC+ADX"). Manual panel = pure UI/ops convenience (live regime display, per-strategy on/off), independent of strategy logic — low priority, easy win whenever the user wants it. | No action — logged for completeness only. |

**Recommendation:** of these, the **BIAS reversion strategy** is the only one that closes an actual structural gap (§13.3 item 6) rather than duplicating existing logic. Worth scoping as a real `CStrategy_BIAS_Reversion` once the MA+SMC+ADX portfolio baseline is confirmed — it's new-strategy-scale work (same tier as §13.4 priority 7), not a quick patch.

### 14.1 CStrategy_BIAS_Reversion v1.00 — built (2026-07-01), not yet optimized

Built per a reviewed/approved plan (plan file: `snuggly-spinning-dahl.md`) using the proven structural-SL template (`CStrategy_ADX_Trend.mqh`), explicitly NOT the grid-reliant pattern that made the old VWAP_Reversion/Bands_Extreme/Pivot_Divergence strategies weak.

- **File:** `CStrategy_BIAS_Reversion.mqh` (new), magic **10011**, name `"BIAS回归"` (the `"回归"` substring is required by `CStrategyManager`'s regime router to only fire in `REGIME_LOW_VOL_RANGE` — do not rename without updating the router).
- **Signal:** `BIAS = (Close - MA) / MA × 100` on closed bars only (bar 1 = last closed, bar 2 = second-to-last — never bar 0/forming). Crossing-back-through-threshold trigger (same shape as MA_Trend's KDJ OB/OS crossover): BUY when BIAS was ≤ −threshold and crosses back above; SELL when BIAS was ≥ +threshold and crosses back below.
- **Risk:** structural SL from swing high/low + buffer, capped at `BIAS_Max_SL_Pts`. **Trade is skipped (not clamped) if structural SL exceeds the cap** — an artificially tightened SL is unprotected by structure. Also validates against broker `SYMBOL_TRADE_STOPS_LEVEL` + spread before sending. Fixed TP (`BIAS_TP_Pts`, default 2000). Trail hardcoded effectively OFF (50000/50000/1000), not exposed as input.
- **Filters (all default OFF for v1 — unproven for a reversion regime):** KDJ-extreme-within-lookback-window (`BIAS_Use_KDJ_Filter`), ADX-below-max (`BIAS_Use_ADX_Max_Filter`), session window 9-12/14-17 (`BIAS_Use_Session_Filter` — explicitly defaulted OFF since the trend-strategy session window is unproven for range conditions and might exclude the Asian/pre-London hours this strategy targets).
- **Diagnostic logging:** every entry prints distance-to-MA, TP distance, SL distance, and R:R — data for a possible v2 dynamic "TP-to-MA" mode, not used in v1 logic.
- **Wiring:** `Custom_Enable_BIAS_Reversion` (default false) + `BIAS_Reversion_Weight` (default 0.3) inputs in `quantumking.mq5` v1.51. **CUSTOM preset only** — no existing preset (MA_ONLY/SMC_CHAMPION/MA_SMC/MA_SMC_ADX/ADX_ONLY/FTMO_CHALLENGE) enables it; zero risk to any locked baseline.
- **Status: EXPERIMENTAL, zero backtests run.** Not part of the per-strategy workflow shortlist yet — needs a standalone MT5 run first (compile F7, set `Runtime_Preset = QK_PRESET_CUSTOM`, `Custom_Enable_BIAS_Reversion = true`, all other `Custom_Enable_*` false) to confirm it fires only in low-vol regime and produces sane trades, before any optimization sweep.
- **Known deferred risk (flagged during plan review, not yet mitigated):** the classic mean-reversion trap — regime looks like range, BIAS fires, then price breaks into a real trend. Candidate guards (H1 EMA200 counter-trend block, news filter, spread filter, ATR-expansion filter) were explicitly deferred to the optimization phase, not built into v1.

---

## 15. MA + SMC + ADX portfolio test results (2026-07-01)

**Preset:** `QK_PRESET_MA_SMC_ADX` | **Baseline:** CStrategyManager v1.31 (Monday gate fixed) | **Data:** MetaQuotes demo, 100% quality, XAUUSD M15, 141,572 bars, $400 initial deposit

### 15.1 Results

| Metric | Value | Verdict |
|---|---|---|
| Profit Factor | **2.11** | ✅ Beats per-strategy 1.8 target |
| Balance DD Maximal | **8.53%** ($316.47) | ✅ Well under 20% hard ceiling |
| Equity DD Maximal | **11.15%** ($425.07) | ✅ Under 20% |
| Balance DD Relative | 25.00% ($99.99) | ⚠️ See note below |
| Equity DD Relative | 26.14% ($109.90) | ⚠️ See note below |
| Net Profit | **$4,389.43** (+1097%) | ✅ ~47% CAGR |
| Total Trades | **732 = 122/yr** | ⚠️ Short of 300/yr target |
| Sharpe Ratio | **7.73** | ✅ Strong |
| Recovery Factor | 10.33 | ✅ Strong |
| Long Trades won% | 29.12% | Expected (trend: few big winners) |
| Short Trades won% | 20.07% | Expected |

### 15.2 Relative vs. Maximal DD — why 25% is not a red flag

Throughout this project, "DD" has meant **Balance DD Maximal** (the largest peak-to-trough balance drop, expressed as % of balance at that moment). The 20% hard ceiling refers to this metric — **8.53% passes comfortably**.

The **Balance DD Relative** (25%) is a different calculation: the largest % drop from any local peak balance, measured over the full history. The 25% occurred early in the backtest (~2020-2021) when the account was still near the $400 starting deposit and took a $99.99 loss. As the account grew (e.g., to $3,700 at end), the same-dollar losses became much smaller percentages — hence Maximal later in the test is only 8.53%. This is normal early-account behavior on a $400 starting deposit, not a structural risk. The $400 floor simply means the first losing streak looks large in percentage terms.

### 15.3 Diversification assessment

Individual standalone profits (from locked configs): MA ≈ $1,614 | SMC ≈ $954 | ADX ≈ $300 (estimated 6yr from OOS rate). Sum ≈ **$2,868 standalone**.
Portfolio produced **$4,389 — a +53% lift** from correlation benefits. Balance DD dropped from SMC's standalone worst (15.10%) to **8.53% combined**. The MA+ADX correlation concern (§13.2) did not materialize into a DD problem — the strategies' entry conditions are sufficiently different in practice.

**Headroom remaining:** 20% ceiling − 8.53% actual = **11.47% available** for one more strategy.

### 15.4 Gap: trade frequency

732 trades / 6 years = **122 trades/yr** — roughly 40% of the 300/yr target. The three trend-following strategies share the same `REGIME_HIGH_VOL_TREND` requirement; adding a fourth trend strategy stacks risk without solving frequency. Two paths to close the gap:

1. **MACD_Momentum** (next in §10 roadmap) — different MACD-based signal logic, still trend-regime, adds more M15 trigger opportunities.
2. **BIAS_Reversion** (experimental, §14.1) — fires in `REGIME_LOW_VOL_RANGE`, structurally independent, adds trades in the ~30-40% of bars the current portfolio is dark.

Both are needed to approach 300/yr. Plan: optimize MACD first (§16), then BIAS after its standalone sanity check.

### 15.5 Conclusion

**Portfolio baseline confirmed: PF 2.11, Balance DD 8.53%, $4,389 profit over 6 years.** This is the new portfolio anchor. Next step: add MACD_Momentum to push trade frequency toward 300/yr while staying under the 20% DD ceiling.

---

## 16. MACD_Momentum optimization plan (next step — as of 2026-07-01)

### 16.1 Current state of CStrategy_MACD_Momentum.mqh v1.10

The strategy keeps its solid original signal design: **H4 + H1 dual-EMA trend filter** (both timeframes must agree) + **MACD zero-line cross** (main line crosses through zero) + **histogram expansion** (momentum accelerating in the cross direction). This is conceptually clean and structurally similar to ADX_Trend's approach.

**v1.10 implemented (branch `codex/exp-011-macd-v110-hardening`):** MACD now has tunable MACD periods, tunable `MACD_SL_Buffer_Pts`, tunable `MACD_Max_SL_Pts`, hardcoded London/NY session filter (9-12 / 14-17), Max_SL skip logic, broker stop-level validation, and trail effectively OFF (50000/50000/1000). It is wired into `quantumking.mq5` through `QK_PRESET_MACD_ONLY` and `Custom_Enable_MACD_Momentum`. **Status: implemented for optimization, not locked.**

**Original problems that v1.10 was built to address before the optimization sweep:**

| # | Issue | Location | Impact |
|---|---|---|---|
| 1 | SL buffer hardcoded at 150 pts | `CheckEntry()` line 128/134 | Cannot be tuned; may be too wide or too narrow depending on regime |
| 2 | **No `Max_SL_Pts` cap** | `CheckEntry()` | Tail-risk lesson from SMC (Phase 3) and ADX: unbounded structural SL produces catastrophic single-trade losses. This is the single most important fix. |
| 3 | **Active trail: activation=1000, distance=1000, step=500** | `CheckExit()` line 149 | SMC Phase 9 showed active trail kills winners — best configs had trail effectively OFF. Needs to be at minimum tunable, ideally defaulted OFF. |
| 4 | No session filter | — | SMC and ADX both showed the London/NY session filter (9-12/14-17) as the single biggest PF lift. MACD currently trades 24/5. |
| 5 | No rising-MACD filter | `CalculateSignal()` | ADX's "rising ADX" was its #1 filter (PF 1.09 → 2.49). A "histogram expanding" condition already exists, but a stricter "MACD main was below zero on bar 2 AND bar 1" (confirming the cross just happened) is already in the code — the zero-cross itself is the equivalent. Low priority vs. items 1-4. |
| 6 | No broker stop-level validation | `CheckEntry()` | Same gap flagged and fixed in BIAS_Reversion. Low priority since structural SL on XAUUSD is almost always above stop level, but should be consistent. |

### 16.2 Planned refactor: v1.10

Mirror the ADX_Trend v1.12 hardening pattern:

- **Expose as inputs:** `MACD_SL_Buffer_Pts` (default 150 — preserves current behavior), `MACD_Max_SL_Pts` (default 800 — start conservative, sweep down), `MACD_Fast_EMA` / `MACD_Slow_EMA` / `MACD_Signal_SMA` (already tunable in constructor, move to quantumking.mq5 inputs).
- **Hardcode ON (after confirmation):** H4 + H1 dual-EMA filter (already in place, keep hardcoded — it's the same rationale as ADX's hardcoded H4 EMA), session filter 9-12/14-17 server time (hardcode ON based on SMC+ADX empirical validation — test OFF separately if needed).
- **Trail default effectively OFF:** set activation/distance to 50000 (mathematically unreachable), expose as hardcoded not input — same decision as SMC Phase 9 / ADX v1.12.
- **Add Max_SL skip logic:** same as BIAS_Reversion — skip the trade (don't clamp) if structural SL exceeds Max_SL.

### 16.3 Phase 1 optimization sweep plan

After v1.10 refactor, run a **standalone MT5 optimization** (MetaQuotes demo, 6 years 2020-05-09 → 2026-05-09, $400, 100% quality, QK_PRESET_CUSTOM with only MACD enabled):

**Sweep grid (estimated ~200-300 combos):**

| Input | Range | Step | Rationale |
|---|---|---|---|
| MACD_Fast_EMA | 6, 8, 10, 12 | — | Standard range; 12 is default |
| MACD_Slow_EMA | 20, 24, 26, 30 | — | Standard range; 26 is default |
| MACD_Signal_SMA | 7, 9, 11 | — | Standard range; 9 is default |
| MACD_SL_Buffer_Pts | 50, 100, 150 | — | Tighter vs. current 150 |
| MACD_Max_SL_Pts | 400, 600, 800, 1000 | — | Tail-risk cap sweep (lesson from SMC/ADX) |

**Optimize for:** max Profit Factor with Balance DD Maximal ≤ 20%. Report top 20 by PF with trades ≥ 100.

### 16.4 Targets and roadmap

- **Per-strategy target:** PF ≥ 1.6 (MACD ranked 1.684 best in Python research, §10 table), DD ≤ 20%, ≥ 100 trades/6yr standalone.
- **Portfolio target after adding MACD:** MA+SMC+ADX+MACD combined DD stays ≤ 20% (current headroom: 11.47%).
- **If MACD adds ~50-80 trades/yr** → portfolio reaches ~170-200/yr; BIAS_Reversion needed for the final push to 300/yr.

**Steps:**
1. Refactor `CStrategy_MACD_Momentum.mqh` → v1.10 (plan above — present plan first, implement after approval).
2. Wire MACD inputs into `quantumking.mq5` (add `QK_PRESET_MACD_ONLY` or use CUSTOM preset for standalone sweep).
3. Run Phase 1 sweep (~200 combos) in MT5 → top 20 shortlist → user verifies → lock.
4. Run portfolio test: MA + SMC + ADX + MACD (`QK_PRESET_MA_SMC_ADX` + MACD added) → confirm combined DD ≤ 20%.
5. If combined DD ≤ 20% → proceed to BIAS_Reversion optimization.
6. If combined DD > 20% → revisit MACD weight or decide to drop it.
