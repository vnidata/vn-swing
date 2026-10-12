"""
Module tính toán đặc trưng và chỉ báo kỹ thuật (không look-ahead).
Tất cả các đặc trưng rolling đều phải shift(1) khi so sánh với giá hiện tại.
"""
from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd


class FeatureEngine:
    """
    Trích xuất đặc trưng giá, khối lượng và chỉ số cho danh mục cổ phiếu.
    Nhận vào dict các DataFrame dạng wide (index: date, columns: symbol).
    """

    def __init__(self, wide_data: Dict[str, pd.DataFrame], idx_close: pd.Series):
        self.dates = wide_data["open"].index
        self.symbols = wide_data["open"].columns
        self.O = wide_data["open"].values
        self.H = wide_data["high"].values
        self.L = wide_data["low"].values
        self.C = wide_data["close"].values
        self.V = wide_data["volume"].values

        self.Hdf = wide_data["high"]
        self.Ldf = wide_data["low"]
        self.Cdf = wide_data["close"]
        self.Vdf = wide_data["volume"]
        self.Odf = wide_data["open"]
        self.idx = idx_close

        # 1. ADTV: Giá trị giao dịch trung vị 60 phiên, shift(1)
        self.adtv = (self.Cdf * self.Vdf).rolling(60, min_periods=40).median().shift(1).values

        # 2. True Range & ATR14
        cp = np.vstack([np.full((1, self.C.shape[1]), np.nan), self.C[:-1]])
        tr = np.maximum(self.H - self.L, np.maximum(np.abs(self.H - cp), np.abs(self.L - cp)))
        self.atr = pd.DataFrame(tr, index=self.dates, columns=self.symbols).rolling(14, min_periods=10).mean().values

        # 3. Khối lượng trung bình 20 phiên, shift(1)
        self.volavg = self.Vdf.rolling(20, min_periods=15).mean().shift(1).values

        # 4. CLV (Close Location Value)
        rng = self.H - self.L
        with np.errstate(invalid="ignore", divide="ignore"):
            self.clv = np.where(rng > 0, (self.C - self.L) / rng, 0.5)

        # Caching dictionaries
        self._sma: Dict[int, np.ndarray] = {}
        self._ema: Dict[int, np.ndarray] = {}
        self._hh: Dict[int, np.ndarray] = {}
        self._ll: Dict[int, np.ndarray] = {}
        self._reg: Dict[int, np.ndarray] = {}
        self._rsr: Dict[int, np.ndarray] = {}
        self._sig: Dict[Tuple, Tuple[np.ndarray, np.ndarray]] = {}

    def sma(self, n: int) -> np.ndarray:
        if n not in self._sma:
            self._sma[n] = self.Cdf.rolling(n, min_periods=n).mean().values
        return self._sma[n]

    def ema(self, n: int) -> np.ndarray:
        if n not in self._ema:
            self._ema[n] = self.Cdf.ewm(span=n, adjust=False, min_periods=n).mean().values
        return self._ema[n]

    def hh(self, n: int) -> np.ndarray:
        """Đỉnh cao nhất N phiên trước, shift(1) để không nhìn thấy nến hiện tại."""
        if n not in self._hh:
            self._hh[n] = self.Hdf.rolling(n, min_periods=n).max().shift(1).values
        return self._hh[n]

    def ll(self, n: int) -> np.ndarray:
        """Đáy thấp nhất N phiên trước, shift(1) để không nhìn thấy nến hiện tại."""
        if n not in self._ll:
            self._ll[n] = self.Ldf.rolling(n, min_periods=n).min().shift(1).values
        return self._ll[n]

    def regime(self, m: int) -> np.ndarray:
        """Bộ lọc xu hướng thị trường VN-Index: Close_idx > SMA_m(Close_idx)."""
        if m not in self._reg:
            if m == 0:
                self._reg[m] = np.ones(len(self.dates), dtype=bool)
            else:
                self._reg[m] = (self.idx > self.idx.rolling(m, min_periods=m).mean()).fillna(False).values
        return self._reg[m]

    def rs_rank(self, min_adtv: float, lb: int = 126) -> np.ndarray:
        """
        Phân vị Relative Strength (lợi suất lb phiên) trong nhóm đủ thanh khoản (ADTV >= min_adtv).
        """
        if lb not in self._rsr:
            roc = self.Cdf / self.Cdf.shift(lb) - 1.0
            elig = pd.DataFrame(self.adtv >= min_adtv, index=roc.index, columns=roc.columns)
            self._rsr[lb] = roc.where(elig).rank(axis=1, pct=True).values
        return self._rsr[lb]

    def exit_line(self, mode: str, n_out: int) -> np.ndarray:
        return self.ll(n_out) if mode == "brk" else self.sma(n_out)
