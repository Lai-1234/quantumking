"""Python port of CRiskManager + CPositionManager (research version).

Faithful to the MQL5 logic where it matters for backtests:
- spread filter (gold cap 400 pts)
- equity-adaptive lot sizing (1000 pts assumed SL, $1000/0.01 ceiling, hard cap 1.0)
- three-parameter trailing stop (activation, distance, step)
- non-Martingale equal-volume grid (breakeven escape at avg + 150 pts,
  add layer when price moves grid_spacing pts against lowest fill)
- 20% drawdown emergency close-all

Backtest assumptions
--------------------
XAUUSD: point = 0.01, contract size = 100 oz, tick value ≈ 1 USD per pip
per 0.01 lot. We treat 1 pt = 0.01 USD per 0.01 lot, so $1 = 100 pts on
0.01 lot. Adjust :data:`POINT_VALUE_PER_LOT` if your broker differs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# XAUUSD constants. USD profit per 1.0 lot per 1.0 point of price move.
# Price moves 0.01 = 1 point; 1.0 lot = 100 oz; profit = 1 USD per pt per lot.
POINT_VALUE_PER_LOT = 1.0
POINT = 0.01  # price per point


@dataclass
class RiskParams:
    max_spread_pts: int = 400
    risk_pct: float = 0.02
    max_drawdown_pct: float = 0.20
    sl_assumed_pts: int = 1000  # used by adaptive lot sizing


@dataclass
class GridParams:
    breakeven_pts: int = 150
    grid_spacing_pts: int = 1000
    max_grids: int = 10


def adaptive_lot(equity: float, *, weight: float = 1.0,
                 min_lot: float = 0.01, step: float = 0.01,
                 max_lot: float = 1.0,
                 risk: RiskParams = RiskParams()) -> float:
    """Mirror of CRiskManager::CalculateSafeLotSize for XAUUSD standard USD.

    Soft ceiling: 0.01 lot per $1000 equity, hard cap 1.0, scaled by weight.
    """
    risk_money = equity * risk.risk_pct * weight
    loss_per_lot = risk.sl_assumed_pts * POINT_VALUE_PER_LOT
    raw = risk_money / loss_per_lot
    lot = (raw // step) * step

    ceiling = (equity // 1000.0) * 0.01
    ceiling = max(ceiling, min_lot)
    ceiling = min(ceiling, max_lot)
    ceiling *= weight

    if lot > ceiling:
        lot = ceiling
    if lot < min_lot:
        lot = min_lot
    if lot > max_lot:
        lot = max_lot
    return round(lot / step) * step


@dataclass
class OpenTrade:
    side: int  # +1 long, -1 short
    entry: float
    sl: float
    lot: float
    bar_in: int
    stop: float = 0.0  # trailing stop level (0 = not yet active)


@dataclass
class ClosedTrade:
    side: int
    entry: float
    exit: float
    lot: float
    bar_in: int
    bar_out: int
    pnl_usd: float
    reason: str


@dataclass
class TrailParams:
    activation_pts: int
    distance_pts: int
    step_pts: int


def update_trailing(t: OpenTrade, bid: float, ask: float,
                    trail: TrailParams) -> None:
    """In-place port of CPositionManager::ManageTrailingStop."""
    if t.side > 0:
        if (bid - t.entry) >= trail.activation_pts * POINT:
            new_sl = bid - trail.distance_pts * POINT
            if t.stop == 0 or (new_sl - t.stop) >= trail.step_pts * POINT:
                t.stop = new_sl
    else:
        if (t.entry - ask) >= trail.activation_pts * POINT:
            new_sl = ask + trail.distance_pts * POINT
            if t.stop == 0 or (t.stop - new_sl) >= trail.step_pts * POINT:
                t.stop = new_sl


def trade_pnl_usd(t: OpenTrade, exit_price: float) -> float:
    """XAUUSD: 1 lot = 100 oz, so $1 PnL per pt per 1.0 lot."""
    pts = (exit_price - t.entry) / POINT * t.side
    return pts * t.lot * POINT_VALUE_PER_LOT
