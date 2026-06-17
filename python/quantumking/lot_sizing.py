"""Lot-sizing schemes for variant testing (audit v6 Layer C).

Five strategies tested:
  1. fixed_lot        : constant lot size every trade
  2. dollar_anchored  : 0.01 lot per $1000 equity (current CRiskManager)
  3. atr_vol_adjusted : scale inversely with current ATR vs median ATR
  4. kelly_fractional : (win_rate * win/loss - loss_rate) * equity * 0.5
  5. fixed_risk_pct   : risk_pct * equity / SL distance (most common)

Each function returns lot size in standard lots.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


POINT = 0.01
POINT_VALUE_PER_LOT = 1.0  # XAUUSD


@dataclass
class LotConfig:
    scheme: str = "fixed_risk_pct"
    fixed_lot: float = 0.01
    risk_pct: float = 0.02
    weight: float = 1.0
    min_lot: float = 0.01
    max_lot: float = 1.0
    step: float = 0.01
    # for atr-adaptive
    base_lot: float = 0.05
    # for Kelly
    kelly_fraction: float = 0.5
    # for fixed-risk
    sl_assumed_pts: int = 1000


def _clip(lot: float, cfg: LotConfig) -> float:
    if lot < cfg.min_lot:
        lot = cfg.min_lot
    if lot > cfg.max_lot:
        lot = cfg.max_lot
    return round(lot / cfg.step) * cfg.step


def fixed_lot(equity: float, cfg: LotConfig, **kwargs) -> float:
    return _clip(cfg.fixed_lot * cfg.weight, cfg)


def dollar_anchored(equity: float, cfg: LotConfig, **kwargs) -> float:
    ceiling = (equity // 1000.0) * 0.01
    return _clip(ceiling * cfg.weight, cfg)


def atr_vol_adjusted(equity: float, cfg: LotConfig, *,
                      atr_now: float = 1.0, atr_median: float = 1.0,
                      **kwargs) -> float:
    """Lot inversely proportional to current vs median ATR. Wider vol -> smaller lot."""
    if atr_now <= 0:
        scale = 1.0
    else:
        scale = atr_median / atr_now
    scale = max(0.5, min(2.0, scale))
    return _clip(cfg.base_lot * scale * cfg.weight, cfg)


def kelly_fractional(equity: float, cfg: LotConfig, *,
                      win_rate: float = 0.4, win_loss_ratio: float = 2.0,
                      **kwargs) -> float:
    """f* = win_rate - loss_rate / win_loss_ratio (Kelly formula).
    Half-Kelly by default for safety."""
    f_star = win_rate - (1 - win_rate) / max(win_loss_ratio, 1e-6)
    f_star = max(0.0, f_star) * cfg.kelly_fraction
    # convert fraction-of-equity to lots: lot = (f * equity) / (SL_pts * POINT_VALUE_PER_LOT)
    sl_money_per_lot = cfg.sl_assumed_pts * POINT_VALUE_PER_LOT
    if sl_money_per_lot <= 0:
        return cfg.min_lot
    raw = f_star * equity / sl_money_per_lot
    return _clip(raw * cfg.weight, cfg)


def fixed_risk_pct(equity: float, cfg: LotConfig, **kwargs) -> float:
    """Current CRiskManager-style: risk_pct of equity / SL pts.
    Plus the $1000-per-0.01-lot ceiling.
    """
    risk_money = equity * cfg.risk_pct * cfg.weight
    loss_per_lot = cfg.sl_assumed_pts * POINT_VALUE_PER_LOT
    raw = risk_money / loss_per_lot
    raw = (raw // cfg.step) * cfg.step
    ceiling = (equity // 1000.0) * 0.01 * cfg.weight
    ceiling = max(ceiling, cfg.min_lot)
    ceiling = min(ceiling, cfg.max_lot)
    if raw > ceiling:
        raw = ceiling
    return _clip(raw, cfg)


SCHEMES: dict[str, Callable] = {
    "fixed_lot": fixed_lot,
    "dollar_anchored": dollar_anchored,
    "atr_vol_adjusted": atr_vol_adjusted,
    "kelly_fractional": kelly_fractional,
    "fixed_risk_pct": fixed_risk_pct,
}


def compute_lot(equity: float, cfg: LotConfig, **state) -> float:
    fn = SCHEMES.get(cfg.scheme, fixed_risk_pct)
    return fn(equity, cfg, **state)
