# QuantumKing

A multi-system quantitative trading framework for **XAUUSD (gold)**, combining a live MQL5 Expert Advisor for MetaTrader 5 with an independent Python research pipeline used to design, optimize, and validate the strategies before they're deployed to the EA.

The project runs two parallel tracks that inform each other:
- **MQL5 / MT5** — the production Expert Advisor (`quantumking.mq5`) that actually places and manages orders in the Strategy Tester / on a live or demo account.
- **Python** — a bar-by-bar backtesting and optimization pipeline (`python/quantumking/`) used to screen strategy ideas, run parameter grids/Optuna studies, and walk-forward validate configurations before they're ported into MQL5.

## Tech stack

| Layer | Tools |
|---|---|
| Trading platform | MetaTrader 5 (MQL5 Expert Advisor) |
| Research / backtesting | Python 3.10+, pandas, NumPy, Optuna, joblib, PyArrow (parquet), pytest |
| Data | HistData.com XAUUSD M1 ASCII exports (2020–2026), resampled to M15/H1/H4/D1 and cached as parquet |

## Core features

### 1. SMC (Smart Money Concept) system — complete
`CStrategy_SMC_OrderBlock.mqh` implements an order-block / fair-value-gap / OTE (optimal trade entry) Smart Money Concept strategy: HTF bias, break-of-structure detection via H4 fractals, FVG and OTE Fibonacci zone entries, with optional KDJ/ADX quality filters and a London/New York session filter. It went through 9 documented optimization phases in the MT5 Strategy Tester (real-tick modeling) before reaching its current "champion" configuration.

### 2. EMA + Fibonacci trend system — in development
`CStrategy_MA_Trend.mqh` is the actively-maintained trend-following strategy: an H4 EMA(fast)/EMA(slow) trend filter, an M15 stochastic ("KDJ") momentum trigger, and entries gated on price retracing into a Fibonacci zone of the recent swing, with ATR/swing-based stop loss and a trailing exit. It is the strategy currently wired into `OnInit()` in `quantumking.mq5` and continues to be re-tuned; earlier default 20/70 EMA periods and 150-pt entry zone have since been narrowed (30/50 EMA, 80-pt zone) as part of ongoing optimization.

### 3. Supporting infrastructure
- `CStrategyManager.mqh` — orchestrator: ATR-based market-regime detection (`ATR(7) > ATR(50)×1.2` ⇒ trend regime, else range regime), a global open-position cap, a low-liquidity "danger zone" pause (23:00–00:00), and per-magic-number grid-risk isolation.
- `CRiskManager.mqh` — spread filter, equity-based adaptive lot sizing, and an emergency drawdown close-out.
- `CPositionManager.mqh` — order execution, a non-Martingale averaging grid for mean-reversion strategies, and trailing-stop management.
- 7 additional strategy classes (`CStrategy_ADX_Trend`, `Asian_Breakout`, `Bands_Extreme`, `Fractal_Breakout`, `MACD_Momentum`, `Pivot_Divergence`, `Pulse_Momentum`, `VWAP_Reversion`) exist as researched-but-currently-inactive candidates; see `archive/README.md` for why each was benched and how to re-enable one.

### 4. Python research pipeline
`python/quantumking/` is an independent bar-by-bar backtest engine (`backtest.py`, `regime.py`, `risk.py`, `lot_sizing.py`, `portfolio_engine.py`, `grid_backtest.py`) plus one Python re-implementation per MQL5 strategy under `python/quantumking/strategies/`. `python/scripts/` contains 30+ numbered research scripts (symbol probing → data import → per-strategy screening → Optuna optimization → walk-forward validation → Monte Carlo → portfolio combination search). Results and audit write-ups live in `python/reports/strategy_audit*.md` and `python/data/`.

## Architecture

```
quantumking/
├── quantumking.mq5              # Main EA — OnInit/OnTick, active strategy registration
├── CStrategyManager.mqh         # Orchestrator: regime detection, position cap, danger zone
├── CRiskManager.mqh             # Spread filter, adaptive lot sizing, drawdown kill-switch
├── CPositionManager.mqh         # Order execution, averaging grid, trailing stop
├── CStrategy.mqh                # Base class for all strategies
├── CStrategy_MA_Trend.mqh       # ACTIVE — EMA + Fibonacci trend strategy
├── CStrategy_SMC_OrderBlock.mqh # Smart Money Concept strategy (complete, currently disabled while MA_Trend is re-tuned)
├── CStrategy_*.mqh              # 7 other researched strategies (inactive, see archive/README.md)
├── archive/                     # Notes on benched strategies
└── python/
    ├── quantumking/             # Backtest engine + Python strategy re-implementations
    ├── scripts/                 # Numbered research pipeline (data import → optimization → validation)
    ├── data/                    # Cached OHLCV parquet, Optuna trial CSVs, trade logs
    ├── reports/                 # strategy_audit.md / v3 / v4 / v5 / v6 write-ups
    └── tests/                   # pytest indicator tests
```

## Results

These are **Strategy Tester backtest results** (real-tick modeling, historical XAUUSD data), not live trading results. Treat them as evidence of strategy design quality, not a guarantee of future performance.

| System | Profit Factor | Max Drawdown | Trades | Window |
|---|---:|---:|---:|---|
| **SMC_OrderBlock** (champion config) | **3.14** | 15.10% | 245 | 6-year MT5 real-tick backtest (2020-05-09 → 2026-05-09), $400 starting balance |
| **MA_Trend** (locked baseline) | 1.82 | 4.68% (balance) / 5.74% (equity) | 476 | Same 6-year MT5 real-tick backtest |

The Python pipeline additionally runs rolling walk-forward optimization (`python/scripts/08_walk_forward.py`, `19_walk_forward_opt.py`) — training on a window, then testing locked parameters on the next unseen window — to check that a strategy's edge survives out-of-sample rather than being curve-fit to one period. See `python/reports/strategy_audit_v6.md` for the fullest write-up, including a portfolio-level in-sample/out-of-sample comparison and 5,000-path Monte Carlo drawdown simulation.

## Installation / Setup

### MQL5 Expert Advisor (MetaTrader 5)
1. Install MetaTrader 5 and open MetaEditor.
2. Copy `quantumking.mq5` and all `CStrategy*.mqh` / `C*.mqh` files into your `MQL5/Experts/quantumking/` folder (keep them in the same folder — the `#include` paths are relative).
3. Open `quantumking.mq5` in MetaEditor and compile (F7) to produce `quantumking.ex5`.
4. Attach the EA to an **XAUUSD, M15** chart, or load it in the Strategy Tester with real-tick modeling for backtesting. `v4_tester.ini` shows an example Strategy Tester config (symbol, period, model, date range, deposit).
5. Only `MA_Trend` is active in `OnInit()` by default. To test other strategies, uncomment the relevant `AddStrategy(...)` call — see `archive/README.md` for the archived ones.

### Python research pipeline
```bash
cd python
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r ../requirements.txt
pip install -e .              # installs the quantumking package (pyproject.toml)
```
Historical XAUUSD data (HistData.com M1 ASCII exports) is expected under `python/data/raw_histdata/` — see `python/data/README.md` for sourcing instructions. Run the numbered scripts in `python/scripts/` in order (e.g. `02_import_histdata.py` to build parquet caches, then the screening/optimization/validation scripts) to reproduce the research. Run tests with:
```bash
pytest
```

## Disclaimer

This is a research and portfolio project. All performance figures come from historical backtests / MetaTrader 5 Strategy Tester runs on a small simulated account, not audited live trading results. Nothing here is financial advice. Trading leveraged instruments like XAUUSD carries a high risk of loss.

## Author

**Lai Si Xiang**
GitHub: [github.com/Lai-1234](https://github.com/Lai-1234)
LinkedIn: [linkedin.com/in/laisixiang](https://linkedin.com/in/laisixiang)
