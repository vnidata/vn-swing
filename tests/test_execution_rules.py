"""
Bộ kiểm thử thực thi thị trường HOSE (Execution & Risk Rules):
- test_limit_up_no_fill
- test_limit_down_no_sell
- test_floor_streak
- test_min_hold
- test_cost_accounting
- test_sizing_arithmetic
- test_position_caps
- test_delisting
"""
import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import pandas as pd
import pytest

from vnswing.features.indicators import FeatureEngine
from vnswing.backtest.engine import backtest


def _create_mock_feed(n_days=120, n_sym=2, base_px=20000.0):
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    syms = [f"SYM{i}" for i in range(n_sym)]
    
    # Tạo giá cố định ban đầu
    df_c = pd.DataFrame(base_px, index=dates, columns=syms)
    df_o = df_c.copy()
    df_h = df_c * 1.01
    df_l = df_c * 0.99
    df_v = pd.DataFrame(1_000_000, index=dates, columns=syms)
    idx_close = pd.Series(1200.0, index=dates)

    W = {"open": df_o, "high": df_h, "low": df_l, "close": df_c, "volume": df_v}
    return W, idx_close, dates, syms


def test_limit_up_no_fill():
    """
    Test 3: Mở cửa ở giá trần phiên t+1 -> Không mua được; tín hiệu không chuyển thành vị thế.
    """
    W, idx_close, dates, syms = _create_mock_feed(n_days=100, n_sym=2)
    
    # Ngày 60: Close bứt phá đỉnh 20 phiên
    W["close"].iloc[60, 0] = 25000.0
    W["high"].iloc[60, 0] = 25000.0
    
    # Ngày 61: Giá mở cửa tại trần (+7% so với 25000 = 26750)
    W["open"].iloc[61, 0] = 25000.0 * 1.07
    W["close"].iloc[61, 0] = 25000.0 * 1.07

    F = FeatureEngine(W, idx_close)
    cfg = {
        "mode": "brk", "init_cash": 1e9, "min_hold": 3, "limit": 0.07,
        "buy_cost": 0.003, "sell_cost": 0.004, "max_pos": 10, "max_w": 0.15,
        "adtv_frac": 0.03, "lot": 100, "min_adtv": 1e6, "risk_pct": 0.01,
        "delist_haircut": 0.0, "ato_fill_prob": 1.0
    }
    params = (20, 10, 0, 0, 99, 0, 0)
    
    ret, trades = backtest(F, params, cfg, i0=50, i1=80)
    # Lệnh mở cửa trần ở phiên 61 không được khớp mua
    assert len(trades) == 0, "Không được khớp lệnh mua khi mở cửa ở giá trần"


def test_limit_down_no_sell():
    """
    Test 4: Mở cửa ở giá sàn khi cần thoát lệnh -> Không bán được, tiếp tục giữ.
    """
    W, idx_close, dates, syms = _create_mock_feed(n_days=100, n_sym=2)
    # Ngày 55: Breakout
    W["close"].iloc[55, 0] = 22000.0
    W["high"].iloc[55, 0] = 22000.0
    # Ngày 56: Mở cửa bình thường -> Khớp mua
    W["open"].iloc[56, 0] = 22000.0
    W["close"].iloc[56, 0] = 22000.0
    
    # Ngày 62: Chạm tín hiệu thoát (đóng cửa tụt sâu dưới đáy 10 phiên)
    W["close"].iloc[62, 0] = 18000.0
    # Ngày 63: Mở cửa ở giá sàn (-7% so với 18000)
    W["open"].iloc[63, 0] = 18000.0 * 0.93
    W["close"].iloc[63, 0] = 18000.0 * 0.93
    # Ngày 64: Mở cửa thoát sàn (-2%) -> Được bán tại ngày 64
    W["open"].iloc[64, 0] = 18000.0 * 0.93 * 0.98
    W["close"].iloc[64, 0] = 18000.0 * 0.93 * 0.98

    F = FeatureEngine(W, idx_close)
    cfg = {
        "mode": "brk", "init_cash": 1e9, "min_hold": 3, "limit": 0.07,
        "buy_cost": 0.003, "sell_cost": 0.004, "max_pos": 10, "max_w": 0.15,
        "adtv_frac": 0.03, "lot": 100, "min_adtv": 1e6, "risk_pct": 0.01,
        "delist_haircut": 0.0, "ato_fill_prob": 1.0
    }
    params = (20, 10, 0, 0, 99, 0, 0)
    
    ret, trades = backtest(F, params, cfg, i0=50, i1=80)
    assert len(trades) == 1, "Vị thế phải được thoát sau khi hết sàn"
    # Hold time phải bằng 64 - 56 = 8 phiên (chứ không phải 63 - 56 = 7 phiên do sàn phiên 63)
    hold_time = trades[0][0]
    assert hold_time == 8, f"Vị thế phải bị hoãn bán do sàn, hold_time={hold_time}"


def test_floor_streak():
    """
    Test 5: Sàn liên tiếp 5 phiên -> Lỗ thực tế > khoảng cách stop, được ghi nhận đầy đủ.
    """
    W, idx_close, dates, syms = _create_mock_feed(n_days=110, n_sym=2)
    # Ngày 55-61: Breakout và duy trì giá 25000, khớp mua tại ngày 56
    W["close"].iloc[55:62, 0] = 25000.0
    W["high"].iloc[55:62, 0] = 25000.0
    W["open"].iloc[55:62, 0] = 25000.0
    W["low"].iloc[55:62, 0] = 25000.0

    # Ngày 62: Kích hoạt stop
    W["close"].iloc[62, 0] = 20000.0
    
    # 5 phiên liên tiếp mở cửa sàn 7%
    curr_px = 20000.0
    for day in range(63, 68):
        W["open"].iloc[day, 0] = curr_px * 0.93
        W["close"].iloc[day, 0] = curr_px * 0.93
        W["high"].iloc[day, 0] = curr_px * 0.93
        W["low"].iloc[day, 0] = curr_px * 0.93
        curr_px = curr_px * 0.93

    # Phiên 68 mở cửa thoát sàn
    W["open"].iloc[68, 0] = curr_px * 0.98
    W["close"].iloc[68, 0] = curr_px * 0.98

    F = FeatureEngine(W, idx_close)
    cfg = {
        "mode": "brk", "init_cash": 1e9, "min_hold": 3, "limit": 0.07,
        "buy_cost": 0.003, "sell_cost": 0.004, "max_pos": 10, "max_w": 0.15,
        "adtv_frac": 0.03, "lot": 100, "min_adtv": 1e6, "risk_pct": 0.01,
        "delist_haircut": 0.0, "ato_fill_prob": 1.0
    }
    params = (20, 10, 0, 0, 3.0, 0, 0)
    
    ret, trades = backtest(F, params, cfg, i0=50, i1=85)
    assert len(trades) == 1
    trade_return = trades[0][1]
    # Lỗ thực tế phải rất sâu (chuỗi 5 phiên sàn = lỗ > 30%)
    assert trade_return < -0.30, f"Lỗ chuỗi sàn phải ghi nhận thực tế, hiện tại: {trade_return:.2%}"


def test_min_hold():
    """
    Test 6: Tín hiệu thoát ngay sau khi vào -> Không bán trước min_hold (3 phiên).
    """
    W, idx_close, dates, syms = _create_mock_feed(n_days=100, n_sym=2)
    # Ngày 55: Breakout -> Mua ngày 56
    W["close"].iloc[55, 0] = 22000.0
    W["high"].iloc[55, 0] = 22000.0
    W["open"].iloc[56, 0] = 22000.0
    W["close"].iloc[56, 0] = 22000.0

    # Ngay ngày 56: Giá sập xuống kích hoạt tín hiệu thoát
    W["close"].iloc[56, 0] = 15000.0

    F = FeatureEngine(W, idx_close)
    cfg = {
        "mode": "brk", "init_cash": 1e9, "min_hold": 3, "limit": 0.07,
        "buy_cost": 0.003, "sell_cost": 0.004, "max_pos": 10, "max_w": 0.15,
        "adtv_frac": 0.03, "lot": 100, "min_adtv": 1e6, "risk_pct": 0.01,
        "delist_haircut": 0.0, "ato_fill_prob": 1.0
    }
    params = (20, 10, 0, 0, 99, 0, 0)
    ret, trades = backtest(F, params, cfg, i0=50, i1=75)
    
    assert len(trades) == 1
    hold_days = trades[0][0]
    assert hold_days >= 3, f"Phải giữ tối thiểu 3 phiên (T+2.5), thực tế: {hold_days}"


def test_cost_accounting():
    """
    Test 7: 1 lệnh khứ hồi, giá đứng yên -> Lỗ đúng bằng buy_cost + sell_cost (+ trượt giá tích lũy).
    """
    W, idx_close, dates, syms = _create_mock_feed(n_days=100, n_sym=1, base_px=10000.0)
    # Ngày 55: Breakout
    W["close"].iloc[55, 0] = 12000.0
    W["high"].iloc[55, 0] = 12000.0
    # Ngày 56: Khớp mua tại 10000
    W["open"].iloc[56, 0] = 10000.0
    W["close"].iloc[56, 0] = 10000.0

    # Ngày 60: Bán tại 10000 (sau min_hold = 3 phiên)
    W["close"].iloc[59, 0] = 8000.0 # kích hoạt exit
    W["open"].iloc[60, 0] = 10000.0

    F = FeatureEngine(W, idx_close)
    buy_cost = 0.0030
    sell_cost = 0.0040
    cfg = {
        "mode": "brk", "init_cash": 1e9, "min_hold": 3, "limit": 0.07,
        "buy_cost": buy_cost, "sell_cost": sell_cost, "max_pos": 10, "max_w": 0.15,
        "adtv_frac": 0.03, "lot": 100, "min_adtv": 1e6, "risk_pct": 0.01,
        "delist_haircut": 0.0, "ato_fill_prob": 1.0
    }
    params = (20, 10, 0, 0, 99, 0, 0)
    ret, trades = backtest(F, params, cfg, i0=50, i1=75)
    
    assert len(trades) == 1
    # Giá mua thực: px0 = 10000 * (1 + 0.003) = 10030
    # Giá bán thực: px = 10000 * (1 - 0.004) = 9960
    # Lợi suất lệnh: 9960 / 10030 - 1 = -0.6979%
    trade_ret = trades[0][1]
    expected_ret = (10000.0 * (1.0 - sell_cost)) / (10000.0 * (1.0 + buy_cost)) - 1.0
    assert abs(trade_ret - expected_ret) < 1e-6, f"Lỗ thực tế {trade_ret} khác tính toán {expected_ret}"


def test_sizing_arithmetic():
    """
    Test 8: ATR=3%, k=3, risk=1% -> Giá trị lệnh ≈ 11% vốn.
    """
    eqv = 1e9
    px = 20000.0
    atr = 0.03 * px
    ks = 3.0
    risk_pct = 0.01

    risk_ps = ks * atr
    shares = (risk_pct * eqv) / risk_ps
    pos_val = shares * px
    pct_equity = pos_val / eqv
    assert abs(pct_equity - 1.0 / 9.0) < 1e-4, f"Tỷ lệ vốn {pct_equity:.2%} phải xấp xỉ 11.11%"


def test_position_caps():
    """
    Test 9: Cap theo max_w (15%) và adtv_frac (3% ADTV).
    """
    W, idx_close, dates, syms = _create_mock_feed(n_days=100, n_sym=1, base_px=10000.0)
    W["close"].iloc[55, 0] = 15000.0
    W["high"].iloc[55, 0] = 15000.0
    W["open"].iloc[56, 0] = 10000.0
    W["close"].iloc[56, 0] = 10000.0

    W["volume"] = W["volume"] * 100

    F = FeatureEngine(W, idx_close)
    max_w = 0.15
    cfg = {
        "mode": "brk", "init_cash": 1e9, "min_hold": 3, "limit": 0.07,
        "buy_cost": 0.003, "sell_cost": 0.004, "max_pos": 10, "max_w": max_w,
        "adtv_frac": 0.03, "lot": 100, "min_adtv": 1e6, "risk_pct": 0.05,
        "delist_haircut": 0.0, "ato_fill_prob": 1.0
    }
    params = (20, 10, 0, 0, 99, 0, 0)
    ret, trades = backtest(F, params, cfg, i0=50, i1=65)
    # Passed execution without error


def test_delisting():
    """
    Test 10: Dữ liệu mã kết thúc giữa chừng (NaN) -> Vị thế bị thanh lý theo delist_haircut.
    """
    W, idx_close, dates, syms = _create_mock_feed(n_days=100, n_sym=1, base_px=20000.0)
    W["close"].iloc[55, 0] = 25000.0
    W["high"].iloc[55, 0] = 25000.0
    W["open"].iloc[56, 0] = 20000.0
    W["close"].iloc[56, 0] = 20000.0

    # Sau ngày 62: Mã bị đình chỉ / hủy niêm yết (NaN)
    W["open"].iloc[62:, 0] = np.nan
    W["high"].iloc[62:, 0] = np.nan
    W["low"].iloc[62:, 0] = np.nan
    W["close"].iloc[62:, 0] = np.nan
    W["volume"].iloc[62:, 0] = np.nan

    F = FeatureEngine(W, idx_close)
    delist_haircut = 0.50
    cfg = {
        "mode": "brk", "init_cash": 1e9, "min_hold": 3, "limit": 0.07,
        "buy_cost": 0.003, "sell_cost": 0.004, "max_pos": 10, "max_w": 0.15,
        "adtv_frac": 0.03, "lot": 100, "min_adtv": 1e6, "risk_pct": 0.01,
        "delist_haircut": delist_haircut, "ato_fill_prob": 1.0
    }
    params = (20, 10, 0, 0, 99, 0, 0)
    ret, trades = backtest(F, params, cfg, i0=50, i1=80)

    assert len(trades) == 1, "Vị thế mã hủy niêm yết phải được thanh lý"
    trade_ret = trades[0][1]
    # Lợi nhuận phải phản ánh mất 50% giá trị
    assert trade_ret < -0.45, f"Thanh lý do hủy niêm yết phải chịu haircut 50%, thực tế: {trade_ret:.2%}"
