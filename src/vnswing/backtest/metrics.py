"""
Module đo lường hiệu suất (Performance Metrics) và tính toán Deflated Sharpe Ratio.
"""
from typing import Dict, List, Tuple
import numpy as np
from scipy.stats import norm, skew, kurtosis


def perf(ret: np.ndarray, rf: float = 0.05) -> Dict[str, float]:
    """
    Tính toán các chỉ số hiệu suất từ chuỗi lợi suất ngày:
    Sharpe, CAGR, Volatility (năm hóa với 252 phiên), Max Drawdown.
    """
    r = np.asarray(ret, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < 20 or r.std() == 0:
        return dict(sharpe=0.0, cagr=0.0, vol=0.0, mdd=0.0, calmar=0.0)

    eqc = np.cumprod(1.0 + r)
    ann_std = r.std() * np.sqrt(252)
    sr = (r.mean() - rf / 252.0) / r.std() * np.sqrt(252) if r.std() > 0 else 0.0
    cagr = eqc[-1] ** (252.0 / len(r)) - 1.0 if eqc[-1] > 0 else -1.0
    rolling_peak = np.maximum.accumulate(eqc)
    mdd = float((eqc / rolling_peak - 1.0).min())
    calmar = cagr / abs(mdd) if mdd != 0 else 0.0

    return dict(
        sharpe=float(sr),
        cagr=float(cagr),
        vol=float(ann_std),
        mdd=float(mdd),
        calmar=float(calmar),
    )


def trade_stats(trades: List[Tuple[int, float]]) -> Dict[str, float]:
    """
    Thống kê lệnh giao dịch:
    - n: tổng số lệnh
    - win: tỷ lệ thắng (lợi nhuận > 0)
    - payoff: lãi trung bình / lỗ trung bình
    - hold: số phiên nắm giữ trung bình
    """
    if not trades:
        return dict(n=0, win=np.nan, payoff=np.nan, hold=np.nan)

    h = np.array([a for a, _ in trades], dtype=float)
    r = np.array([b for _, b in trades], dtype=float)
    w = r[r > 0]
    l = r[r <= 0]

    n_trades = len(r)
    win_rate = float(len(w) / n_trades) if n_trades > 0 else np.nan
    payoff = float(w.mean() / abs(l.mean())) if len(w) > 0 and len(l) > 0 and l.mean() != 0 else np.nan
    hold_mean = float(h.mean()) if len(h) > 0 else np.nan

    return dict(n=n_trades, win=win_rate, payoff=payoff, hold=hold_mean)


def deflated_sharpe(r: np.ndarray, n_trials: int, var_sr_daily: float) -> float:
    """
    Deflated Sharpe Ratio (Bailey & López de Prado, 2014):
    Ước lượng xác suất Sharpe thật > 0 sau khi điều chỉnh cho selection bias và đa thử nghiệm (multiple testing).
    """
    r = np.asarray(r, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < 20 or r.std() == 0:
        return 0.0

    T = len(r)
    sr = r.mean() / r.std()
    euler_mascheroni = 0.5772156649

    if n_trials <= 1:
        sr0 = 0.0
    else:
        sr0 = np.sqrt(max(var_sr_daily, 1e-12)) * (
            (1.0 - euler_mascheroni) * norm.ppf(1.0 - 1.0 / n_trials)
            + euler_mascheroni * norm.ppf(1.0 - 1.0 / (n_trials * np.e))
        )

    sk = float(skew(r))
    ku = float(kurtosis(r, fisher=False))
    denom = np.sqrt(max(1.0 - sk * sr + (ku - 1.0) / 4.0 * sr**2, 1e-12))
    stat = (sr - sr0) * np.sqrt(T - 1.0) / denom

    return float(norm.cdf(stat))
