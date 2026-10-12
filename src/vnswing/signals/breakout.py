"""
Định nghĩa và tạo tín hiệu giao dịch Donchian Breakout (brk) và Pullback (pb).
"""
from typing import Tuple
import numpy as np
from vnswing.features.indicators import FeatureEngine


def generate_breakout_signals(
    F: FeatureEngine,
    n_in: int,
    m: int,
    vm: float,
    clv: float,
    rs: float,
    min_adtv: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Sinh tín hiệu Breakout đỉnh N_in phiên kèm bộ lọc.
    Trả về: (sig_matrix, strength_matrix).
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        hh = F.hh(n_in)
        sig = F.C > hh
        strength = (F.C - hh) / F.atr

        # Bộ lọc
        sig = sig & F.regime(m)[:, None] & (F.adtv >= min_adtv)
        if vm > 0:
            sig &= F.V >= vm * F.volavg
        if clv > 0:
            sig &= F.clv >= clv
        if rs > 0:
            sig &= F.rs_rank(min_adtv) >= (1.0 - rs)

    valid_mask = sig & ~np.isnan(strength)
    clean_strength = np.nan_to_num(strength, nan=-1.0)
    return valid_mask, clean_strength


def generate_pullback_signals(
    F: FeatureEngine,
    n_in: int,
    m: int,
    vm: float,
    clv: float,
    rs: float,
    min_adtv: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Sinh tín hiệu Pullback về EMA n_in trong xu hướng tăng.
    Trả về: (sig_matrix, strength_matrix).
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        e = F.ema(n_in)
        s20 = F.sma(20)
        s50 = F.sma(50)
        s20_prev5 = np.vstack([np.full((5, s20.shape[1]), np.nan), s20[:-5]])
        up = (F.C > s50) & (s20 > s50) & (s20 > s20_prev5)
        sig = up & (F.L <= e) & (F.C > e) & (F.C > F.O)
        strength = (F.C - e) / F.atr

        # Bộ lọc
        sig = sig & F.regime(m)[:, None] & (F.adtv >= min_adtv)
        if vm > 0:
            sig &= F.V >= vm * F.volavg
        if clv > 0:
            sig &= F.clv >= clv
        if rs > 0:
            sig &= F.rs_rank(min_adtv) >= (1.0 - rs)

    valid_mask = sig & ~np.isnan(strength)
    clean_strength = np.nan_to_num(strength, nan=-1.0)
    return valid_mask, clean_strength
