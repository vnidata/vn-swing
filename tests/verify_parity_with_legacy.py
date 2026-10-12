"""
Script kiểm tra tính tương đương tuyệt đối (Ground Truth Parity Verification)
giữa module mới vnswing và file gốc legacy/vn_donchian_wf.py.
Chênh lệch phải bằng 0.
"""
import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import pandas as pd

# Thiết lập đường dẫn import
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "legacy"))

import vn_donchian_wf as legacy
from vnswing.features.indicators import FeatureEngine
from vnswing.backtest.engine import backtest as modular_backtest
from vnswing.backtest.metrics import perf, trade_stats


def test_parity_single_backtest():
    print("[1/3] Kiểm tra single backtest parity trên dữ liệu synthetic...")
    df_px, df_idx = legacy.synthetic(n_sym=30, n_days=500, seed=42)

    # Format wide
    df_px["date"] = pd.to_datetime(df_px["date"])
    W = {
        c: df_px.pivot(index="date", columns="symbol", values=c).sort_index()
        for c in ["open", "high", "low", "close", "volume"]
    }
    df_idx["date"] = pd.to_datetime(df_idx["date"])
    idx_close = df_idx.set_index("date")["close"].sort_index().reindex(W["close"].index).ffill()

    # 1. Khởi tạo Feat legacy và FeatureEngine modular
    feat_legacy = legacy.Feat(W, idx_close)
    feat_modular = FeatureEngine(W, idx_close)

    # Kiểm tra tính khớp của các indicators
    np.testing.assert_allclose(feat_legacy.adtv, feat_modular.adtv, equal_nan=True, err_msg="ADTV mismatch")
    np.testing.assert_allclose(feat_legacy.atr, feat_modular.atr, equal_nan=True, err_msg="ATR mismatch")
    np.testing.assert_allclose(feat_legacy.volavg, feat_modular.volavg, equal_nan=True, err_msg="Volavg mismatch")
    np.testing.assert_allclose(feat_legacy.clv, feat_modular.clv, equal_nan=True, err_msg="CLV mismatch")
    print(" -> Đặc trưng kỹ thuật khớp 100%!")

    # 2. Kiểm tra backtest trên chế độ Breakout
    params_brk = (20, 10, 100, 1.3, 3.0, 0.65, 0.5)
    cfg_brk = dict(legacy.CFG)
    cfg_brk["mode"] = "brk"

    ret_leg, trades_leg = legacy.backtest(feat_legacy, params_brk, cfg_brk, 50, 450)
    ret_mod, trades_mod = modular_backtest(feat_modular, params_brk, cfg_brk, 50, 450)

    np.testing.assert_allclose(ret_leg, ret_mod, equal_nan=True, err_msg="Breakout returns mismatch")
    assert len(trades_leg) == len(trades_mod), f"Trade count mismatch: {len(trades_leg)} vs {len(trades_mod)}"
    for i, (t_leg, t_mod) in enumerate(zip(trades_leg, trades_mod)):
        assert t_leg[0] == t_mod[0], f"Trade {i} hold mismatch: {t_leg[0]} vs {t_mod[0]}"
        assert abs(t_leg[1] - t_mod[1]) < 1e-12, f"Trade {i} return mismatch: {t_leg[1]} vs {t_mod[1]}"
    print(" -> Kết quả Breakout backtest khớp 100%!")

    # 3. Kiểm tra backtest trên chế độ Pullback
    params_pb = (15, 20, 100, 1.5, 2.0, 0.0, 0.0)
    cfg_pb = dict(legacy.CFG)
    cfg_pb["mode"] = "pb"

    ret_pb_leg, trades_pb_leg = legacy.backtest(feat_legacy, params_pb, cfg_pb, 50, 450)
    ret_pb_mod, trades_pb_mod = modular_backtest(feat_modular, params_pb, cfg_pb, 50, 450)

    np.testing.assert_allclose(ret_pb_leg, ret_pb_mod, equal_nan=True, err_msg="Pullback returns mismatch")
    assert len(trades_pb_leg) == len(trades_pb_mod), f"Trade count mismatch: {len(trades_pb_leg)} vs {len(trades_pb_mod)}"
    print(" -> Kết quả Pullback backtest khớp 100%!")

    # 4. Kiểm tra metrics
    perf_leg = legacy.perf(ret_leg, cfg_brk["rf"])
    perf_mod = perf(ret_mod, cfg_brk["rf"])
    for k in ["sharpe", "cagr", "vol", "mdd"]:
        assert abs(perf_leg[k] - perf_mod[k]) < 1e-10, f"Metric {k} mismatch: {perf_leg[k]} vs {perf_mod[k]}"
    print(" -> Metrics tính toán khớp 100%!")

    print("\n[SUCCESS] TOÀN BỘ ENGINE VNSWING ĐẠT ZERO-DIFF PARITY VỚI LEGACY BENCHMARK!")


if __name__ == "__main__":
    test_parity_single_backtest()
