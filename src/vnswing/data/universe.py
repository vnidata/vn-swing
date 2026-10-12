"""
Xây dựng ma trận cổ phiếu đủ điều kiện giao dịch (Eligible Universe) chống survivorship bias:
- Đang niêm yết tại ngày xét (bao gồm các mã sau này bị hủy niêm yết)
- Thuộc sàn HOSE
- Giá trị giao dịch trung vị 60 phiên >= min_adtv (mặc định 10 tỷ VND)
"""
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


def build_eligible_universe(
    prices_wide_c: pd.DataFrame,
    prices_wide_v: pd.DataFrame,
    min_adtv: float = 1e10,
    delisted_symbols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Tạo ma trận boolean eligible[date, symbol].
    Chống survivorship bias: các mã hủy niêm yết vẫn được tham gia trong giai đoạn
    chúng còn niêm yết và đạt chuẩn thanh khoản.
    """
    # 1. Tính ADTV (Close * Volume median 60 phiên, shift(1))
    daily_turnover = prices_wide_c * prices_wide_v
    adtv = daily_turnover.rolling(60, min_periods=40).median().shift(1)

    # 2. Điều kiện thanh khoản
    liquidity_mask = adtv >= min_adtv

    # 3. Điều kiện đang có giao dịch (không bị NaN hay đình chỉ giao dịch tại ngày đó)
    active_mask = prices_wide_c.notna() & prices_wide_v.notna() & (prices_wide_v > 0)

    eligible = liquidity_mask & active_mask
    return eligible
